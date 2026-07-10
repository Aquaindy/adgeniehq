from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.suggested_copy import SuggestedCopyType


class SuggestedCopyPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    growth_dna_profile_id: UUID | None
    product_name: str
    copy_type: SuggestedCopyType
    section: str
    title: str
    body: str
    # Organic social only; null for keyword plans, ad copy, emails, etc.
    platform: str | None = None
    hashtags: list[str] | None = None
    source: str
    model_used: str | None
    created_at: datetime


class GenerateSuggestedCopiesRequest(BaseModel):
    """Optional overrides for a Growth Content Studio run.

    `product_name` is the Product/Service the run targets — when omitted the
    backend falls back to the onboarding business name. `profile_id` pins a
    specific Growth DNA Profile; omitted means the workspace's latest.
    """

    product_name: str | None = None
    profile_id: UUID | None = None
