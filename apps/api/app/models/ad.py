from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
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


class AdStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class Ad(Base, TimestampMixin):
    __tablename__ = "ads"
    __table_args__ = (
        UniqueConstraint(
            "ad_group_id", "external_id", name="uq_ads_group_external"
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
    ad_group_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("ad_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    creative_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("creatives.id", ondelete="SET NULL"),
    )
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[AdStatus] = mapped_column(
        Enum(
            AdStatus,
            name="ad_status",
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
        default=AdStatus.ACTIVE,
    )
    landing_page_url: Mapped[str | None] = mapped_column(String(2048))
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)

    ad_group: Mapped["AdGroup"] = relationship(  # noqa: F821
        "AdGroup", back_populates="ads"
    )
    creative: Mapped["Creative | None"] = relationship(  # noqa: F821
        "Creative", back_populates="ads"
    )
