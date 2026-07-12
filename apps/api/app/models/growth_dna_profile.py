from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class GrowthDnaProfile(Base, TimestampMixin):
    """Generated insight bundle. Latest row per workspace is "current"."""

    __tablename__ = "growth_dna_profiles"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    onboarding_profile_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("onboarding_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional user-given name ("DemoGenius launch", "Q3 offer") so saved
    # profiles stay identifiable in the history list.
    label: Mapped[str | None] = mapped_column(String(160), nullable=True)

    # Frozen copy of the onboarding answers this profile was generated from.
    # Lets one workspace hold DNA for many products: restore a snapshot into
    # the (single) onboarding profile to edit/regenerate that product later.
    onboarding_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    business_summary: Mapped[str] = mapped_column(Text, nullable=False)
    icp_summary: Mapped[str] = mapped_column(Text, nullable=False)
    offer_positioning: Mapped[str] = mapped_column(Text, nullable=False)

    funnel_readiness_score: Mapped[int] = mapped_column(Integer, nullable=False)
    paid_ads_readiness_score: Mapped[int] = mapped_column(Integer, nullable=False)

    seo_geo_opportunity_summary: Mapped[str] = mapped_column(Text, nullable=False)
    website_conversion_risks: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    tracking_readiness: Mapped[str] = mapped_column(Text, nullable=False)

    recommended_first_campaigns: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    thirty_day_growth_plan: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)

    # Comprehensive cross-channel marketing strategy bundle (paid, organic
    # social, email/lifecycle, SEO, GEO, content, CRO, automation, referral,
    # measurement) plus content pillars, platform plan, and content calendar.
    marketing_strategy: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    engine_version: Mapped[str] = mapped_column(String(32), nullable=False)

    onboarding_profile = relationship("OnboardingProfile", back_populates="growth_dna_profiles")

    @property
    def has_onboarding_snapshot(self) -> bool:
        return bool(self.onboarding_snapshot)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<GrowthDnaProfile workspace={self.workspace_id} engine={self.engine_version}>"
