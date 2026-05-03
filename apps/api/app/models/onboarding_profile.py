from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class OnboardingProfile(Base, TimestampMixin):
    """One business profile per workspace, filled progressively by the wizard."""

    __tablename__ = "onboarding_profiles"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Business basics
    business_name: Mapped[str | None] = mapped_column(String(255))
    website_url: Mapped[str | None] = mapped_column(String(2048))
    industry: Mapped[str | None] = mapped_column(String(120))

    # Audience + offer
    target_audience: Mapped[str | None] = mapped_column(Text)
    offer_description: Mapped[str | None] = mapped_column(Text)
    pain_points: Mapped[str | None] = mapped_column(Text)

    # Goals + budget
    primary_conversion_goal: Mapped[str | None] = mapped_column(String(500))
    # Budget is captured as a range (min/max) so we can score readiness
    # against the realistic floor and plan against the ceiling. Equal
    # values are valid — that's just "fixed budget = $X".
    monthly_ad_budget_min_usd: Mapped[int | None] = mapped_column(Integer)
    monthly_ad_budget_max_usd: Mapped[int | None] = mapped_column(Integer)
    geographic_target: Mapped[str | None] = mapped_column(Text)

    # Channels
    current_ad_platforms: Mapped[list[str] | None] = mapped_column(JSONB)
    landing_page_urls: Mapped[list[str] | None] = mapped_column(JSONB)
    analytics_status: Mapped[str | None] = mapped_column(String(32))
    competitors: Mapped[list[dict] | None] = mapped_column(JSONB)

    # Brand
    brand_voice: Mapped[str | None] = mapped_column(Text)

    # Wizard state
    step_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    growth_dna_profiles = relationship(
        "GrowthDnaProfile", back_populates="onboarding_profile", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<OnboardingProfile workspace={self.workspace_id} step={self.step_completed}>"
