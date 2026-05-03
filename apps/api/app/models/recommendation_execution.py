from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class ExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REVERTED = "reverted"


class RecommendationExecution(Base, TimestampMixin):
    """One execution attempt against an external provider.

    Stores prior_state so a successful execution can be reverted (e.g. restore
    the original budget if a campaign budget change misbehaves)."""

    __tablename__ = "recommendation_executions"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recommendation_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("recommendations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    approval_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("approvals.id", ondelete="SET NULL"),
    )

    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus, name="execution_status"),
        nullable=False,
        default=ExecutionStatus.PENDING,
    )

    target_external_id: Mapped[str | None] = mapped_column(String(128))
    target_external_account_id: Mapped[str | None] = mapped_column(String(128))

    payload: Mapped[dict | None] = mapped_column(JSONB)
    prior_state: Mapped[dict | None] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)

    is_revert: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reverts_execution_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("recommendation_executions.id", ondelete="SET NULL"),
    )

    # Optional caller-supplied key. Same key + same workspace returns the
    # existing row without re-dispatching, so a network retry never doubles
    # a budget change or duplicates a campaign.
    idempotency_key: Mapped[str | None] = mapped_column(String(128))

    executed_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    recommendation = relationship("Recommendation", back_populates="executions")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<RecommendationExecution id={self.id} provider={self.provider} "
            f"action={self.action_type} status={self.status}>"
        )
