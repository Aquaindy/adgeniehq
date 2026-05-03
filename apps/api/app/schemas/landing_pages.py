from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models.landing_page import LandingPageSource


class LandingPagePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    url: str
    label: str | None
    source: LandingPageSource
    is_primary: bool
    last_audited_at: datetime | None
    last_audit_summary: dict | None
    created_at: datetime


class LandingPageCreate(BaseModel):
    url: HttpUrl
    label: str | None = Field(default=None, max_length=255)
    is_primary: bool = False


class ImportFromOnboardingResponse(BaseModel):
    created: int
