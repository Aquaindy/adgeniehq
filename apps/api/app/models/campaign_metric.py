from datetime import date as date_type
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CampaignMetric(Base, TimestampMixin):
    """Daily performance snapshot for a campaign (one row per campaign per day).

    Raw counters only — derived KPIs (CTR, CPC, CPA, ROAS, conversion rate) are
    computed on read so we never store stale/duplicated math. Populated by the
    insights sync from each ad platform; idempotent per (campaign, date)."""

    __tablename__ = "campaign_metrics"
    __table_args__ = (
        UniqueConstraint("campaign_id", "date", name="uq_campaign_metrics_campaign_date"),
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
    provider: Mapped[str | None] = mapped_column(String(64))
    date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)

    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spend_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    conversions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conversion_value_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<CampaignMetric campaign={self.campaign_id} date={self.date} "
            f"spend={self.spend_cents} clicks={self.clicks} conv={self.conversions}>"
        )
