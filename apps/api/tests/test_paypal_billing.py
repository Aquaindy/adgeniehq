"""PayPal recurring-subscription billing.

Covers: plan <-> PayPal Plan id mapping, webhook idempotency (a replayed event
id is a no-op), subscription event -> plan/status mapping, cancellation, the
checkout endpoint returning a PayPal approval URL when configured, the
signature-verified webhook endpoint, and fee-invoice confirmation via
INVOICING.INVOICE.PAID.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations import paypal_billing
from app.models.billing_subscription import (
    BillingSubscription,
    SubscriptionSource,
    SubscriptionStatus,
)
from app.models.fee_invoice import FeeInvoice, FeeInvoiceStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role
from app.services import billing_service


def _set_paypal_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "ppl_cid")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "ppl_secret")
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "ppl_whid")
    monkeypatch.setenv("PAYPAL_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("PAYPAL_PLAN_ID_STARTER", "P-starter")
    monkeypatch.setenv("PAYPAL_PLAN_ID_PRO", "P-pro")
    monkeypatch.setenv("PAYPAL_PLAN_ID_AGENCY", "P-agency")


def _seed(db: Session, *, email: str = "owner@x.com") -> tuple[User, Workspace]:
    user = User(email=email, hashed_password=hash_password("correct-horse-9"), is_active=True)
    db.add(user)
    db.flush()
    ws = Workspace(name="WS", slug=f"ws-{email.split('@')[0]}")
    db.add(ws)
    db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=ws.id, user_id=user.id, role=Role.OWNER, status=MemberStatus.ACTIVE
        )
    )
    db.commit()
    return user, ws


def _sub_event(
    ws: Workspace,
    *,
    event_id: str,
    event_type: str = "BILLING.SUBSCRIPTION.ACTIVATED",
    status: str = "ACTIVE",
    plan_id: str = "P-starter",
    plan: str = "starter",
    interval: str = "month",
) -> dict:
    return {
        "id": event_id,
        "event_type": event_type,
        "resource": {
            "id": "I-SUB123",
            "status": status,
            "plan_id": plan_id,
            "custom_id": f"{ws.id}|{plan}|{interval}",
            "start_time": "2026-06-01T00:00:00Z",
            "billing_info": {"next_billing_time": "2026-07-01T00:00:00Z"},
        },
    }


def _sub(db: Session, ws: Workspace) -> BillingSubscription | None:
    return (
        db.query(BillingSubscription)
        .filter(BillingSubscription.workspace_id == ws.id)
        .first()
    )


# ---------------------------------------------------------------------------
# Plan mapping
# ---------------------------------------------------------------------------


def test_plan_id_mapping_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_paypal_env(monkeypatch)
    assert paypal_billing.plan_id_for_plan("pro") == "P-pro"
    assert paypal_billing.plan_for_plan_id("P-agency") == "agency"
    assert paypal_billing.plan_for_plan_id("P-unknown") is None


def test_status_mapping() -> None:
    assert paypal_billing.map_status("ACTIVE") == SubscriptionStatus.ACTIVE
    assert paypal_billing.map_status("SUSPENDED") == SubscriptionStatus.PAST_DUE
    assert paypal_billing.map_status("CANCELLED") == SubscriptionStatus.CANCELED
    assert paypal_billing.map_status("APPROVAL_PENDING") == SubscriptionStatus.INCOMPLETE


# ---------------------------------------------------------------------------
# Webhook processing + idempotency
# ---------------------------------------------------------------------------


def test_subscription_event_sets_plan_and_status(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_paypal_env(monkeypatch)
    _, ws = _seed(db_session)
    billing_service.process_paypal_webhook(
        db_session, _sub_event(ws, event_id="evt_1", plan="pro", plan_id="P-pro")
    )
    sub = _sub(db_session, ws)
    assert sub is not None
    assert sub.source == SubscriptionSource.PAYPAL
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.plan_code == "pro"
    assert sub.external_subscription_id == "I-SUB123"
    assert sub.external_price_id == "P-pro"
    assert sub.current_period_end is not None


def test_webhook_is_idempotent_on_replayed_event_id(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_paypal_env(monkeypatch)
    _, ws = _seed(db_session)
    billing_service.process_paypal_webhook(
        db_session, _sub_event(ws, event_id="evt_dup", plan="starter")
    )
    sub = _sub(db_session, ws)
    assert sub.status == SubscriptionStatus.ACTIVE

    # Re-deliver the SAME event id carrying a (stale) cancelled state — must be a
    # no-op, not resurrect/cancel the subscription.
    billing_service.process_paypal_webhook(
        db_session,
        _sub_event(
            ws,
            event_id="evt_dup",
            event_type="BILLING.SUBSCRIPTION.CANCELLED",
            status="CANCELLED",
            plan="starter",
        ),
    )
    db_session.refresh(sub)
    assert sub.status == SubscriptionStatus.ACTIVE  # unchanged by the replay


def test_subscription_canceled_downgrades_to_free(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_paypal_env(monkeypatch)
    _, ws = _seed(db_session)
    billing_service.process_paypal_webhook(
        db_session, _sub_event(ws, event_id="evt_a", plan="pro", plan_id="P-pro")
    )
    billing_service.process_paypal_webhook(
        db_session,
        _sub_event(
            ws,
            event_id="evt_b",
            event_type="BILLING.SUBSCRIPTION.CANCELLED",
            status="CANCELLED",
        ),
    )
    sub = _sub(db_session, ws)
    assert sub.status == SubscriptionStatus.CANCELED
    assert sub.plan_code == "free"


def test_invoice_paid_confirms_fee_invoice(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_paypal_env(monkeypatch)
    _, ws = _seed(db_session)
    inv = FeeInvoice(
        workspace_id=ws.id, provider="paypal", status=FeeInvoiceStatus.OPEN,
        amount_cents=2500, currency="USD", accrual_count=1, external_id="INV-999",
    )
    db_session.add(inv)
    db_session.commit()

    event = {
        "id": "evt_inv",
        "event_type": "INVOICING.INVOICE.PAID",
        "resource": {"invoice": {"id": "INV-999"}},
    }
    billing_service.process_paypal_webhook(db_session, event)
    db_session.refresh(inv)
    assert inv.status == FeeInvoiceStatus.PAID


# ---------------------------------------------------------------------------
# Checkout endpoint
# ---------------------------------------------------------------------------


def _signup(client: TestClient) -> str:
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "paypal-owner@x.com", "password": "correct-horse-9", "full_name": "O"},
    )
    client.headers.update({"Authorization": f"Bearer {reg.json()['access_token']}"})
    return client.post("/api/v1/workspaces", json={"name": "Acme"}).json()["id"]


def test_checkout_returns_approval_url_when_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_paypal_env(monkeypatch)
    captured: dict = {}

    def _fake_create(**kwargs):
        captured.update(kwargs)
        return {"id": "I-XYZ", "approval_url": "https://paypal.example/approve?ba_token=z"}

    monkeypatch.setattr(paypal_billing, "create_subscription", _fake_create)

    ws_id = _signup(client)
    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/billing/checkout-session",
        json={"plan_code": "starter"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["provider"] == "paypal"
    assert body["paypal"]["approval_url"] == "https://paypal.example/approve?ba_token=z"
    assert captured["plan_id"] == "P-starter"
    assert captured["custom_id"] == f"{ws_id}|starter|month"


def test_paypal_webhook_endpoint_verifies_and_applies(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_paypal_env(monkeypatch)
    _, ws = _seed(db_session, email="http-owner@x.com")
    event = _sub_event(ws, event_id="evt_http", plan="starter")
    body = json.dumps(event).encode()

    # Bad signature -> the verify call raises -> 400, nothing applied.
    def _reject(_headers, _event):
        raise paypal_billing.PayPalSignatureError("nope")

    monkeypatch.setattr(paypal_billing, "verify_webhook", _reject)
    bad = client.post("/api/v1/billing/paypal/webhook", content=body)
    assert bad.status_code == 400

    # Valid signature -> verify passes -> event applied.
    monkeypatch.setattr(paypal_billing, "verify_webhook", lambda _h, _e: None)
    ok = client.post("/api/v1/billing/paypal/webhook", content=body)
    assert ok.status_code == 200
    sub = _sub(db_session, ws)
    assert sub is not None and sub.status == SubscriptionStatus.ACTIVE
