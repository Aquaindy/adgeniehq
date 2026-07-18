from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.billing.plans import PLANS
from app.models.billing_subscription import (
    BillingSubscription,
    SubscriptionSource,
    SubscriptionStatus,
)
from app.models.usage_event import UsageEvent, UsageEventType
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_workspace(
    db: Session, *, role: Role = Role.OWNER, email: str = "alice@example.com"
) -> tuple[User, Workspace]:
    user = User(email=email, hashed_password=hash_password("correct-horse-9"), is_active=True)
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


def _seed_paid_subscription(
    db: Session,
    *,
    workspace_id,
    plan_code: str = "pro",
    management_url: str = "https://www.paypal.com/myaccount/autopay/",
) -> None:
    """Seed an active PayPal subscription row (no Stripe/Paddle — removed)."""
    db.add(
        BillingSubscription(
            workspace_id=workspace_id,
            plan_code=plan_code,
            status=SubscriptionStatus.ACTIVE,
            source=SubscriptionSource.PAYPAL,
            external_subscription_id=f"I-{plan_code}-{workspace_id}",
            management_url=management_url,
        )
    )
    db.commit()


def _configure_paypal(monkeypatch) -> None:
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "ppl_test_cid")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "ppl_test_secret")
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "ppl_test_whid")
    monkeypatch.setenv("PAYPAL_PLAN_ID_PRO", "P-pro-monthly")
    monkeypatch.setenv("PAYPAL_PLAN_ID_PRO_ANNUAL", "P-pro-yearly")


def _stub_paypal_create(monkeypatch) -> dict:
    """Replace the PayPal subscription-create HTTP call with a capture stub.
    Returns the dict that receives the kwargs create_subscription was called
    with, so tests can assert plan_id / custom_id without hitting the network."""
    from app.integrations import paypal_billing

    captured: dict = {}

    def _fake_create(**kwargs):
        captured.update(kwargs)
        return {"id": "I-TEST-123", "approval_url": "https://paypal.example/approve?ba_token=abc"}

    monkeypatch.setattr(paypal_billing, "create_subscription", _fake_create)
    return captured


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------


def test_status_defaults_to_free_plan(client: TestClient, db_session: Session) -> None:
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    response = client.get(f"/api/v1/workspaces/{workspace.id}/billing/status")
    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["code"] == "free"
    assert body["subscription_status"] == "none"
    assert body["has_billing_customer"] is False
    assert body["usage"]["agent_runs_last_30d"] == 0
    # `free` is the technical fallback for unsubscribed workspaces but is not
    # marketed — the public listing only includes paid tiers.
    plan_codes = {p["code"] for p in body["available_plans"]}
    assert plan_codes == {"starter", "pro", "agency"}
    # Paid plans expose both monthly and annual display prices.
    pro = next(p for p in body["available_plans"] if p["code"] == "pro")
    assert pro["monthly_price_usd"] == 129
    assert pro["annual_price_usd"] == 1290


def test_status_reflects_active_subscription(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    _seed_paid_subscription(db_session, workspace_id=workspace.id, plan_code="pro")
    _login(client, "alice@example.com")
    body = client.get(
        f"/api/v1/workspaces/{workspace.id}/billing/status"
    ).json()
    assert body["plan"]["code"] == "pro"
    assert body["subscription_status"] == "active"
    # A manageable PayPal subscription (has a subscription id).
    assert body["has_billing_customer"] is True
    assert body["subscription_source"] == "paypal"


def test_status_falls_back_to_free_for_past_due(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    _seed_paid_subscription(db_session, workspace_id=workspace.id, plan_code="pro")
    sub = (
        db_session.query(BillingSubscription)
        .filter(BillingSubscription.workspace_id == workspace.id)
        .one()
    )
    sub.status = SubscriptionStatus.PAST_DUE
    db_session.commit()

    _login(client, "alice@example.com")
    body = client.get(
        f"/api/v1/workspaces/{workspace.id}/billing/status"
    ).json()
    assert body["plan"]["code"] == "free"  # limits revert
    assert body["subscription_status"] == "past_due"


# ---------------------------------------------------------------------------
# Plan-limit enforcement on agent runs (caps read from PLANS, not hardcoded)
# ---------------------------------------------------------------------------


def test_agent_run_blocked_when_free_plan_quota_exceeded(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    from app.services.billing_service import CREDIT_COST

    # Exhaust the free plan's AI-credit pool with agent runs; the next run
    # trips the credit gate.
    runs = PLANS["free"].limits.monthly_credits // CREDIT_COST[UsageEventType.AGENT_RUN]
    now = datetime.now(timezone.utc)
    for i in range(runs):
        db_session.add(
            UsageEvent(
                workspace_id=workspace.id,
                event_type=UsageEventType.AGENT_RUN,
                quantity=1,
                occurred_at=now - timedelta(minutes=i),
            )
        )
    db_session.commit()

    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/agents/run",
        json={"agent_type": "onboarding_insight"},
    )
    assert response.status_code == 402
    assert response.json()["error"]["code"] == "insufficient_credits"


def test_agent_run_records_usage_event_when_succeeded(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/agents/run",
        json={"agent_type": "onboarding_insight"},
    )
    assert response.status_code == 201
    count = (
        db_session.query(UsageEvent)
        .filter(
            UsageEvent.workspace_id == workspace.id,
            UsageEvent.event_type == UsageEventType.AGENT_RUN,
        )
        .count()
    )
    assert count == 1


def test_pro_plan_has_higher_quota(client: TestClient, db_session: Session) -> None:
    _, workspace = _seed_workspace(db_session)
    _seed_paid_subscription(db_session, workspace_id=workspace.id, plan_code="pro")
    from app.services.billing_service import CREDIT_COST

    # Over the free credit pool, well under pro's — a paid plan lifts it.
    over_free = (
        PLANS["free"].limits.monthly_credits
        // CREDIT_COST[UsageEventType.AGENT_RUN]
        + 5
    )
    now = datetime.now(timezone.utc)
    for i in range(over_free):
        db_session.add(
            UsageEvent(
                workspace_id=workspace.id,
                event_type=UsageEventType.AGENT_RUN,
                quantity=1,
                occurred_at=now - timedelta(minutes=i),
            )
        )
    db_session.commit()

    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/agents/run",
        json={"agent_type": "onboarding_insight"},
    )
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Landing-page limit enforcement (cap read from PLANS)
# ---------------------------------------------------------------------------


def test_free_plan_blocks_landing_page_over_cap(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    cap = PLANS["free"].limits.landing_pages
    assert cap is not None
    for i in range(cap):
        created = client.post(
            f"/api/v1/workspaces/{workspace.id}/landing-pages",
            json={"url": f"https://acme.example/p{i}"},
        )
        assert created.status_code == 201, created.text

    blocked = client.post(
        f"/api/v1/workspaces/{workspace.id}/landing-pages",
        json={"url": "https://acme.example/over-cap"},
    )
    assert blocked.status_code == 402
    assert blocked.json()["error"]["code"] == "plan_limit_exceeded"


# ---------------------------------------------------------------------------
# PayPal checkout / portal
# ---------------------------------------------------------------------------


def test_checkout_503_when_billing_unconfigured(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/billing/checkout-session",
        json={"plan_code": "starter"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "billing_not_configured"


def test_checkout_404_for_unknown_plan(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    _configure_paypal(monkeypatch)
    _stub_paypal_create(monkeypatch)
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/billing/checkout-session",
        json={"plan_code": "platinum"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_plan"


def test_checkout_returns_paypal_approval_url_monthly(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    _configure_paypal(monkeypatch)
    captured = _stub_paypal_create(monkeypatch)
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/billing/checkout-session",
        json={"plan_code": "pro"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["provider"] == "paypal"
    assert body["paypal"]["approval_url"] == "https://paypal.example/approve?ba_token=abc"
    # The subscription was created against the monthly plan id, and custom_id
    # round-trips workspace + plan + interval for the webhook.
    assert captured["plan_id"] == "P-pro-monthly"
    assert captured["custom_id"] == f"{workspace.id}|pro|month"


def test_checkout_annual_uses_annual_plan(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    _configure_paypal(monkeypatch)
    captured = _stub_paypal_create(monkeypatch)
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/billing/checkout-session",
        json={"plan_code": "pro", "interval": "year"},
    )
    assert response.status_code == 201, response.text
    assert captured["plan_id"] == "P-pro-yearly"
    assert captured["custom_id"] == f"{workspace.id}|pro|year"


def test_checkout_requires_owner_role(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session, role=Role.ADMIN, email="admin@example.com")
    _login(client, "admin@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/billing/checkout-session",
        json={"plan_code": "pro"},
    )
    assert response.status_code == 403


def test_portal_returns_paypal_management_url(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    _seed_paid_subscription(
        db_session,
        workspace_id=workspace.id,
        management_url="https://www.paypal.com/myaccount/autopay/",
    )
    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/billing/portal-session"
    )
    assert response.status_code == 201
    assert response.json()["url"] == "https://www.paypal.com/myaccount/autopay/"


def test_portal_503_when_no_subscription_to_manage(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/billing/portal-session"
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "billing_not_configured"


# ---------------------------------------------------------------------------
# LLM cost surfacing
# ---------------------------------------------------------------------------


def test_llm_cost_cents_aggregates_metadata_micros(
    client: TestClient, db_session: Session
) -> None:
    """billing_service.llm_cost_cents_last_30d sums every LLM_CALL event's
    `estimated_cost_usd_micros` metadata and returns the result in cents."""

    from app.services import billing_service

    _, ws = _seed_workspace(db_session)
    now = datetime.now(timezone.utc)

    # Three LLM calls: 50k + 30k + 20k micros = 100k micros = 10c
    for amount in (50_000, 30_000, 20_000):
        db_session.add(
            UsageEvent(
                workspace_id=ws.id,
                event_type=UsageEventType.LLM_CALL,
                quantity=1234,  # tokens, irrelevant for cost
                metadata_json={"estimated_cost_usd_micros": amount},
                occurred_at=now,
            )
        )
    # An older event without the metadata field should be ignored.
    db_session.add(
        UsageEvent(
            workspace_id=ws.id,
            event_type=UsageEventType.LLM_CALL,
            quantity=999,
            metadata_json={"purpose": "ancient"},
            occurred_at=now,
        )
    )
    db_session.commit()

    cents = billing_service.llm_cost_cents_last_30d(db_session, workspace_id=ws.id)
    assert cents == 10  # 100_000 micros / 10_000 = 10 cents


def test_billing_status_surfaces_llm_cost(
    client: TestClient, db_session: Session
) -> None:
    """End-to-end: GET /billing/status returns llm_cost_cents_last_30d."""

    user, ws = _seed_workspace(db_session)
    db_session.add(
        UsageEvent(
            workspace_id=ws.id,
            event_type=UsageEventType.LLM_CALL,
            quantity=2_000,
            metadata_json={"estimated_cost_usd_micros": 250_000},  # 25 cents
            occurred_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    _login(client, user.email)
    response = client.get(f"/api/v1/workspaces/{ws.id}/billing/status")
    assert response.status_code == 200
    body = response.json()
    assert body["usage"]["llm_cost_cents_last_30d"] == 25
