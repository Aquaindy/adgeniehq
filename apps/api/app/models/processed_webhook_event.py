from uuid import UUID, uuid4

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ProcessedWebhookEvent(Base, TimestampMixin):
    """Idempotency ledger for inbound payment-processor webhooks.

    A processor (Paddle/Stripe/PayPal) re-delivers an event on any non-2xx and
    can deliver out of order. Before applying an event we insert its
    ``(provider, event_id)`` here inside the same transaction; the unique
    constraint makes a duplicate a guaranteed no-op (the handler short-circuits
    on conflict). One row per distinct event the system has durably applied."""

    __tablename__ = "processed_webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_processed_webhook_provider_event"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(64))
