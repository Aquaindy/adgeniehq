from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class AbTestTarget(StrEnum):
    AD = "ad"
    LANDING_PAGE = "landing_page"


class AbTestStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"  # variants defined, awaiting launch
    LAUNCHED = "launched"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class BanditStrategy(StrEnum):
    """Traffic allocation strategy.

    `static` uses each variant's fixed `traffic_share`. `thompson_sampling`
    samples from a Beta posterior built from observed exposures + conversions
    on every assignment, dynamically funneling traffic to whichever variant
    looks most promising while still exploring others."""

    STATIC = "static"
    THOMPSON_SAMPLING = "thompson_sampling"


class AbTest(Base, TimestampMixin):
    """An A/B test definition.

    For target=ad, variants map to provider-launched campaigns/ads via the
    Phase A write pipeline. For target=landing_page, variants are URL/copy
    pairs whose outcome metrics are recorded manually or via analytics."""

    __tablename__ = "ab_tests"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hypothesis: Mapped[str | None] = mapped_column(Text)
    target: Mapped[AbTestTarget] = mapped_column(
        Enum(AbTestTarget, name="ab_test_target"),
        nullable=False,
    )
    objective: Mapped[str] = mapped_column(String(64), nullable=False)
    # e.g. "click_through_rate", "conversion_rate", "cpa", "roas"

    status: Mapped[AbTestStatus] = mapped_column(
        Enum(AbTestStatus, name="ab_test_status"),
        nullable=False,
        default=AbTestStatus.DRAFT,
        index=True,
    )

    provider: Mapped[str | None] = mapped_column(String(64))  # for ad tests
    external_account_id: Mapped[str | None] = mapped_column(String(128))

    bandit_strategy: Mapped[BanditStrategy] = mapped_column(
        Enum(BanditStrategy, name="ab_test_bandit_strategy"),
        nullable=False,
        default=BanditStrategy.STATIC,
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    winner_variant_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))

    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB)

    created_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    variants = relationship(
        "AbTestVariant",
        back_populates="test",
        cascade="all, delete-orphan",
        order_by="AbTestVariant.position",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AbTest id={self.id} name={self.name} status={self.status}>"


class AbTestVariant(Base, TimestampMixin):
    __tablename__ = "ab_test_variants"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ab_test_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("ab_tests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_control: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    traffic_share: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, default=0.5
    )

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Ad: {headline, body, cta, image_url, daily_budget_cents, targeting...}
    # Landing page: {url, copy, ...}

    external_id: Mapped[str | None] = mapped_column(String(128))  # provider's id once launched
    launched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Outcome metrics (recorded manually or via sync). Stored as JSONB so the
    # shape can evolve without a migration.
    metrics: Mapped[dict | None] = mapped_column(JSONB)

    test = relationship("AbTest", back_populates="variants")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AbTestVariant id={self.id} test={self.ab_test_id} name={self.name}>"
