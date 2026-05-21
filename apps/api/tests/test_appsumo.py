from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.appsumo_code import AppSumoCode, AppSumoCodeStatus
from app.models.billing_subscription import (
    BillingSubscription,
    SubscriptionSource,
    SubscriptionStatus,
)
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_workspace(
    db: Session,
    *,
    role: Role = Role.OWNER,
    email: str = "alice@example.com",
    is_superuser: bool = False,
) -> tuple[User, Workspace]:
    user = User(
        email=email,
        hashed_password=hash_password("correct-horse-9"),
        is_active=True,
        is_superuser=is_superuser,
    )
    db.add(user)
    db.flush()
    workspace = Workspace(name="Acme", slug=f"acme-{email.split('@')[0]}")
    db.add(workspace)
    db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=workspace.id, user_id=user.id, role=role, status=MemberStatus.ACTIVE
        )
    )
    db.commit()
    return user, workspace


def _login(client: TestClient, email: str) -> None:
    token = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct-horse-9"},
    ).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})


def _seed_codes(db: Session, codes: list[str]) -> None:
    for c in codes:
        db.add(AppSumoCode(code=c, status=AppSumoCodeStatus.UNREDEEMED, batch="t"))
    db.commit()


# ---------------------------------------------------------------------------
# Redemption + stacking
# ---------------------------------------------------------------------------


def test_redeem_grants_tier1(client: TestClient, db_session: Session) -> None:
    _, ws = _seed_workspace(db_session)
    _seed_codes(db_session, ["ADV-AAAA-BBBB-CCCC"])
    _login(client, "alice@example.com")

    r = client.post(
        f"/api/v1/workspaces/{ws.id}/appsumo/redeem",
        json={"code": "adv-aaaa-bbbb-cccc"},  # case-insensitive
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tier"] == 1
    assert body["codes_redeemed"] == 1
    assert body["plan_code"] == "appsumo_tier1"
    assert body["can_stack_more"] is True

    # Subscription row reflects a lifetime AppSumo grant.
    sub = (
        db_session.query(BillingSubscription)
        .filter(BillingSubscription.workspace_id == ws.id)
        .one()
    )
    db_session.refresh(sub)
    assert sub.source == SubscriptionSource.APPSUMO
    assert sub.plan_code == "appsumo_tier1"
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.billing_customer_id is None


def test_stacking_climbs_tiers_and_caps_at_max(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session)
    _seed_codes(db_session, ["ADV-1", "ADV-2", "ADV-3", "ADV-4"])
    _login(client, "alice@example.com")

    expected = {"ADV-1": ("appsumo_tier1", 1), "ADV-2": ("appsumo_tier2", 2), "ADV-3": ("appsumo_tier3", 3)}
    for code, (plan, tier) in expected.items():
        body = client.post(
            f"/api/v1/workspaces/{ws.id}/appsumo/redeem", json={"code": code}
        ).json()
        assert body["plan_code"] == plan
        assert body["tier"] == tier

    # 4th code exceeds the 3-code ceiling.
    r = client.post(f"/api/v1/workspaces/{ws.id}/appsumo/redeem", json={"code": "ADV-4"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "appsumo_max_tier_reached"


def test_redeem_unknown_code_404(client: TestClient, db_session: Session) -> None:
    _, ws = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/appsumo/redeem", json={"code": "ADV-NOPE"}
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "appsumo_code_not_found"


def test_redeem_already_used_code_409(client: TestClient, db_session: Session) -> None:
    _, ws_a = _seed_workspace(db_session, email="alice@example.com")
    _, ws_b = _seed_workspace(db_session, email="bob@example.com")
    _seed_codes(db_session, ["ADV-ONCE"])

    _login(client, "alice@example.com")
    assert client.post(
        f"/api/v1/workspaces/{ws_a.id}/appsumo/redeem", json={"code": "ADV-ONCE"}
    ).status_code == 200

    _login(client, "bob@example.com")
    r = client.post(
        f"/api/v1/workspaces/{ws_b.id}/appsumo/redeem", json={"code": "ADV-ONCE"}
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "appsumo_code_already_redeemed"


def test_redeem_requires_owner(client: TestClient, db_session: Session) -> None:
    _, ws = _seed_workspace(db_session, role=Role.ADMIN, email="admin@example.com")
    _seed_codes(db_session, ["ADV-OWN"])
    _login(client, "admin@example.com")
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/appsumo/redeem", json={"code": "ADV-OWN"}
    )
    assert r.status_code == 403


def test_status_reflects_in_billing(client: TestClient, db_session: Session) -> None:
    user, ws = _seed_workspace(db_session)
    _seed_codes(db_session, ["ADV-LIFE"])
    _login(client, user.email)
    client.post(f"/api/v1/workspaces/{ws.id}/appsumo/redeem", json={"code": "ADV-LIFE"})

    body = client.get(f"/api/v1/workspaces/{ws.id}/billing/status").json()
    assert body["plan"]["code"] == "appsumo_tier1"
    assert body["subscription_source"] == "appsumo"
    assert body["subscription_status"] == "active"


# ---------------------------------------------------------------------------
# Admin code minting (superuser)
# ---------------------------------------------------------------------------


def test_admin_generate_requires_superuser(
    client: TestClient, db_session: Session
) -> None:
    _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    r = client.post("/api/v1/appsumo/admin/codes", json={"count": 5})
    assert r.status_code == 403


def test_admin_generate_mints_unique_codes(
    client: TestClient, db_session: Session
) -> None:
    _seed_workspace(db_session, email="root@example.com", is_superuser=True)
    _login(client, "root@example.com")
    r = client.post(
        "/api/v1/appsumo/admin/codes", json={"count": 25, "batch": "launch", "prefix": "ADV"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["generated"] == 25
    assert len(set(body["codes"])) == 25
    assert all(c.startswith("ADV-") for c in body["codes"])

    stats = client.get("/api/v1/appsumo/admin/codes/stats").json()
    assert stats["total"] == 25
    assert stats["unredeemed"] == 25


def test_admin_deactivate_downgrades_workspace(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed_workspace(db_session, email="root@example.com", is_superuser=True)
    _seed_codes(db_session, ["ADV-REFUND"])
    _login(client, "root@example.com")
    client.post(f"/api/v1/workspaces/{ws.id}/appsumo/redeem", json={"code": "ADV-REFUND"})

    r = client.post(
        "/api/v1/appsumo/admin/codes/deactivate", json={"code": "ADV-REFUND"}
    )
    assert r.status_code == 200
    assert r.json()["workspace_status"]["tier"] == 0

    sub = (
        db_session.query(BillingSubscription)
        .filter(BillingSubscription.workspace_id == ws.id)
        .one()
    )
    db_session.refresh(sub)
    assert sub.plan_code == "free"
    assert sub.status == SubscriptionStatus.NONE
