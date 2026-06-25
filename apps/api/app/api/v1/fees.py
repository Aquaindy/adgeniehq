from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.db.session import get_db
from app.models.campaign import Campaign
from app.models.user import User
from app.models.workspace_member import WorkspaceMember
from app.schemas.fees import (
    AdminRevenueSummary,
    FeeInvoicePublic,
    FeeQuotePublic,
    FeeRulePublic,
    FeeRuleUpdateRequest,
    FeeRuleUpsertRequest,
    GenerateInvoiceRequest,
    PaymentProviderInfo,
    WorkspaceFeeSummary,
)
from app.security.dependencies import get_current_member, require_superuser
from app.services import fee_billing_service, fee_service

# Mounted at /workspaces (member-scoped fee preview + summary).
workspace_router = APIRouter()
# Mounted at /admin (superuser fee schedule + revenue).
admin_router = APIRouter()


class CampaignNotFoundError(AdVantaError):
    status_code = 404
    code = "campaign_not_found"


# ---------------------------------------------------------------------------
# Member-facing
# ---------------------------------------------------------------------------


@workspace_router.get(
    "/{workspace_id}/billing/fees", response_model=WorkspaceFeeSummary
)
def workspace_fees(
    workspace_id: UUID,
    period: str | None = Query(default=None, description="YYYY-MM; defaults to current."),
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> WorkspaceFeeSummary:
    return WorkspaceFeeSummary(
        **fee_service.workspace_fee_summary(db, workspace_id=workspace_id, period=period)
    )


@workspace_router.get(
    "/{workspace_id}/billing/invoices", response_model=list[FeeInvoicePublic]
)
def workspace_invoices(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[FeeInvoicePublic]:
    invoices = fee_billing_service.list_invoices(db, workspace_id=workspace_id)
    return [FeeInvoicePublic.model_validate(i) for i in invoices]


@workspace_router.get(
    "/{workspace_id}/billing/fee-quote", response_model=FeeQuotePublic
)
def prelaunch_fee_quote(
    workspace_id: UUID,
    provider: str | None = Query(default=None),
    campaign_type: str = Query(default="other"),
    daily_budget_cents: int = Query(default=0, ge=0),
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> FeeQuotePublic:
    """Quote fees for a hypothetical campaign before it's launched (for the
    New Campaign builder)."""
    quote = fee_service.quote_fees(
        db,
        provider=provider,
        campaign_type=campaign_type,
        daily_budget_cents=daily_budget_cents,
    )
    return FeeQuotePublic(
        provider=quote.provider,
        campaign_type=quote.campaign_type,
        listing_fee_cents=quote.listing_fee_cents,
        run_flat_fee_cents=quote.run_flat_fee_cents,
        run_pct_basis_points=quote.run_pct_basis_points,
        est_monthly_spend_cents=quote.est_monthly_spend_cents,
        est_monthly_run_fee_cents=quote.est_monthly_run_fee_cents,
        est_first_month_total_cents=quote.est_first_month_total_cents,
        source=quote.source,
    )


@workspace_router.get(
    "/{workspace_id}/campaigns/{campaign_id}/fee-quote",
    response_model=FeeQuotePublic,
)
def campaign_fee_quote(
    workspace_id: UUID,
    campaign_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> FeeQuotePublic:
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.workspace_id == workspace_id)
        .first()
    )
    if campaign is None:
        raise CampaignNotFoundError("Campaign not found in this workspace.")
    quote = fee_service.quote_for_campaign(db, campaign=campaign)
    return FeeQuotePublic(
        provider=quote.provider,
        campaign_type=quote.campaign_type,
        listing_fee_cents=quote.listing_fee_cents,
        run_flat_fee_cents=quote.run_flat_fee_cents,
        run_pct_basis_points=quote.run_pct_basis_points,
        est_monthly_spend_cents=quote.est_monthly_spend_cents,
        est_monthly_run_fee_cents=quote.est_monthly_run_fee_cents,
        est_first_month_total_cents=quote.est_first_month_total_cents,
        source=quote.source,
    )


# ---------------------------------------------------------------------------
# Admin (superuser) — fee schedule + revenue
# ---------------------------------------------------------------------------


@admin_router.get("/fee-rules", response_model=list[FeeRulePublic])
def list_fee_rules(
    _: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> list[FeeRulePublic]:
    return [FeeRulePublic.model_validate(r) for r in fee_service.list_rules(db)]


@admin_router.post("/fee-rules", response_model=FeeRulePublic, status_code=201)
def upsert_fee_rule(
    payload: FeeRuleUpsertRequest,
    user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> FeeRulePublic:
    rule = fee_service.upsert_rule(
        db,
        provider=payload.provider,
        campaign_type=payload.campaign_type,
        label=payload.label,
        listing_fee_cents=payload.listing_fee_cents,
        run_flat_fee_cents=payload.run_flat_fee_cents,
        run_pct_basis_points=payload.run_pct_basis_points,
        actor_user_id=user.id,
    )
    return FeeRulePublic.model_validate(rule)


@admin_router.patch("/fee-rules/{rule_id}", response_model=FeeRulePublic)
def update_fee_rule(
    rule_id: UUID,
    payload: FeeRuleUpdateRequest,
    _: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> FeeRulePublic:
    rule = fee_service.update_rule(
        db, rule_id=rule_id, updates=payload.model_dump(exclude_unset=True)
    )
    return FeeRulePublic.model_validate(rule)


@admin_router.delete("/fee-rules/{rule_id}", status_code=204)
def delete_fee_rule(
    rule_id: UUID,
    _: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> None:
    fee_service.delete_rule(db, rule_id=rule_id)


@admin_router.get("/fees/revenue", response_model=AdminRevenueSummary)
def fee_revenue(
    period: str | None = Query(default=None),
    _: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> AdminRevenueSummary:
    return AdminRevenueSummary(**fee_service.admin_revenue_summary(db, period=period))


# ---------------------------------------------------------------------------
# Admin (superuser) — collection layer (invoices + payment providers)
# ---------------------------------------------------------------------------


@admin_router.get("/fees/payment-providers", response_model=list[PaymentProviderInfo])
def list_payment_providers(
    _: User = Depends(require_superuser),
) -> list[PaymentProviderInfo]:
    return [PaymentProviderInfo(**p) for p in fee_billing_service.payment_provider_catalog()]


@admin_router.get("/fees/invoices", response_model=list[FeeInvoicePublic])
def list_fee_invoices(
    workspace_id: UUID | None = Query(default=None),
    _: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> list[FeeInvoicePublic]:
    invoices = fee_billing_service.list_invoices(db, workspace_id=workspace_id)
    return [FeeInvoicePublic.model_validate(i) for i in invoices]


@admin_router.post("/fees/invoices", response_model=FeeInvoicePublic, status_code=201)
def generate_fee_invoice(
    payload: GenerateInvoiceRequest,
    request: Request,
    user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> FeeInvoicePublic:
    invoice = fee_billing_service.generate_invoice(
        db,
        workspace_id=payload.workspace_id,
        provider_id=payload.provider,
        period=payload.period,
        actor_user_id=user.id,
        request=request,
    )
    return FeeInvoicePublic.model_validate(invoice)


@admin_router.post("/fees/invoices/{invoice_id}/mark-paid", response_model=FeeInvoicePublic)
def mark_fee_invoice_paid(
    invoice_id: UUID,
    request: Request,
    user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> FeeInvoicePublic:
    invoice = fee_billing_service.mark_invoice_paid(
        db, invoice_id=invoice_id, actor_user_id=user.id, request=request
    )
    return FeeInvoicePublic.model_validate(invoice)


@admin_router.post("/fees/invoices/{invoice_id}/void", response_model=FeeInvoicePublic)
def void_fee_invoice(
    invoice_id: UUID,
    request: Request,
    user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> FeeInvoicePublic:
    invoice = fee_billing_service.void_invoice(
        db, invoice_id=invoice_id, actor_user_id=user.id, request=request
    )
    return FeeInvoicePublic.model_validate(invoice)
