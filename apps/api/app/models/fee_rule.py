from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class FeeRule(Base, TimestampMixin):
    """Admin-configurable platform fee schedule.

    A rule sets the fees AdVanta charges for ad activity for a given
    (provider, campaign_type). `NULL` on either dimension is a wildcard, so a
    single `(NULL, NULL)` rule acts as the global default and more specific
    rows override it. Resolution picks the most specific active match.

    Fees are platform/software fees on the customer's *own* ad activity —
    AdVanta never touches the ad spend itself, which is billed by the ad
    platform to the customer's own payment method.
    """

    __tablename__ = "fee_rules"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Matching dimensions. NULL = "any".
    provider: Mapped[str | None] = mapped_column(String(64), index=True)
    campaign_type: Mapped[str | None] = mapped_column(String(64), index=True)

    label: Mapped[str] = mapped_column(String(120), nullable=False)

    # One-time fee charged when a campaign is launched through AdVanta.
    listing_fee_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Flat fee accrued per billing period (month) while the campaign runs.
    run_flat_fee_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Percentage of ad spend, in basis points (800 = 8%).
    run_pct_basis_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<FeeRule provider={self.provider} type={self.campaign_type} "
            f"listing={self.listing_fee_cents} flat={self.run_flat_fee_cents} "
            f"pct_bps={self.run_pct_basis_points}>"
        )
