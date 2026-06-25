from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.campaign import CampaignStatus


class CampaignPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    connected_account_id: UUID | None
    provider: str
    external_id: str
    external_account_id: str | None
    name: str
    status: CampaignStatus
    objective: str | None
    daily_budget_cents: int | None
    lifetime_budget_cents: int | None
    currency: str | None
    start_date: date | None
    end_date: date | None
    last_synced_at: datetime
    created_at: datetime


class CampaignDetail(CampaignPublic):
    raw_payload: dict | None


class CampaignSummary(BaseModel):
    total: int
    active: int
    paused: int
    ended: int
    archived: int
    unknown: int
    per_provider: dict[str, int]
    active_without_budget: int
    stale_active: int
    last_synced_at: datetime | None


class ProviderSyncResultPublic(BaseModel):
    provider: str
    sync_log_id: UUID
    status: str
    fetched: int
    upserted: int
    error: str | None


class CampaignSyncResponse(BaseModel):
    started_at: datetime
    completed_at: datetime
    providers: list[ProviderSyncResultPublic]


# --- Campaign management actions (pause / resume / edit budget) -------------


class CampaignBudgetRequest(BaseModel):
    daily_budget_cents: int = Field(gt=0, description="New daily budget in cents.")


class CampaignLaunchRequest(BaseModel):
    provider: str = Field(description="meta_ads | google_ads | linkedin_ads")
    name: str = Field(min_length=1, max_length=255)
    campaign_type: str = Field(default="other", max_length=64)
    daily_budget_cents: int = Field(gt=0)


class CampaignLaunchResponse(BaseModel):
    status: str  # executed | failed | queued
    risk_level: str
    required_role: str
    message: str
    recommendation_id: UUID
    approval_id: UUID | None
    approval_status: str | None
    execution_id: UUID | None
    execution_status: str | None
    error_message: str | None
    campaign: CampaignPublic | None


class CampaignActionResponse(BaseModel):
    """Outcome of a user-initiated campaign action.

    `status` is one of: "executed" (applied on the platform now), "failed"
    (approved but the platform write errored), or "queued" (needs approval
    from a higher role before it runs)."""

    status: str
    action: str
    risk_level: str
    required_role: str
    message: str
    recommendation_id: UUID
    approval_id: UUID | None
    approval_status: str | None
    execution_id: UUID | None
    execution_status: str | None
    error_message: str | None
    campaign: CampaignPublic
