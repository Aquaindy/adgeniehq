from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class AdGroupStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"
    ARCHIVED = "archived"


class AdGroup(Base, TimestampMixin):
    __tablename__ = "ad_groups"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id", "external_id", name="uq_ad_groups_campaign_external"
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[AdGroupStatus] = mapped_column(
        Enum(
            AdGroupStatus,
            name="ad_group_status",
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
        default=AdGroupStatus.ACTIVE,
    )
    daily_budget_cents: Mapped[int | None] = mapped_column(BigInteger)
    targeting: Mapped[dict | None] = mapped_column(JSONB)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)

    ads: Mapped[list["Ad"]] = relationship(  # noqa: F821
        "Ad", back_populates="ad_group", cascade="all, delete-orphan"
    )
