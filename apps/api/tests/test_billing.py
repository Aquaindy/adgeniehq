from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.billing_customer import BillingCustomer
from app.models.billing_subscription import BillingSubscription, SubscriptionStatus
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
    db: Session, *, workspace_id, plan_code: str = "pro"
) -> None:
    customer = BillingCustomer(
        workspace_id=workspace_id,
        stripe_customer_id=f"cus_test_{plan_code}_{workspace_id}",
        email="alice@example.com",
    )
    db.add(customer)
    db.flush()
    db.add(
        BillingSubscription(
            workspace_id=workspace_id,
            billing_customer_id=customer.id,
            stripe_subscription_id=f"sub_test_{workspace_id}",
            plan_code=plan_code,
            status=SubscriptionStatus.ACTIVE,
        )
    )
    db.commit()


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
    assert body["has_billing_customer"] is True


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
# Plan-limit enforcement on agent runs
# ---------------------------------------------------------------------------


def test_agent_run_blocked_when_free_plan_quota_exceeded(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    # Free plan caps at 10 agent runs / 30d. Seed 10 events.
    now = datetime.now(timezone.utc)
    for i in range(10):
        db_session.add(
            UsageEvent(
                workspace_id=workspace.id,
                event_type=UsageEventType.AGENT_RUN,
                quantity=1,
                occurred_at=now - timedelta(hours=i),
            )
        )
    db_session.commit()

    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/agents/run",
        json={"agent_type": "onboarding_insight"},
    )
    assert response.status_code == 402
    assert response.json()["error"]["code"] == "plan_limit_exceeded"


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
    # 20 events — well under pro's 500/30d ceiling, well over free's 10
    now = datetime.now(timezone.utc)
    for i in range(20):
        db_session.add(
            UsageEvent(
                workspace_id=workspace.id,
                event_type=UsageEventType.AGENT_RUN,
                quantity=1,
                occurred_at=now - timedelta(hours=i),
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
# Landing-page limit enforcement
# ---------------------------------------------------------------------------


def test_free_plan_blocks_second_landing_page(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")

    first = client.post(
        f"/api/v1/workspaces/{workspace.id}/landing-pages",
        json={"url": "https://acme.example/pricing"},
    )
    assert first.status_code == 201

    second = client.post(
        f"/api/v1/workspaces/{workspace.id}/landing-pages",
        json={"url": "https://acme.example/demo"},
    )
    assert second.status_code == 402
    assert second.json()["error"]["code"] == "plan_limit_exceeded"


# ---------------------------------------------------------------------------
# Checkout / Portal sessions (mocked Stripe SDK)
# ---------------------------------------------------------------------------


def test_checkout_session_503_when_stripe_unconfigured(
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


def test_checkout_session_404_for_unknown_plan(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_xxx")
    monkeypatch.setenv("STRIPE_PRICE_ID_STARTER", "price_starter_xxx")
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/billing/checkout-session",
        json={"plan_code": "platinum"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_plan"


def test_checkout_session_creates_customer_and_returns_url(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_xxx")
    monkeypatch.setenv("STRIPE_PRICE_ID_PRO", "price_pro_xxx")
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")

    with patch(
        "stripe.Customer.create",
        return_value={"id": "cus_test_123"},
    ) as cust_mock, patch(
        "stripe.checkout.Session.create",
        return_value={"id": "cs_test_xxx", "url": "https://checkout.stripe.com/c/pay/x"},
    ) as session_mock:
        response = client.post(
            f"/api/v1/workspaces/{workspace.id}/billing/checkout-session",
            json={"plan_code": "pro"},
        )
    assert response.status_code == 201
    assert response.json()["url"] == "https://checkout.stripe.com/c/pay/x"
    assert cust_mock.called
    session_kwargs = session_mock.call_args.kwargs
    assert session_kwargs["customer"] == "cus_test_123"
    assert session_kwargs["mode"] == "subscription"
    assert session_kwargs["line_items"][0]["price"] == "price_pro_xxx"
    assert session_kwargs["client_reference_id"] == str(workspace.id)

    customer = (
        db_session.query(BillingCustomer)
        .filter(BillingCustomer.workspace_id == workspace.id)
        .one()
    )
    assert customer.stripe_customer_id == "cus_test_123"


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


def test_portal_session_returns_url(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_xxx")
    _, workspace = _seed_workspace(db_session)
    _seed_paid_subscription(db_session, workspace_id=workspace.id)
    _login(client, "alice@example.com")
    with patch(
        "stripe.billing_portal.Session.create",
        return_value={"url": "https://billing.stripe.com/p/session/x"},
    ):
        response = client.post(
            f"/api/v1/workspaces/{workspace.id}/billing/portal-session"
        )
    assert response.status_code == 201
    assert response.json()["url"] == "https://billing.stripe.com/p/session/x"


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------


def test_webhook_rejects_invalid_signature(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_xxx")
    response = client.post(
        "/api/v1/billing/webhook",
        content=b'{"type":"customer.subscription.updated"}',
        headers={"Stripe-Signature": "t=0,v1=bad"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_webhook_signature"


def test_webhook_503_when_secret_missing(client: TestClient) -> None:
    response = client.post(
        "/api/v1/billing/webhook",
        content=b'{}',
        headers={"Stripe-Signature": "t=0,v1=x"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "billing_not_configured"


def test_webhook_subscription_updated_promotes_workspace_to_pro(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_xxx")
    monkeypatch.setenv("STRIPE_PRICE_ID_PRO", "price_pro_xxx")

    _, workspace = _seed_workspace(db_session)
    _seed_paid_subscription(db_session, workspace_id=workspace.id, plan_code="free")
    customer = (
        db_session.query(BillingCustomer)
        .filter(BillingCustomer.workspace_id == workspace.id)
        .one()
    )

    fake_event = {
        "id": "evt_test_1",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_test_xxx",
                "customer": customer.stripe_customer_id,
                "status": "active",
                "items": {"data": [{"price": {"id": "price_pro_xxx"}}]},
                "current_period_start": 1738368000,
                "current_period_end": 1741046400,
                "cancel_at_period_end": False,
                "trial_end": None,
            }
        },
    }

    with patch(
        "stripe.Webhook.construct_event", return_value=fake_event
    ):
        response = client.post(
            "/api/v1/billing/webhook",
            content=b'{}',
            headers={"Stripe-Signature": "t=1,v1=fake"},
        )
    assert response.status_code == 200

    sub = (
        db_session.query(BillingSubscription)
        .filter(BillingSubscription.workspace_id == workspace.id)
        .one()
    )
    db_session.refresh(sub)
    assert sub.plan_code == "pro"
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.stripe_subscription_id == "sub_test_xxx"


def test_webhook_subscription_deleted_reverts_to_free(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_xxx")

    _, workspace = _seed_workspace(db_session)
    _seed_paid_subscription(db_session, workspace_id=workspace.id, plan_code="pro")
    customer = (
        db_session.query(BillingCustomer)
        .filter(BillingCustomer.workspace_id == workspace.id)
        .one()
    )

    fake_event = {
        "id": "evt_test_del",
        "type": "customer.subscription.deleted",
        "data": {"object": {"customer": customer.stripe_customer_id}},
    }

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        response = client.post(
            "/api/v1/billing/webhook",
            content=b'{}',
            headers={"Stripe-Signature": "t=1,v1=fake"},
        )
    assert response.status_code == 200

    sub = (
        db_session.query(BillingSubscription)
        .filter(BillingSubscription.workspace_id == workspace.id)
        .one()
    )
    db_session.refresh(sub)
    assert sub.plan_code == "free"
    assert sub.status == SubscriptionStatus.CANCELED


def test_llm_cost_cents_aggregates_metadata_micros(
    client: TestClient, db_session: Session
) -> None:
    """billing_service.llm_cost_cents_last_30d sums every LLM_CALL event's
    `estimated_cost_usd_micros` metadata and returns the result in cents."""

    from datetime import datetime, timezone
    from app.models.usage_event import UsageEvent, UsageEventType
    from app.services import billing_service

    _, ws = _seed_workspace(db_session)
    now = datetime.now(timezone.utc)

    # Three LLM calls: 50k micros + 30k micros + 20k micros = 100k micros = 10c
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

    cents = billing_service.llm_cost_cents_last_30d(
        db_session, workspace_id=ws.id
    )
    assert cents == 10  # 100_000 micros / 10_000 = 10 cents


def test_billing_status_surfaces_llm_cost(
    client: TestClient, db_session: Session
) -> None:
    """End-to-end: GET /billing/status returns llm_cost_cents_last_30d."""

    from datetime import datetime, timezone
    from app.models.usage_event import UsageEvent, UsageEventType

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
