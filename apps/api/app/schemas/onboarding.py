from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class AnalyticsStatus(StrEnum):
    CONFIGURED = "configured"
    PARTIAL = "partial"
    NONE = "none"
    UNKNOWN = "unknown"


class AdPlatform(StrEnum):
    GOOGLE_ADS = "google_ads"
    META_ADS = "meta_ads"
    LINKEDIN_ADS = "linkedin_ads"
    TIKTOK_ADS = "tiktok_ads"
    MICROSOFT_ADS = "microsoft_ads"
    X_ADS = "x_ads"
    PINTEREST_ADS = "pinterest_ads"
    OTHER = "other"


class CompetitorEntry(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: HttpUrl | None = None


class OnboardingProfilePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    business_name: str | None
    website_url: str | None
    industry: str | None
    target_audience: str | None
    offer_description: str | None
    pain_points: str | None
    primary_conversion_goal: str | None
    monthly_ad_budget_min_usd: int | None
    monthly_ad_budget_max_usd: int | None
    geographic_target: str | None
    current_ad_platforms: list[str] | None
    landing_page_urls: list[str] | None
    analytics_status: AnalyticsStatus | None
    competitors: list[CompetitorEntry] | None
    brand_voice: str | None
    step_completed: int
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class OnboardingProfileUpdate(BaseModel):
    """Partial update — every field optional. Sent step-by-step by the wizard."""

    business_name: str | None = Field(default=None, min_length=1, max_length=255)
    website_url: HttpUrl | None = None
    industry: str | None = Field(default=None, min_length=1, max_length=120)

    target_audience: str | None = Field(default=None, min_length=1, max_length=2000)
    offer_description: str | None = Field(default=None, min_length=1, max_length=2000)
    pain_points: str | None = Field(default=None, min_length=1, max_length=2000)

    primary_conversion_goal: str | None = Field(default=None, min_length=1, max_length=500)
    monthly_ad_budget_min_usd: int | None = Field(default=None, ge=0, le=10_000_000)
    monthly_ad_budget_max_usd: int | None = Field(default=None, ge=0, le=10_000_000)
    geographic_target: str | None = Field(default=None, min_length=1, max_length=2000)

    current_ad_platforms: list[AdPlatform] | None = Field(default=None, max_length=20)
    landing_page_urls: list[HttpUrl] | None = Field(default=None, max_length=20)
    analytics_status: AnalyticsStatus | None = None
    competitors: list[CompetitorEntry] | None = Field(default=None, max_length=20)

    brand_voice: str | None = Field(default=None, min_length=1, max_length=2000)

    step_completed: int | None = Field(default=None, ge=0, le=10)
    mark_completed: bool | None = None

    @model_validator(mode="after")
    def _budget_range_ordering(self) -> "OnboardingProfileUpdate":
        if (
            self.monthly_ad_budget_min_usd is not None
            and self.monthly_ad_budget_max_usd is not None
            and self.monthly_ad_budget_min_usd > self.monthly_ad_budget_max_usd
        ):
            raise ValueError(
                "monthly_ad_budget_min_usd cannot exceed monthly_ad_budget_max_usd."
            )
        return self
