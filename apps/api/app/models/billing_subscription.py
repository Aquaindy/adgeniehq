from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class SubscriptionSource(StrEnum):
    """Where the current plan grant comes from. `appsumo` rows are lifetime
    deals with no Stripe customer and no recurring charge. `paddle` is the
    Merchant-of-Record processor for recurring plans (handles global tax/VAT)."""

    STRIPE = "stripe"
    APPSUMO = "appsumo"
    PADDLE = "paddle"


class SubscriptionStatus(StrEnum):
    """Stripe subscription status values plus our own `none` for free workspaces."""

    NONE = "none"
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    UNPAID = "unpaid"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"
    PAUSED = "paused"


class BillingSubscription(Base, TimestampMixin):
    """One row per (workspace, stripe subscription). Latest = current."""

    __tablename__ = "billing_subscriptions"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # Nullable: AppSumo lifetime subscriptions have no Stripe customer.
    billing_customer_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("billing_customers.id", ondelete="CASCADE"),
        nullable=True,
    )
    source: Mapped[SubscriptionSource] = mapped_column(
        Enum(SubscriptionSource, name="subscription_source"),
        nullable=False,
        default=SubscriptionSource.STRIPE,
    )

    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    stripe_price_id: Mapped[str | None] = mapped_column(String(64))

    # Provider-neutral identifiers used by non-Stripe processors (Paddle).
    # Kept separate from the stripe_* columns so AppSumo/Stripe rows are
    # untouched. `management_url` is the processor-hosted page where the
    # customer can update or cancel (Paddle returns these on the subscription).
    external_subscription_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    external_price_id: Mapped[str | None] = mapped_column(String(64))
    management_url: Mapped[str | None] = mapped_column(String(1024))

    plan_code: Mapped[str] = mapped_column(String(32), nullable=False, default="free")

    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status"),
        nullable=False,
        default=SubscriptionStatus.NONE,
    )
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trial_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    customer = relationship("BillingCustomer", back_populates="subscription")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BillingSubscription workspace={self.workspace_id} plan={self.plan_code} status={self.status}>"
