from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class OutreachEmailStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    SENT = "sent"
    FAILED = "failed"
    REPLIED = "replied"
    BOUNCED = "bounced"


class OutreachEmail(Base, TimestampMixin):
    """One outreach email — drafted, approved, sent — linked to a prospect."""

    __tablename__ = "outreach_emails"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    prospect_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("backlink_prospects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    to_email: Mapped[str] = mapped_column(String(320), nullable=False)

    status: Mapped[OutreachEmailStatus] = mapped_column(
        Enum(OutreachEmailStatus, name="outreach_email_status"),
        nullable=False,
        default=OutreachEmailStatus.DRAFT,
        index=True,
    )

    source: Mapped[str] = mapped_column(String(32), nullable=False, default="agent")
    model_used: Mapped[str | None] = mapped_column(String(64))

    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB)

    # Per-email Reply-To token. The send path stamps this onto the outgoing
    # message as `reply+<token>@<INBOUND_EMAIL_DOMAIN>`. When the recipient
    # replies, the inbound parse service routes the mail to our /inbound/email
    # webhook and we look up the email by this token.
    reply_token: Mapped[str | None] = mapped_column(String(64), unique=True)

    # Follow-up threading. A follow-up email points back at the original send
    # via `parent_email_id`; the original then has step_index=1 and the
    # follow-up step_index=2, etc. Used by the dashboard + auto-scheduler.
    parent_email_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("outreach_emails.id", ondelete="SET NULL"),
        index=True,
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    prospect = relationship("BacklinkProspect", back_populates="emails")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<OutreachEmail id={self.id} status={self.status}>"
