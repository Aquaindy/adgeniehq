"""Platform fee engine: schedule resolution, quoting, accrual, summaries, admin CRUD."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.campaign import Campaign, CampaignStatus
from app.models.fee_accrual import FeeAccrual, FeeType
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role
from app.services import fee_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_member(
    db: Session, *, email: str, role: Role = Role.OWNER, is_superuser: bool = False
) -> tuple[User, Workspace]:
    user = User(
        email=email,
        hashed_password=hash_password("correct-horse-9"),
        is_active=True,
        is_superuser=is_superuser,
    )
    db.add(user)
    db.flush()
    ws = Workspace(name="Test", slug=f"test-{email.split('@')[0]}")
    db.add(ws)
    db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=ws.id, user_id=user.id, role=role, status=MemberStatus.ACTIVE
        )
    )
    db.commit()
    return user, ws


def _seed_campaign(
    db: Session,
    *,
    workspace: Workspace,
    provider: str = "meta_ads",
    objective: str = "Lead generation",
    daily_budget_cents: int | None = 4000,
) -> Campaign:
    c = Campaign(
        workspace_id=workspace.id,
        provider=provider,
        external_id="100",
        external_account_id="act_42",
        name="Summer Sale",
        status=CampaignStatus.ACTIVE,
        objective=objective,
        daily_budget_cents=daily_budget_cents,
        currency="USD",
        last_synced_at=datetime.now(timezone.utc),
        raw_payload={},
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _login(client: TestClient, email: str) -> None:
    resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-9"}
    )
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})


# ---------------------------------------------------------------------------
# Quoting
# ---------------------------------------------------------------------------


def test_quote_uses_defaults_when_no_rule(client: TestClient, db_session: Session) -> None:
    _, ws = _seed_member(db_session, email="o@example.com")
    c = _seed_campaign(db_session, workspace=ws)  # leads, $40/day

    _login(client, "o@example.com")
    resp = client.get(f"/api/v1/workspaces/{ws.id}/campaigns/{c.id}/fee-quote")
    assert resp.status_code == 200, resp.text
    q = resp.json()
    assert q["source"] == "default"
    assert q["campaign_type"] == "leads"
    assert q["listing_fee_cents"] == 2500
    assert q["run_pct_basis_points"] == 1000
    # 4000/day * 30 = 120000 spend; 10% = 12000 monthly run fee
    assert q["est_monthly_spend_cents"] == 120000
    assert q["est_monthly_run_fee_cents"] == 12000
    assert q["est_first_month_total_cents"] == 14500


def test_normalize_campaign_type() -> None:
    assert fee_service.normalize_campaign_type("Lead generation") == "leads"
    assert fee_service.normalize_campaign_type("OUTCOME_SALES") == "sales"
    assert fee_service.normalize_campaign_type("Brand Awareness") == "awareness"
    assert fee_service.normalize_campaign_type(None) == "other"


# ---------------------------------------------------------------------------
# Admin schedule + resolution
# ---------------------------------------------------------------------------


def test_admin_rule_overrides_default_and_resolves_by_specificity(
    client: TestClient, db_session: Session
) -> None:
    su, _ = _seed_member(db_session, email="root@example.com", is_superuser=True)
    _, ws = _seed_member(db_session, email="o@example.com")
    c = _seed_campaign(db_session, workspace=ws, provider="meta_ads", objective="Lead generation")

    _login(client, "root@example.com")
    # Wildcard default rule + a specific meta_ads/leads rule.
    client.post(
        "/api/v1/admin/fee-rules",
        json={"label": "Global", "listing_fee_cents": 1000, "run_flat_fee_cents": 0, "run_pct_basis_points": 500},
    )
    specific = client.post(
        "/api/v1/admin/fee-rules",
        json={
            "provider": "meta_ads",
            "campaign_type": "leads",
            "label": "Meta Leads",
            "listing_fee_cents": 5000,
            "run_flat_fee_cents": 1500,
            "run_pct_basis_points": 800,
        },
    )
    assert specific.status_code == 201, specific.text

    _login(client, "o@example.com")
    q = client.get(f"/api/v1/workspaces/{ws.id}/campaigns/{c.id}/fee-quote").json()
    assert q["source"] == "rule"
    assert q["listing_fee_cents"] == 5000  # most-specific rule wins
    assert q["run_flat_fee_cents"] == 1500
    assert q["run_pct_basis_points"] == 800


def test_upsert_updates_existing_rule(client: TestClient, db_session: Session) -> None:
    _seed_member(db_session, email="root@example.com", is_superuser=True)
    _login(client, "root@example.com")
    first = client.post(
        "/api/v1/admin/fee-rules",
        json={"provider": "google_ads", "campaign_type": "sales", "label": "G Sales",
              "listing_fee_cents": 3000, "run_flat_fee_cents": 0, "run_pct_basis_points": 700},
    ).json()
    second = client.post(
        "/api/v1/admin/fee-rules",
        json={"provider": "google_ads", "campaign_type": "sales", "label": "G Sales v2",
              "listing_fee_cents": 4000, "run_flat_fee_cents": 0, "run_pct_basis_points": 900},
    ).json()
    assert first["id"] == second["id"]  # upsert, not duplicate
    assert second["listing_fee_cents"] == 4000
    rules = client.get("/api/v1/admin/fee-rules").json()
    assert len([r for r in rules if r["provider"] == "google_ads"]) == 1


def test_admin_fee_endpoints_require_superuser(
    client: TestClient, db_session: Session
) -> None:
    _seed_member(db_session, email="o@example.com", role=Role.OWNER)  # not superuser
    _login(client, "o@example.com")
    assert client.get("/api/v1/admin/fee-rules").status_code == 403
    assert (
        client.post(
            "/api/v1/admin/fee-rules",
            json={"label": "x", "listing_fee_cents": 1, "run_flat_fee_cents": 0, "run_pct_basis_points": 0},
        ).status_code
        == 403
    )


def test_pct_over_100pct_rejected(client: TestClient, db_session: Session) -> None:
    _seed_member(db_session, email="root@example.com", is_superuser=True)
    _login(client, "root@example.com")
    resp = client.post(
        "/api/v1/admin/fee-rules",
        json={"label": "bad", "listing_fee_cents": 0, "run_flat_fee_cents": 0, "run_pct_basis_points": 10001},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Accrual + summaries (service-level)
# ---------------------------------------------------------------------------


def test_accrue_listing_fee_is_idempotent(db_session: Session) -> None:
    _, ws = _seed_member(db_session, email="o@example.com")
    c = _seed_campaign(db_session, workspace=ws)

    a1 = fee_service.accrue_listing_fee(db_session, campaign=c, actor_user_id=None)
    a2 = fee_service.accrue_listing_fee(db_session, campaign=c, actor_user_id=None)
    db_session.commit()
    assert a1 is not None and a1.id == a2.id
    rows = (
        db_session.query(FeeAccrual)
        .filter(FeeAccrual.campaign_id == c.id, FeeAccrual.fee_type == FeeType.LISTING)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].amount_cents == 2500


def test_run_fee_accrual_and_summary(client: TestClient, db_session: Session) -> None:
    _, ws = _seed_member(db_session, email="o@example.com")
    c = _seed_campaign(db_session, workspace=ws, daily_budget_cents=4000)  # leads

    fee_service.accrue_listing_fee(db_session, campaign=c, actor_user_id=None)
    fee_service.accrue_run_fees_for_workspace(db_session, workspace_id=ws.id, period="2026-06")

    _login(client, "o@example.com")
    summary = client.get(f"/api/v1/workspaces/{ws.id}/billing/fees?period=2026-06").json()
    # listing $25 + run pct (10% of $1200 = $120) = $145 in the period
    assert summary["by_type"]["listing"] == 2500
    assert summary["by_type"]["run_pct"] == 12000
    assert summary["total_cents"] == 14500


def test_run_fee_accrual_idempotent_per_period(db_session: Session) -> None:
    _, ws = _seed_member(db_session, email="o@example.com")
    c = _seed_campaign(db_session, workspace=ws)
    fee_service.accrue_run_fees_for_workspace(db_session, workspace_id=ws.id, period="2026-06")
    fee_service.accrue_run_fees_for_workspace(db_session, workspace_id=ws.id, period="2026-06")
    rows = (
        db_session.query(FeeAccrual)
        .filter(FeeAccrual.campaign_id == c.id, FeeAccrual.fee_type == FeeType.RUN_PCT)
        .all()
    )
    assert len(rows) == 1


def test_admin_revenue_summary(client: TestClient, db_session: Session) -> None:
    su, ws_su = _seed_member(db_session, email="root@example.com", is_superuser=True)
    _, ws = _seed_member(db_session, email="o@example.com")
    c = _seed_campaign(db_session, workspace=ws)
    fee_service.accrue_listing_fee(db_session, campaign=c, actor_user_id=None)
    db_session.commit()

    _login(client, "root@example.com")
    rev = client.get("/api/v1/admin/fees/revenue").json()
    assert rev["all_time_total_cents"] >= 2500
    assert rev["accrual_count"] >= 1
