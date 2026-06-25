"""Fee collection layer: generate invoices through pluggable payment providers,
flip accruals to invoiced (no double-billing), mark paid / void, provider gating."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.fee_accrual import FeeAccrual, FeeAccrualStatus, FeeType
from app.models.fee_invoice import FeeInvoice, FeeInvoiceStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role


def _seed_member(
    db: Session, *, email: str, role: Role = Role.OWNER, is_superuser: bool = False
) -> tuple[User, Workspace]:
    user = User(
        email=email, hashed_password=hash_password("correct-horse-9"),
        is_active=True, is_superuser=is_superuser,
    )
    db.add(user)
    db.flush()
    ws = Workspace(name="Test", slug=f"test-{email.split('@')[0]}")
    db.add(ws)
    db.flush()
    db.add(
        WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=role, status=MemberStatus.ACTIVE)
    )
    db.commit()
    return user, ws


def _login(client: TestClient, email: str) -> None:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-9"})
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})


def _accrual(db: Session, *, ws: Workspace, amount: int = 2500, fee_type=FeeType.LISTING) -> FeeAccrual:
    a = FeeAccrual(
        workspace_id=ws.id, fee_type=fee_type, provider="meta_ads", campaign_type="leads",
        period=None if fee_type == FeeType.LISTING else "2026-06", amount_cents=amount,
        status=FeeAccrualStatus.ACCRUED, metadata_json={"campaign_name": "Summer Sale"},
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _superuser(client: TestClient, db: Session) -> Workspace:
    """Seed a workspace + owner (billing identity) and a superuser admin; log in
    as the superuser. Returns the target workspace."""
    _, ws = _seed_member(db, email="owner@example.com", role=Role.OWNER)
    _seed_member(db, email="root@example.com", is_superuser=True)
    _login(client, "root@example.com")
    return ws


# ---------------------------------------------------------------------------
# Generate / no-double-bill
# ---------------------------------------------------------------------------


def test_generate_manual_invoice_bills_accruals(client: TestClient, db_session: Session) -> None:
    ws = _superuser(client, db_session)
    _accrual(db_session, ws=ws, amount=2500)
    _accrual(db_session, ws=ws, amount=4000, fee_type=FeeType.RUN_PCT)

    resp = client.post(
        "/api/v1/admin/fees/invoices",
        json={"workspace_id": str(ws.id), "provider": "manual"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "open"
    assert body["amount_cents"] == 6500
    assert body["accrual_count"] == 2
    assert body["provider"] == "manual"

    # Accruals flipped to invoiced + linked.
    db_session.expire_all()
    rows = db_session.query(FeeAccrual).filter(FeeAccrual.workspace_id == ws.id).all()
    assert all(r.status == FeeAccrualStatus.INVOICED for r in rows)
    assert all(str(r.invoice_id) == body["id"] for r in rows)


def test_no_double_bill(client: TestClient, db_session: Session) -> None:
    ws = _superuser(client, db_session)
    _accrual(db_session, ws=ws, amount=2500)
    first = client.post(
        "/api/v1/admin/fees/invoices", json={"workspace_id": str(ws.id), "provider": "manual"}
    )
    assert first.status_code == 201
    # Second run: nothing left in ACCRUED.
    second = client.post(
        "/api/v1/admin/fees/invoices", json={"workspace_id": str(ws.id), "provider": "manual"}
    )
    assert second.status_code == 409


def test_nothing_to_bill(client: TestClient, db_session: Session) -> None:
    ws = _superuser(client, db_session)
    resp = client.post(
        "/api/v1/admin/fees/invoices", json={"workspace_id": str(ws.id), "provider": "manual"}
    )
    assert resp.status_code == 409


def test_period_filter(client: TestClient, db_session: Session) -> None:
    ws = _superuser(client, db_session)
    _accrual(db_session, ws=ws, amount=4000, fee_type=FeeType.RUN_PCT)  # period 2026-06
    # Bill a different period → nothing.
    resp = client.post(
        "/api/v1/admin/fees/invoices",
        json={"workspace_id": str(ws.id), "provider": "manual", "period": "2026-05"},
    )
    assert resp.status_code == 409
    # Correct period bills it.
    ok = client.post(
        "/api/v1/admin/fees/invoices",
        json={"workspace_id": str(ws.id), "provider": "manual", "period": "2026-06"},
    )
    assert ok.status_code == 201
    assert ok.json()["amount_cents"] == 4000


# ---------------------------------------------------------------------------
# Mark paid / void
# ---------------------------------------------------------------------------


def test_mark_paid(client: TestClient, db_session: Session) -> None:
    ws = _superuser(client, db_session)
    _accrual(db_session, ws=ws, amount=2500)
    inv = client.post(
        "/api/v1/admin/fees/invoices", json={"workspace_id": str(ws.id), "provider": "manual"}
    ).json()
    paid = client.post(f"/api/v1/admin/fees/invoices/{inv['id']}/mark-paid")
    assert paid.status_code == 200
    assert paid.json()["status"] == "paid"
    assert paid.json()["paid_at"] is not None


def test_void_releases_accruals(client: TestClient, db_session: Session) -> None:
    ws = _superuser(client, db_session)
    a = _accrual(db_session, ws=ws, amount=2500)
    inv = client.post(
        "/api/v1/admin/fees/invoices", json={"workspace_id": str(ws.id), "provider": "manual"}
    ).json()
    voided = client.post(f"/api/v1/admin/fees/invoices/{inv['id']}/void")
    assert voided.status_code == 200
    assert voided.json()["status"] == "void"
    db_session.expire_all()
    refreshed = db_session.get(FeeAccrual, a.id)
    assert refreshed.status == FeeAccrualStatus.ACCRUED  # released for re-billing
    assert refreshed.invoice_id is None


# ---------------------------------------------------------------------------
# Provider gating + catalog
# ---------------------------------------------------------------------------


def test_stripe_provider_unconfigured_503(client: TestClient, db_session: Session) -> None:
    ws = _superuser(client, db_session)
    _accrual(db_session, ws=ws, amount=2500)
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("STRIPE_SECRET_KEY", None)
        resp = client.post(
            "/api/v1/admin/fees/invoices",
            json={"workspace_id": str(ws.id), "provider": "stripe"},
        )
    assert resp.status_code == 503


def test_paddle_provider_unconfigured_503(client: TestClient, db_session: Session) -> None:
    ws = _superuser(client, db_session)
    _accrual(db_session, ws=ws, amount=2500)
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("PADDLE_API_KEY", None)
        resp = client.post(
            "/api/v1/admin/fees/invoices",
            json={"workspace_id": str(ws.id), "provider": "paddle"},
        )
    assert resp.status_code == 503


def test_payment_provider_catalog(client: TestClient, db_session: Session) -> None:
    _superuser(client, db_session)
    resp = client.get("/api/v1/admin/fees/payment-providers")
    assert resp.status_code == 200
    providers = {p["provider"]: p for p in resp.json()}
    assert providers["manual"]["configured"] is True
    assert "stripe" in providers and "paddle" in providers


def test_invoicing_requires_superuser(client: TestClient, db_session: Session) -> None:
    _, ws = _seed_member(db_session, email="plain@example.com", role=Role.OWNER)
    _login(client, "plain@example.com")
    resp = client.post(
        "/api/v1/admin/fees/invoices", json={"workspace_id": str(ws.id), "provider": "manual"}
    )
    assert resp.status_code == 403


def test_paypal_provider_unconfigured_503(client: TestClient, db_session: Session) -> None:
    ws = _superuser(client, db_session)
    _accrual(db_session, ws=ws, amount=2500)
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("PAYPAL_CLIENT_ID", None)
        os.environ.pop("PAYPAL_CLIENT_SECRET", None)
        resp = client.post(
            "/api/v1/admin/fees/invoices",
            json={"workspace_id": str(ws.id), "provider": "paypal"},
        )
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Payment-confirmation gating (launch blocker 4)
# ---------------------------------------------------------------------------


def _invoice(
    db: Session, *, ws: Workspace, provider: str, status: FeeInvoiceStatus
) -> FeeInvoice:
    inv = FeeInvoice(
        workspace_id=ws.id, provider=provider, status=status,
        amount_cents=2500, currency="USD", accrual_count=1,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


def test_mark_paid_rejects_non_manual_invoice(db_session: Session) -> None:
    """Staff cannot mark a processor-backed (stripe/paddle) invoice paid — that
    must come from a verified webhook, not an unverified button click."""
    from app.services import fee_billing_service

    _, ws = _seed_member(db_session, email="o1@example.com")
    inv = _invoice(db_session, ws=ws, provider="stripe", status=FeeInvoiceStatus.OPEN)
    with pytest.raises(fee_billing_service.FeeInvoiceNotManuallyPayableError):
        fee_billing_service.mark_invoice_paid(db_session, invoice_id=inv.id)
    db_session.refresh(inv)
    assert inv.status == FeeInvoiceStatus.OPEN  # unchanged


def test_mark_paid_is_idempotent(db_session: Session) -> None:
    from app.services import fee_billing_service

    _, ws = _seed_member(db_session, email="o2@example.com")
    inv = _invoice(db_session, ws=ws, provider="manual", status=FeeInvoiceStatus.OPEN)
    fee_billing_service.mark_invoice_paid(db_session, invoice_id=inv.id)
    # Second call is a no-op, not an error or a double-stamp.
    again = fee_billing_service.mark_invoice_paid(db_session, invoice_id=inv.id)
    assert again.status == FeeInvoiceStatus.PAID


def test_mark_paid_rejects_non_open_invoice(db_session: Session) -> None:
    from app.services import fee_billing_service

    _, ws = _seed_member(db_session, email="o3@example.com")
    inv = _invoice(db_session, ws=ws, provider="manual", status=FeeInvoiceStatus.VOID)
    with pytest.raises(fee_billing_service.InvalidFeeInvoiceStateError):
        fee_billing_service.mark_invoice_paid(db_session, invoice_id=inv.id)


def test_void_rejects_paid_invoice(db_session: Session) -> None:
    """Voiding a PAID invoice would resurrect its accruals and re-bill — refuse."""
    from app.services import fee_billing_service

    _, ws = _seed_member(db_session, email="o4@example.com")
    inv = _invoice(db_session, ws=ws, provider="manual", status=FeeInvoiceStatus.PAID)
    with pytest.raises(fee_billing_service.InvalidFeeInvoiceStateError):
        fee_billing_service.void_invoice(db_session, invoice_id=inv.id)
    db_session.refresh(inv)
    assert inv.status == FeeInvoiceStatus.PAID  # unchanged


def test_confirm_invoice_payment_marks_processor_invoice_paid(db_session: Session) -> None:
    """The webhook-driven path CAN mark a processor invoice paid (idempotently)."""
    from app.services import fee_billing_service

    _, ws = _seed_member(db_session, email="o5@example.com")
    inv = _invoice(db_session, ws=ws, provider="paddle", status=FeeInvoiceStatus.OPEN)
    confirmed = fee_billing_service.confirm_invoice_payment(
        db_session, invoice=inv, confirmation_ref="txn_123"
    )
    assert confirmed.status == FeeInvoiceStatus.PAID
    assert confirmed.paid_at is not None
    # Idempotent on webhook re-delivery.
    again = fee_billing_service.confirm_invoice_payment(db_session, invoice=inv)
    assert again.status == FeeInvoiceStatus.PAID


# ---------------------------------------------------------------------------
# Real provider implementations (mocked HTTP)
# ---------------------------------------------------------------------------


class _Resp:
    def __init__(self, body, *, status_code=200, text=""):
        self.status_code = status_code
        self._b = body
        self.text = text
        self.content = b"{}"

    def json(self):
        return self._b


def test_paddle_create_invoice_builds_transaction() -> None:
    import httpx

    from app.payments.base import InvoiceCustomer, InvoiceLine
    from app.payments.paddle import PaddlePaymentProvider

    captured: dict = {}

    def _post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return _Resp({"data": {"id": "txn_1", "status": "draft", "checkout": {"url": "https://paddle/pay"}}})

    from uuid import uuid4

    customer = InvoiceCustomer(workspace_id=uuid4(), email="o@example.com", external_customer_id="ctm_1")
    lines = [InvoiceLine(description="Listing fee", amount_cents=2500, accrual_id=uuid4())]
    with patch.dict(os.environ, {"PADDLE_API_KEY": "pk"}, clear=False):
        with patch.object(httpx, "post", side_effect=_post):
            result = PaddlePaymentProvider.create_invoice(
                customer=customer, currency="USD", lines=lines, period=None, metadata={"x": "y"}
            )
    assert result.external_id == "txn_1"
    assert result.hosted_url == "https://paddle/pay"
    item = captured["json"]["items"][0]
    assert item["price"]["unit_price"]["amount"] == "2500"
    assert captured["json"]["customer_id"] == "ctm_1"


def test_paypal_create_invoice_sends_and_returns_link() -> None:
    import httpx

    from app.payments.base import InvoiceCustomer, InvoiceLine
    from app.payments.paypal import PayPalPaymentProvider

    def _post(url, **kwargs):
        if url.endswith("/v1/oauth2/token"):
            return _Resp({"access_token": "tok"})
        if url.endswith("/v2/invoicing/invoices"):
            return _Resp({"href": "https://api-m.paypal.com/v2/invoicing/invoices/INV2-AAAA"}, status_code=201)
        if url.endswith("/send"):
            return _Resp({"href": "https://paypal/payerview"})
        return _Resp({}, status_code=404)

    from uuid import uuid4

    customer = InvoiceCustomer(workspace_id=uuid4(), email="o@example.com")
    lines = [InvoiceLine(description="Run fee", amount_cents=4000, accrual_id=uuid4())]
    with patch.dict(os.environ, {"PAYPAL_CLIENT_ID": "c", "PAYPAL_CLIENT_SECRET": "s"}, clear=False):
        with patch.object(httpx, "post", side_effect=_post):
            result = PayPalPaymentProvider.create_invoice(
                customer=customer, currency="USD", lines=lines, period=None, metadata={}
            )
    assert result.external_id == "INV2-AAAA"
    assert result.hosted_url == "https://paypal/payerview"


def test_generate_invoice_via_paddle_end_to_end(client: TestClient, db_session: Session) -> None:
    import httpx

    ws = _superuser(client, db_session)
    _accrual(db_session, ws=ws, amount=2500)

    def _post(url, **kwargs):
        if url.endswith("/customers"):
            return _Resp({"data": {"id": "ctm_x"}})
        if url.endswith("/transactions"):
            return _Resp({"data": {"id": "txn_9", "status": "draft", "checkout": {"url": "https://paddle/pay9"}}})
        return _Resp({}, status_code=404)

    with patch.dict(os.environ, {"PADDLE_API_KEY": "pk"}, clear=False):
        with patch.object(httpx, "post", side_effect=_post):
            resp = client.post(
                "/api/v1/admin/fees/invoices",
                json={"workspace_id": str(ws.id), "provider": "paddle"},
            )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "open"
    assert body["provider"] == "paddle"
    assert body["external_id"] == "txn_9"
    assert body["hosted_url"] == "https://paddle/pay9"

    db_session.expire_all()
    rows = db_session.query(FeeAccrual).filter(FeeAccrual.workspace_id == ws.id).all()
    assert all(r.status == FeeAccrualStatus.INVOICED for r in rows)


def test_member_can_list_workspace_invoices(client: TestClient, db_session: Session) -> None:
    ws = _superuser(client, db_session)
    _accrual(db_session, ws=ws, amount=2500)
    client.post(
        "/api/v1/admin/fees/invoices", json={"workspace_id": str(ws.id), "provider": "manual"}
    )
    # The workspace owner can see their invoices.
    _login(client, "owner@example.com")
    resp = client.get(f"/api/v1/workspaces/{ws.id}/billing/invoices")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["amount_cents"] == 2500
