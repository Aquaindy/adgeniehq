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
from app.models.ad_group import AdGroupStatus, AdObjectSource
from app.models.creative import CreativeSource, CreativeType


class AdPublishResponse(BaseModel):
    """Result of publishing a draft ad group / ad to the platform — mirrors the
    campaign-launch response (one-click executes, else queues for approval)."""

    status: str  # "executed" | "failed" | "queued"
    object_type: str  # "ad_group" | "ad"
    risk_level: str
    required_role: str
    message: str
    recommendation_id: UUID
    approval_id: UUID | None = None
    approval_status: str | None = None
    execution_id: UUID | None = None
    execution_status: str | None = None
    external_id: str | None = None
    error_message: str | None = None


class AdGroupPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    campaign_id: UUID
    external_id: str | None
    source: AdObjectSource
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
    external_id: str | None
    source: AdObjectSource
    name: str
    status: AdStatus
    landing_page_url: str | None
    last_synced_at: datetime
    created_at: datetime


# --- Ad-structure builder (user-built drafts) ------------------------------


class AdGroupTargeting(BaseModel):
    """Flexible targeting captured in the builder; stored as JSON on the ad
    group. All fields optional — the operator fills what's relevant."""

    locations: list[str] = Field(default_factory=list)
    age_min: int | None = Field(default=None, ge=13, le=99)
    age_max: int | None = Field(default=None, ge=13, le=99)
    genders: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    optimization_goal: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=2000)


class AdGroupCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=512)
    daily_budget_cents: int | None = Field(default=None, ge=0)
    targeting: AdGroupTargeting = Field(default_factory=AdGroupTargeting)


class AdGroupUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=512)
    daily_budget_cents: int | None = Field(default=None, ge=0)
    targeting: AdGroupTargeting | None = None


class AdCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=512)
    landing_page_url: str | None = Field(default=None, max_length=2048)
    creative_id: UUID | None = None


class AdUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=512)
    landing_page_url: str | None = Field(default=None, max_length=2048)
    creative_id: UUID | None = None


class CreativeCreateRequest(BaseModel):
    type: CreativeType = CreativeType.SINGLE_IMAGE
    title: str | None = Field(default=None, max_length=512)
    headline: str | None = Field(default=None, max_length=512)
    primary_text: str | None = None
    description: str | None = None
    cta: str | None = Field(default=None, max_length=120)
    image_url: str | None = Field(default=None, max_length=2048)
    video_url: str | None = Field(default=None, max_length=2048)


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
