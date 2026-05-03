from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Date,
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


class CampaignStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"
    ARCHIVED = "archived"
    UNKNOWN = "unknown"


class Campaign(Base, TimestampMixin):
    """A normalized campaign record. One row per provider-campaign pairing in a workspace."""

    __tablename__ = "campaigns"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "provider", "external_id",
            name="uq_campaigns_workspace_provider_external",
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)

    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connected_account_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("connected_accounts.id", ondelete="SET NULL"),
        index=True,
    )

    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    external_account_id: Mapped[str | None] = mapped_column(String(128))

    name: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus, name="campaign_status"),
        nullable=False,
        default=CampaignStatus.UNKNOWN,
    )
    objective: Mapped[str | None] = mapped_column(String(120))

    daily_budget_cents: Mapped[int | None] = mapped_column(BigInteger)
    lifetime_budget_cents: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str | None] = mapped_column(String(8))

    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)

    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)

    connected_account = relationship("ConnectedAccount")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Campaign {self.provider}:{self.external_id} status={self.status}>"
