"""Traffic metrics — per (campaign, source, day) results (Phase 6).

Operator-logged or imported performance for a traffic source/campaign. This is
the data backbone for source/campaign comparison, the traffic quality score, and
profitability analysis. Derived ratios (CPC, CPL, ROAS, EPC, conversion rate)
are computed in the service, never stored, so they always reflect the raw inputs.

Every number here is real — entered by the operator or imported from a connected
source. The analytics layer also folds in Phase 4 solo-ad orders so paid-email
results show up without re-entry.
"""

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Date, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class TrafficMetric(Base, TimestampMixin):
    __tablename__ = "traffic_metrics"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    traffic_campaign_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("traffic_campaigns.id", ondelete="SET NULL"),
        index=True,
    )

    source_slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    medium: Mapped[str | None] = mapped_column(String(64))
    date: Mapped[date | None] = mapped_column(Date, index=True)

    visitors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    leads: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sales: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revenue_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str | None] = mapped_column(String(8))

    bounce_rate: Mapped[float | None] = mapped_column(Float)  # 0..1
    avg_session_duration_sec: Mapped[int | None] = mapped_column(Integer)
    email_opens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    email_clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unsubscribes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spam_complaints: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    refunds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TrafficMetric {self.source_slug} {self.date} cost={self.cost_cents}>"
