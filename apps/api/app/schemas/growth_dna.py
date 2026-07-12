from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CampaignSuggestion(BaseModel):
    platform: str
    objective: str
    budget_share_pct: int  # 0-100
    rationale: str


class GrowthPlanWeek(BaseModel):
    week: int
    focus: str
    deliverables: list[str]


# --- Comprehensive marketing strategy ---------------------------------------


class ChannelStrategy(BaseModel):
    channel: str
    category: str  # paid | owned | earned | foundation
    priority: str  # high | medium | low
    status: str  # ready | needs_setup | recommended
    cadence: str = ""
    summary: str = ""
    tactics: list[str] = Field(default_factory=list)
    kpis: list[str] = Field(default_factory=list)
    first_step: str = ""


class ContentPillar(BaseModel):
    name: str
    allocation_pct: int
    description: str = ""
    example_hooks: list[str] = Field(default_factory=list)


class PlatformPlan(BaseModel):
    platform: str
    cadence: str = ""
    focus: str = ""
    best_for: str = ""


class EmailFlow(BaseModel):
    name: str
    trigger: str = ""
    goal: str = ""


class EmailStrategy(BaseModel):
    summary: str = ""
    newsletter_cadence: str = ""
    flows: list[EmailFlow] = Field(default_factory=list)
    kpis: list[str] = Field(default_factory=list)


class CalendarEntry(BaseModel):
    day: int
    channel: str = ""
    format: str = ""
    pillar: str = ""
    hook: str = ""
    caption_direction: str = ""


class BudgetAllocation(BaseModel):
    channel: str
    pct: int
    rationale: str = ""


class MarketingOverview(BaseModel):
    model: str = "general"
    thesis: str = ""
    priorities: list[str] = Field(default_factory=list)
    budget_allocation: list[BudgetAllocation] = Field(default_factory=list)


class MarketingStrategy(BaseModel):
    overview: MarketingOverview = Field(default_factory=MarketingOverview)
    channels: list[ChannelStrategy] = Field(default_factory=list)
    content_pillars: list[ContentPillar] = Field(default_factory=list)
    platform_strategy: list[PlatformPlan] = Field(default_factory=list)
    email_strategy: EmailStrategy = Field(default_factory=EmailStrategy)
    content_calendar: list[CalendarEntry] = Field(default_factory=list)
    source: str = "deterministic"  # deterministic | ai
    model_used: str | None = None
    # AI-tailoring lifecycle: "pending" (running in background) | "enriched"
    # (AI applied) | "skipped" (no LLM / failed — deterministic kept) | None.
    enrichment: str | None = None


class GrowthDnaPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    onboarding_profile_id: UUID

    label: str | None = None
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
    marketing_strategy: MarketingStrategy = Field(default_factory=MarketingStrategy)

    engine_version: str

    created_at: datetime


class GrowthDnaSummary(BaseModel):
    """Lightweight row for the saved-profiles history list."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    label: str | None = None
    business_summary: str
    funnel_readiness_score: int
    paid_ads_readiness_score: int
    engine_version: str
    created_at: datetime


class GrowthDnaLabelUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=160)
