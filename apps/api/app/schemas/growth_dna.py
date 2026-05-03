from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CampaignSuggestion(BaseModel):
    platform: str
    objective: str
    budget_share_pct: int  # 0-100
    rationale: str


class GrowthPlanWeek(BaseModel):
    week: int
    focus: str
    deliverables: list[str]


class GrowthDnaPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    onboarding_profile_id: UUID

    business_summary: str
    icp_summary: str
    offer_positioning: str

    funnel_readiness_score: int
    paid_ads_readiness_score: int

    seo_geo_opportunity_summary: str
    website_conversion_risks: list[str]
    tracking_readiness: str

    recommended_first_campaigns: list[CampaignSuggestion]
    thirty_day_growth_plan: list[GrowthPlanWeek]

    engine_version: str

    created_at: datetime
