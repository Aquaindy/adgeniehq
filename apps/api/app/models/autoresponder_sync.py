from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class SyncDirection(StrEnum):
    PUSH = "push"  # AdVanta contacts -> autoresponder list
    PULL = "pull"  # autoresponder list -> AdVanta


class AutoresponderSyncStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class AutoresponderContactSync(Base, TimestampMixin):
    """Ledger of contact push/pull operations against an autoresponder list.

    Every external contact sync is recorded here (counts + outcome + a small
    summary) so the operation is traceable and surfaced in the workspace's
    autoresponder activity feed — in addition to the audit-log entry."""

    __tablename__ = "autoresponder_contact_syncs"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    connection_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("autoresponder_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    direction: Mapped[SyncDirection] = mapped_column(
        Enum(SyncDirection, name="autoresponder_sync_direction"), nullable=False
    )
    status: Mapped[AutoresponderSyncStatus] = mapped_column(
        Enum(AutoresponderSyncStatus, name="autoresponder_sync_status"),
        nullable=False,
        default=AutoresponderSyncStatus.RUNNING,
    )

    audience_external_id: Mapped[str | None] = mapped_column(String(255))
    audience_name: Mapped[str | None] = mapped_column(String(255))
    # Where the pushed contacts came from (manual, campaign_leads, audience_export…).
    source: Mapped[str | None] = mapped_column(String(64))

    requested_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    succeeded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    summary: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    connection = relationship("AutoresponderConnection", back_populates="contact_syncs")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AutoresponderContactSync {self.direction} status={self.status} "
            f"requested={self.requested_count} ok={self.succeeded_count}>"
        )
