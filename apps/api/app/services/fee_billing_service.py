"""Fee collection layer.

Rolls a workspace's ACCRUED fee ledger into an invoice through a pluggable
PaymentProvider, flips those accruals to INVOICED, and records a FeeInvoice. The
ledger stays processor-agnostic — swapping Stripe/Paddle/manual touches only the
provider passed here. Re-running never double-bills: only ACCRUED rows are
picked up, and they leave the pool the moment they're invoiced."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.core.logging import get_logger
from app.models.audit_log import AuditActorType
from app.models.billing_customer import BillingCustomer
from app.models.fee_accrual import FeeAccrual, FeeAccrualStatus
from app.models.fee_invoice import FeeInvoice, FeeInvoiceStatus
from app.models.user import User
from app.models.workspace_member import WorkspaceMember
from app.payments.base import InvoiceCustomer, InvoiceLine, PaymentError
from app.payments.registry import get_payment_provider
from app.security.permissions import Role
from app.services import audit_service

log = get_logger(__name__)


class NothingToBillError(AdVantaError):
    status_code = 409
    code = "nothing_to_bill"


class FeeInvoiceNotFoundError(AdVantaError):
    status_code = 404
    code = "fee_invoice_not_found"


class PaymentProviderUnavailableError(AdVantaError):
    status_code = 503
    code = "payment_provider_unavailable"


class InvalidFeeInvoiceStateError(AdVantaError):
    status_code = 409
    code = "invalid_fee_invoice_state"


class FeeInvoiceNotManuallyPayableError(AdVantaError):
    status_code = 409
    code = "fee_invoice_not_manually_payable"


def _billing_identity(db: Session, *, workspace_id: UUID) -> InvoiceCustomer:
    customer = (
        db.query(BillingCustomer)
        .filter(BillingCustomer.workspace_id == workspace_id)
        .first()
    )
    email = customer.email if customer else None
    if email is None:
        owner = (
            db.query(User)
            .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
            .filter(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.role == Role.OWNER,
            )
            .first()
        )
        email = owner.email if owner else None
    return InvoiceCustomer(
        workspace_id=workspace_id,
        email=email,
        external_customer_id=customer.stripe_customer_id if customer else None,
    )


def _accrual_description(a: FeeAccrual) -> str:
    label = {
        "listing": "Campaign listing fee",
        "run_flat": "Monthly platform fee",
        "run_pct": "Spend-based platform fee",
    }.get(a.fee_type.value, "Platform fee")
    bits = [label]
    if a.provider:
        bits.append(a.provider)
    if a.period:
        bits.append(a.period)
    if (a.metadata_json or {}).get("campaign_name"):
        bits.append(a.metadata_json["campaign_name"])
    return " · ".join(bits)


def generate_invoice(
    db: Session,
    *,
    workspace_id: UUID,
    provider_id: str = "manual",
    period: str | None = None,
    actor_user_id: UUID | None = None,
    request: Request | None = None,
) -> FeeInvoice:
    provider = get_payment_provider(provider_id)
    if not provider.is_configured():
        raise PaymentProviderUnavailableError(
            f"{provider.display_name} is not configured on this server."
        )

    q = db.query(FeeAccrual).filter(
        FeeAccrual.workspace_id == workspace_id,
        FeeAccrual.status == FeeAccrualStatus.ACCRUED,
    )
    if period is not None:
        # Run fees match period exactly; listing fees (period NULL) match by the
        # month they were created.
        accruals = [
            a
            for a in q.all()
            if a.period == period
            or (
                a.period is None
                and f"{a.created_at.year:04d}-{a.created_at.month:02d}" == period
            )
        ]
    else:
        accruals = q.all()

    accruals = [a for a in accruals if a.amount_cents > 0]
    if not accruals:
        raise NothingToBillError(
            "No accrued fees to bill for this workspace"
            + (f" in {period}." if period else ".")
        )

    total = sum(a.amount_cents for a in accruals)
    line_items = [
        {
            "accrual_id": str(a.id),
            "description": _accrual_description(a),
            "amount_cents": a.amount_cents,
            "fee_type": a.fee_type.value,
        }
        for a in accruals
    ]

    invoice = FeeInvoice(
        workspace_id=workspace_id,
        provider=provider_id,
        status=FeeInvoiceStatus.DRAFT,
        amount_cents=total,
        currency="USD",
        period=period,
        accrual_count=len(accruals),
        line_items=line_items,
        created_by=actor_user_id,
    )
    db.add(invoice)
    db.flush()

    customer = _billing_identity(db, workspace_id=workspace_id)
    lines = [
        InvoiceLine(
            description=_accrual_description(a),
            amount_cents=a.amount_cents,
            accrual_id=a.id,
        )
        for a in accruals
    ]

    try:
        result = provider.create_invoice(
            customer=customer,
            currency="USD",
            lines=lines,
            period=period,
            metadata={"workspace_id": str(workspace_id), "fee_invoice_id": str(invoice.id)},
        )
    except (PaymentError, AdVantaError) as exc:
        invoice.status = FeeInvoiceStatus.FAILED
        invoice.error_message = str(exc)
        audit_service.log_event(
            db,
            workspace_id=workspace_id,
            actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
            actor_id=actor_user_id,
            action="fee_invoice.failed",
            resource_type="fee_invoice",
            resource_id=invoice.id,
            metadata={"provider": provider_id, "error": str(exc)},
            request=request,
        )
        db.commit()
        db.refresh(invoice)
        raise

    now = datetime.now(timezone.utc)
    invoice.status = FeeInvoiceStatus.OPEN
    invoice.external_id = result.external_id
    invoice.hosted_url = result.hosted_url
    invoice.issued_at = now

    for a in accruals:
        a.status = FeeAccrualStatus.INVOICED
        a.invoice_id = invoice.id

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        actor_id=actor_user_id,
        action="fee_invoice.created",
        resource_type="fee_invoice",
        resource_id=invoice.id,
        metadata={
            "provider": provider_id,
            "amount_cents": total,
            "accrual_count": len(accruals),
            "external_id": result.external_id,
        },
        request=request,
    )
    db.commit()
    db.refresh(invoice)
    return invoice


def mark_invoice_paid(
    db: Session,
    *,
    invoice_id: UUID,
    actor_user_id: UUID | None = None,
    request: Request | None = None,
) -> FeeInvoice:
    """Manually record a fee invoice as collected.

    This is restricted to ``manual`` invoices: a human who collected payment
    out-of-band (bank transfer, etc.) records it here. For processor-backed
    invoices (Stripe/Paddle/PayPal) "paid" must come from a *verified webhook*
    via ``confirm_invoice_payment`` — staff cannot record unverified revenue as
    collected. Idempotent (a second call on a PAID invoice is a no-op) and only
    an OPEN invoice may transition to PAID."""
    invoice = db.query(FeeInvoice).filter(FeeInvoice.id == invoice_id).first()
    if invoice is None:
        raise FeeInvoiceNotFoundError("Invoice not found.")

    if invoice.provider != "manual":
        raise FeeInvoiceNotManuallyPayableError(
            f"Invoice is billed via '{invoice.provider}'. Payment is confirmed "
            "automatically by the processor's webhook, not marked by hand."
        )
    if invoice.status == FeeInvoiceStatus.PAID:
        return invoice  # idempotent no-op
    if invoice.status != FeeInvoiceStatus.OPEN:
        raise InvalidFeeInvoiceStateError(
            f"Cannot mark a '{invoice.status.value}' invoice paid; only OPEN invoices can be paid."
        )

    return _record_payment(
        db,
        invoice=invoice,
        actor_user_id=actor_user_id,
        actor_type=(AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM),
        action="fee_invoice.marked_paid",
        extra_metadata={"confirmation": "manual"},
        request=request,
    )


def confirm_invoice_payment(
    db: Session,
    *,
    invoice: FeeInvoice,
    confirmation_ref: str | None = None,
    request: Request | None = None,
) -> FeeInvoice:
    """Record a processor-backed invoice as PAID from a *verified* webhook
    (Stripe/Paddle/PayPal `transaction.completed` / `invoice.paid`). Internal —
    never exposed to staff. Idempotent; only OPEN invoices transition to PAID,
    and an unexpected state is logged and left unchanged rather than corrupted."""
    if invoice.status == FeeInvoiceStatus.PAID:
        return invoice  # idempotent — webhook re-delivery
    if invoice.status != FeeInvoiceStatus.OPEN:
        log.warning(
            "fee_invoice.payment_confirm_ignored",
            invoice_id=str(invoice.id),
            status=invoice.status.value,
        )
        return invoice

    return _record_payment(
        db,
        invoice=invoice,
        actor_user_id=None,
        actor_type=AuditActorType.SYSTEM,
        action="fee_invoice.payment_confirmed",
        extra_metadata={
            "confirmation": "webhook",
            "provider": invoice.provider,
            "confirmation_ref": confirmation_ref,
        },
        request=request,
    )


def _record_payment(
    db: Session,
    *,
    invoice: FeeInvoice,
    actor_user_id: UUID | None,
    actor_type: AuditActorType,
    action: str,
    extra_metadata: dict,
    request: Request | None,
) -> FeeInvoice:
    invoice.status = FeeInvoiceStatus.PAID
    invoice.paid_at = datetime.now(timezone.utc)
    audit_service.log_event(
        db,
        workspace_id=invoice.workspace_id,
        actor_type=actor_type,
        actor_id=actor_user_id,
        action=action,
        resource_type="fee_invoice",
        resource_id=invoice.id,
        metadata={"amount_cents": invoice.amount_cents, **extra_metadata},
        request=request,
    )
    db.commit()
    db.refresh(invoice)
    return invoice


def void_invoice(
    db: Session,
    *,
    invoice_id: UUID,
    actor_user_id: UUID | None = None,
    request: Request | None = None,
) -> FeeInvoice:
    """Cancel an invoice and release its accruals back to ACCRUED so they can be
    re-billed (e.g. on a different processor)."""
    invoice = db.query(FeeInvoice).filter(FeeInvoice.id == invoice_id).first()
    if invoice is None:
        raise FeeInvoiceNotFoundError("Invoice not found.")
    if invoice.status == FeeInvoiceStatus.VOID:
        return invoice  # idempotent no-op
    if invoice.status == FeeInvoiceStatus.PAID:
        # Voiding a collected invoice would release its accruals back to ACCRUED
        # and bill the customer a second time. Refuse — paid is terminal.
        raise InvalidFeeInvoiceStateError(
            "Cannot void a PAID invoice; payment has already been collected."
        )
    invoice.status = FeeInvoiceStatus.VOID
    released = (
        db.query(FeeAccrual)
        .filter(
            FeeAccrual.invoice_id == invoice.id,
            FeeAccrual.status == FeeAccrualStatus.INVOICED,
        )
        .all()
    )
    for a in released:
        a.status = FeeAccrualStatus.ACCRUED
        a.invoice_id = None
    audit_service.log_event(
        db,
        workspace_id=invoice.workspace_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        actor_id=actor_user_id,
        action="fee_invoice.voided",
        resource_type="fee_invoice",
        resource_id=invoice.id,
        metadata={"released_accruals": len(released)},
        request=request,
    )
    db.commit()
    db.refresh(invoice)
    return invoice


def list_invoices(
    db: Session, *, workspace_id: UUID | None = None, limit: int = 100
) -> list[FeeInvoice]:
    q = db.query(FeeInvoice)
    if workspace_id is not None:
        q = q.filter(FeeInvoice.workspace_id == workspace_id)
    return q.order_by(FeeInvoice.created_at.desc()).limit(limit).all()


def payment_provider_catalog() -> list[dict]:
    from app.payments.registry import list_payment_providers

    return [p.catalog_entry() for p in list_payment_providers()]
