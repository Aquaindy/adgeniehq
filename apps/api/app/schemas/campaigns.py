from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

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
