from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.connected_account import ConnectionStatus


class AutoresponderConnection(Base, TimestampMixin):
    """One row per (workspace, autoresponder provider).

    Autoresponders (Omnisend, GetResponse, …) authenticate with an API key
    rather than OAuth, so the secret lives in `encrypted_api_key` (Fernet, never
    decrypted into logs or responses) and provider-specific non-secret settings
    live in `config` (e.g. a base URL for the generic connector). Kept separate
    from `connected_accounts` because the auth model and entity shape (lists /
    audiences / contacts) differ from the ad-platform OAuth providers."""

    __tablename__ = "autoresponder_connections"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "provider", name="uq_autoresponder_connections_workspace_provider"
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
    display_name: Mapped[str | None] = mapped_column(String(255))
    provider_account_id: Mapped[str | None] = mapped_column(String(255))

    status: Mapped[ConnectionStatus] = mapped_column(
        Enum(ConnectionStatus, name="autoresponder_status"),
        nullable=False,
        default=ConnectionStatus.DISCONNECTED,
    )

    # Fernet-encrypted API key / auth token. Nullable because the generic
    # connector may target an unauthenticated webhook.
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    # Non-secret provider settings (base_url, store id, auth header name, …).
    config: Mapped[dict | None] = mapped_column(JSONB)

    connected_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    contact_syncs = relationship(
        "AutoresponderContactSync",
        back_populates="connection",
        cascade="all, delete-orphan",
        order_by="AutoresponderContactSync.created_at.desc()",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AutoresponderConnection workspace={self.workspace_id} "
            f"provider={self.provider} status={self.status}>"
        )
