"""Public schemas for the ad hierarchy: ad_groups, ads, creatives.

Read paths surface every column the operator needs to triage; the only write
path is `PATCH /creatives/{id}` for AI-generated creative copy because that's
the loop the Creative Strategy Agent feeds into. Ad/ad_group writes go via
provider sync only — agents never directly mutate the platform-synced rows.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.ad import AdStatus
from app.models.ad_group import AdGroupStatus
from app.models.creative import CreativeSource, CreativeType


class AdGroupPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    campaign_id: UUID
    external_id: str
    name: str
    status: AdGroupStatus
    daily_budget_cents: int | None
    targeting: dict[str, Any] | None
    last_synced_at: datetime
    created_at: datetime


class AdPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    campaign_id: UUID
    ad_group_id: UUID
    creative_id: UUID | None
    external_id: str
    name: str
    status: AdStatus
    landing_page_url: str | None
    last_synced_at: datetime
    created_at: datetime


class CreativePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    type: CreativeType
    source: CreativeSource
    title: str | None
    primary_text: str | None
    headline: str | None
    description: str | None
    cta: str | None
    image_url: str | None
    video_url: str | None
    metadata_json: dict[str, Any] | None = Field(default=None, alias="metadata_json")
    created_at: datetime
    updated_at: datetime


class CreativeUpdateRequest(BaseModel):
    """Fields an operator may rewrite on an AI-generated creative before it's
    attached to an ad. Only string-shaped copy fields — type/source/workspace
    are immutable from the API."""

    title: str | None = Field(default=None, max_length=512)
    primary_text: str | None = None
    headline: str | None = Field(default=None, max_length=512)
    description: str | None = None
    cta: str | None = Field(default=None, max_length=120)
    image_url: str | None = Field(default=None, max_length=2048)
    video_url: str | None = Field(default=None, max_length=2048)
