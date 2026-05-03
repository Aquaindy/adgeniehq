from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class ConnectionStatus(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    ERROR = "error"


class ConnectedAccount(Base, TimestampMixin):
    """One row per (workspace, provider). Created on first /connect-url request
    so we can persist `connected_by`, `last_error`, etc., and updated through the
    OAuth callback + disconnect flow."""

    __tablename__ = "connected_accounts"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "provider", name="uq_connected_accounts_workspace_provider"
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_account_id: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(255))

    status: Mapped[ConnectionStatus] = mapped_column(
        Enum(ConnectionStatus, name="connected_account_status"),
        nullable=False,
        default=ConnectionStatus.DISCONNECTED,
    )
    scopes: Mapped[list[str] | None] = mapped_column(JSONB)

    connected_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    token = relationship(
        "OAuthToken",
        back_populates="connected_account",
        cascade="all, delete-orphan",
        uselist=False,
    )
    sync_logs = relationship(
        "SyncLog",
        back_populates="connected_account",
        cascade="all, delete-orphan",
        order_by="SyncLog.created_at.desc()",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ConnectedAccount workspace={self.workspace_id} provider={self.provider} status={self.status}>"
