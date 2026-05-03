from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class UsageEventType(StrEnum):
    AGENT_RUN = "agent_run"
    LANDING_PAGE_AUDIT = "landing_page_audit"
    REPORT_GENERATED = "report_generated"
    # Phase A — every successful provider write counts (each one can spend
    # money or modify a live campaign).
    OUTBOUND_WRITE = "outbound_write"
    # Phase B
    CONTENT_DRAFT = "content_draft"
    # Phase C
    OUTREACH_EMAIL_SENT = "outreach_email_sent"
    # Phase D
    AB_TEST_CREATED = "ab_test_created"
    # LLM token meter — quantity is set to (prompt_tokens + completion_tokens)
    # rather than 1 so plan caps can throttle by total tokens.
    LLM_CALL = "llm_call"


class UsageEvent(Base, TimestampMixin):
    """Append-only meter for plan-limit enforcement."""

    __tablename__ = "usage_events"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    event_type: Mapped[UsageEventType] = mapped_column(
        Enum(
            UsageEventType,
            name="usage_event_type",
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB)
