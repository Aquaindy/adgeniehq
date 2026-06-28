from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EmailCampaignPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: str
    external_id: str
    name: str | None = None
    subject: str | None = None
    from_name: str | None = None
    campaign_type: str | None = None
    status: str | None = None
    sent_at: datetime | None = None

    sent_count: int
    opened_count: int
    clicked_count: int
    bounced_count: int
    complained_count: int
    unsubscribed_count: int

    open_rate: float | None = None
    click_rate: float | None = None
    bounce_rate: float | None = None
    complaint_rate: float | None = None
    unsubscribe_rate: float | None = None

    revenue_cents: int | None = None
    currency: str | None = None
    ad_campaign_id: UUID | None = None
    synced_at: datetime


class AssociateAdCampaignRequest(BaseModel):
    # Pass null to unlink.
    ad_campaign_id: UUID | None = None
