from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.backlink_prospect import ProspectStatus
from app.models.outreach_email import OutreachEmailStatus


class OutreachEmailPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    prospect_id: UUID
    subject: str
    body: str
    to_email: str
    status: OutreachEmailStatus
    source: str
    model_used: str | None
    scheduled_for: datetime | None
    sent_at: datetime | None
    replied_at: datetime | None
    error_message: str | None
    approved_by: UUID | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BacklinkProspectPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    domain: str
    page_url: str | None
    contact_name: str | None
    contact_email: str | None
    contact_role: str | None
    relevance_score: int | None
    domain_authority: int | None
    status: ProspectStatus
    notes: str | None
    source: str
    last_contacted_at: datetime | None
    won_at: datetime | None
    backlink_url: str | None
    created_at: datetime
    updated_at: datetime


class CreateProspectRequest(BaseModel):
    domain: str = Field(min_length=3, max_length=255)
    page_url: str | None = Field(default=None, max_length=1024)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_role: str | None = Field(default=None, max_length=120)
    relevance_score: int | None = Field(default=None, ge=0, le=100)
    domain_authority: int | None = Field(default=None, ge=0, le=100)
    notes: str | None = Field(default=None, max_length=4000)


class UpdateProspectRequest(BaseModel):
    page_url: str | None = Field(default=None, max_length=1024)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_role: str | None = Field(default=None, max_length=120)
    relevance_score: int | None = Field(default=None, ge=0, le=100)
    domain_authority: int | None = Field(default=None, ge=0, le=100)
    notes: str | None = Field(default=None, max_length=4000)
    status: ProspectStatus | None = None
    backlink_url: str | None = Field(default=None, max_length=1024)


class DraftOutreachRequest(BaseModel):
    angle: str | None = Field(default=None, max_length=2000)
    sender_name: str | None = Field(default=None, max_length=120)


class UpdateOutreachRequest(BaseModel):
    subject: str | None = Field(default=None, min_length=1, max_length=512)
    body: str | None = Field(default=None, min_length=1)


class MarkRepliedRequest(BaseModel):
    won: bool = False
    backlink_url: str | None = Field(default=None, max_length=1024)


class DiscoverProspectsRequest(BaseModel):
    competitor_url: str = Field(min_length=8, max_length=1024)
    max_pages: int = Field(default=15, ge=1, le=50)
    max_prospects: int = Field(default=50, ge=1, le=200)


class DiscoveryResultPublic(BaseModel):
    competitor_url: str
    pages_crawled: int
    prospects_added: int
    prospects_skipped_duplicate: int
    prospects: list[BacklinkProspectPublic] = []


class BulkProspectItem(BaseModel):
    domain: str = Field(min_length=3, max_length=255)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: str | None = Field(default=None, max_length=320)
    notes: str | None = Field(default=None, max_length=4000)


class BulkImportRequest(BaseModel):
    items: list[BulkProspectItem] = Field(min_length=1, max_length=500)


class BulkImportResultPublic(BaseModel):
    added: list[BacklinkProspectPublic] = []
    skipped_duplicate: list[str] = []
    skipped_invalid: list[dict] = []
