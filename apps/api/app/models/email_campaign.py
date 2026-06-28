"""Email campaign records synced from an ESP (Omnisend today).

One row per (workspace, provider, external campaign id). Unlike `Campaign`
(paid ads), these are *email* sends pulled from the autoresponder/ESP with their
engagement + deliverability metrics, so the email-marketing agent can audit them.

Optionally linked to an ad `Campaign` via `ad_campaign_id` so a workspace can see
the email + paid sides of one initiative together (e.g. a Black Friday push)."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class EmailCampaign(Base, TimestampMixin):
    __tablename__ = "email_campaigns"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "provider",
            "external_id",
            name="uq_email_campaigns_workspace_provider_external",
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Source ESP and that ESP's campaign id.
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)

    name: Mapped[str | None] = mapped_column(String(512))
    subject: Mapped[str | None] = mapped_column(String(998))  # RFC 2822 max subject
    from_name: Mapped[str | None] = mapped_column(String(255))
    campaign_type: Mapped[str | None] = mapped_column(String(32))  # email / sms / push
    status: Mapped[str | None] = mapped_column(String(32))  # provider's raw status string
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    # --- Engagement + deliverability counts (absolute) ---
    sent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    opened_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clicked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bounced_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    complained_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unsubscribed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- Rates (0..1), computed at sync from the counts when sent_count > 0 ---
    open_rate: Mapped[float | None] = mapped_column(Float)
    click_rate: Mapped[float | None] = mapped_column(Float)
    bounce_rate: Mapped[float | None] = mapped_column(Float)
    complaint_rate: Mapped[float | None] = mapped_column(Float)
    unsubscribe_rate: Mapped[float | None] = mapped_column(Float)

    revenue_cents: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str | None] = mapped_column(String(8))

    # Optional link to the paid-ads campaign this email push belongs to.
    ad_campaign_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="SET NULL"),
        index=True,
    )

    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    ad_campaign = relationship("Campaign")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<EmailCampaign {self.provider}:{self.external_id} "
            f"sent={self.sent_count} open_rate={self.open_rate}>"
        )
