"""Paddle recurring-subscription billing.

Covers: webhook signature verification, webhook idempotency (replayed event_id
is a no-op), subscription event -> plan/status mapping, cancellation, the
checkout endpoint returning the Paddle overlay config when configured, and the
fee-invoice payment confirmation via transaction.completed.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations import paddle_billing
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

_SECRET = "whsec_test_paddle"


def _set_paddle_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PADDLE_API_KEY", "pdl_test_key")
    monkeypatch.setenv("PADDLE_WEBHOOK_SECRET", _SECRET)
    monkeypatch.setenv("PADDLE_CLIENT_TOKEN", "ptok_test")
    monkeypatch.setenv("PADDLE_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("PADDLE_PRICE_ID_STARTER", "pri_starter")
    monkeypatch.setenv("PADDLE_PRICE_ID_PRO", "pri_pro")
    monkeypatch.setenv("PADDLE_PRICE_ID_AGENCY", "pri_agency")


def _sign(body: bytes, *, ts: str = "1700000000") -> str:
    digest = hmac.new(_SECRET.encode(), ts.encode() + b":" + body, hashlib.sha256).hexdigest()
    return f"ts={ts};h1={digest}"


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
    event_type: str = "subscription.updated",
    status: str = "active",
    price_id: str = "pri_starter",
    plan: str = "starter",
) -> dict:
    return {
        "event_id": event_id,
        "event_type": event_type,
        "data": {
            "id": "sub_123",
            "status": status,
            "items": [{"price": {"id": price_id}}],
            "custom_data": {"workspace_id": str(ws.id), "plan_code": plan},
            "current_billing_period": {
                "starts_at": "2026-06-01T00:00:00Z",
                "ends_at": "2026-07-01T00:00:00Z",
            },
            "management_urls": {"update": "https://paddle.test/manage/abc"},
        },
    }


def _sub(db: Session, ws: Workspace) -> BillingSubscription | None:
    return (
        db.query(BillingSubscription)
        .filter(BillingSubscription.workspace_id == ws.id)
        .first()
    )


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


def test_verify_webhook_rejects_bad_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_paddle_env(monkeypatch)
    with pytest.raises(paddle_billing.PaddleSignatureError):
        paddle_billing.verify_webhook(b"{}", "ts=1;h1=deadbeef")


def test_verify_webhook_rejects_missing_header(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_paddle_env(monkeypatch)
    with pytest.raises(paddle_billing.PaddleSignatureError):
        paddle_billing.verify_webhook(b"{}", None)


def test_verify_webhook_accepts_valid_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_paddle_env(monkeypatch)
    body = b'{"event_id":"evt_x","event_type":"subscription.updated","data":{}}'
    event = paddle_billing.verify_webhook(body, _sign(body))
    assert event["event_id"] == "evt_x"


# ---------------------------------------------------------------------------
# Plan mapping
# ---------------------------------------------------------------------------


def test_price_plan_mapping_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_paddle_env(monkeypatch)
    assert paddle_billing.price_id_for_plan("pro") == "pri_pro"
    assert paddle_billing.plan_for_price_id("pri_agency") == "agency"
    assert paddle_billing.plan_for_price_id("pri_unknown") is None


# ---------------------------------------------------------------------------
# Webhook processing + idempotency
# ---------------------------------------------------------------------------


def test_subscription_event_sets_plan_and_status(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_paddle_env(monkeypatch)
    _, ws = _seed(db_session)
    billing_service.process_paddle_webhook(
        db_session, _sub_event(ws, event_id="evt_1", status="active", plan="pro", price_id="pri_pro")
    )
    sub = _sub(db_session, ws)
    assert sub is not None
    assert sub.source == SubscriptionSource.PADDLE
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.plan_code == "pro"
    assert sub.external_subscription_id == "sub_123"
    assert sub.external_price_id == "pri_pro"
    assert sub.current_period_end is not None
    assert sub.management_url == "https://paddle.test/manage/abc"


def test_webhook_is_idempotent_on_replayed_event_id(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_paddle_env(monkeypatch)
    _, ws = _seed(db_session)
    billing_service.process_paddle_webhook(
        db_session, _sub_event(ws, event_id="evt_dup", status="active", plan="starter")
    )
    sub = _sub(db_session, ws)
    assert sub.status == SubscriptionStatus.ACTIVE

    # Re-deliver the SAME event_id carrying a (stale) canceled state — must be a
    # no-op, not resurrect/cancel the subscription.
    billing_service.process_paddle_webhook(
        db_session,
        _sub_event(ws, event_id="evt_dup", status="canceled", plan="starter"),
    )
    db_session.refresh(sub)
    assert sub.status == SubscriptionStatus.ACTIVE  # unchanged by the replay


def test_subscription_canceled_downgrades_to_free(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_paddle_env(monkeypatch)
    _, ws = _seed(db_session)
    billing_service.process_paddle_webhook(
        db_session, _sub_event(ws, event_id="evt_a", status="active", plan="pro", price_id="pri_pro")
    )
    billing_service.process_paddle_webhook(
        db_session,
        _sub_event(ws, event_id="evt_b", event_type="subscription.canceled", status="canceled"),
    )
    sub = _sub(db_session, ws)
    assert sub.status == SubscriptionStatus.CANCELED
    assert sub.plan_code == "free"


def test_transaction_completed_confirms_fee_invoice(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_paddle_env(monkeypatch)
    _, ws = _seed(db_session)
    inv = FeeInvoice(
        workspace_id=ws.id, provider="paddle", status=FeeInvoiceStatus.OPEN,
        amount_cents=2500, currency="USD", accrual_count=1, external_id="txn_999",
    )
    db_session.add(inv)
    db_session.commit()

    event = {
        "event_id": "evt_txn",
        "event_type": "transaction.completed",
        "data": {"id": "txn_999"},
    }
    billing_service.process_paddle_webhook(db_session, event)
    db_session.refresh(inv)
    assert inv.status == FeeInvoiceStatus.PAID


# ---------------------------------------------------------------------------
# Checkout endpoint
# ---------------------------------------------------------------------------


def _signup(client: TestClient) -> str:
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "paddle-owner@x.com", "password": "correct-horse-9", "full_name": "O"},
    )
    client.headers.update({"Authorization": f"Bearer {reg.json()['access_token']}"})
    return client.post("/api/v1/workspaces", json={"name": "Acme"}).json()["id"]


def test_checkout_returns_paddle_overlay_when_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_paddle_env(monkeypatch)
    ws_id = _signup(client)
    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/billing/checkout-session",
        json={"plan_code": "starter"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["provider"] == "paddle"
    assert body["paddle"]["price_id"] == "pri_starter"
    assert body["paddle"]["client_token"] == "ptok_test"
    assert body["paddle"]["environment"] == "sandbox"
    assert body["paddle"]["custom_data"]["workspace_id"] == ws_id


def test_paddle_webhook_endpoint_verifies_and_applies(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_paddle_env(monkeypatch)
    _, ws = _seed(db_session, email="http-owner@x.com")
    event = _sub_event(ws, event_id="evt_http", status="active", plan="starter")
    body = json.dumps(event).encode()

    # Bad signature -> 400, nothing applied.
    bad = client.post(
        "/api/v1/billing/paddle/webhook", content=body, headers={"Paddle-Signature": "ts=1;h1=bad"}
    )
    assert bad.status_code == 400

    ok = client.post(
        "/api/v1/billing/paddle/webhook", content=body, headers={"Paddle-Signature": _sign(body)}
    )
    assert ok.status_code == 200
    sub = _sub(db_session, ws)
    assert sub is not None and sub.status == SubscriptionStatus.ACTIVE
