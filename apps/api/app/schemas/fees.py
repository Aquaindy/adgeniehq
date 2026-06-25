from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FeeRulePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: str | None
    campaign_type: str | None
    label: str
    listing_fee_cents: int
    run_flat_fee_cents: int
    run_pct_basis_points: int
    is_active: bool
    created_at: datetime


class FeeRuleUpsertRequest(BaseModel):
    provider: str | None = Field(default=None, max_length=64)
    campaign_type: str | None = Field(default=None, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    listing_fee_cents: int = Field(ge=0)
    run_flat_fee_cents: int = Field(ge=0)
    run_pct_basis_points: int = Field(ge=0, le=10_000, description="Basis points; 10000 = 100%.")


class FeeRuleUpdateRequest(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    listing_fee_cents: int | None = Field(default=None, ge=0)
    run_flat_fee_cents: int | None = Field(default=None, ge=0)
    run_pct_basis_points: int | None = Field(default=None, ge=0, le=10_000)
    is_active: bool | None = None


class FeeQuotePublic(BaseModel):
    provider: str | None
    campaign_type: str
    listing_fee_cents: int
    run_flat_fee_cents: int
    run_pct_basis_points: int
    est_monthly_spend_cents: int
    est_monthly_run_fee_cents: int
    est_first_month_total_cents: int
    source: str


class WorkspaceFeeSummary(BaseModel):
    period: str
    total_cents: int
    by_type: dict[str, int]
    currency: str


class AdminRevenueSummary(BaseModel):
    period: str
    period_total_cents: int
    all_time_total_cents: int
    by_status_cents: dict[str, int]
    accrual_count: int
    currency: str


# ---------------------------------------------------------------------------
# Collection layer — invoices + payment providers
# ---------------------------------------------------------------------------


class PaymentProviderInfo(BaseModel):
    provider: str
    display_name: str
    description: str
    configured: bool


class FeeInvoicePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    provider: str
    status: str
    amount_cents: int
    currency: str
    period: str | None
    accrual_count: int
    external_id: str | None
    hosted_url: str | None
    line_items: list | None
    error_message: str | None
    issued_at: datetime | None
    paid_at: datetime | None
    created_at: datetime


class GenerateInvoiceRequest(BaseModel):
    workspace_id: UUID
    provider: str = "manual"
    period: str | None = Field(default=None, description="YYYY-MM; omit to bill all accrued fees.")
