"""Workspace-scoped third-party provider credentials.

Stores BYOK ("bring your own key") secrets for external services like
OpenAI, Anthropic, and Google AI. Plaintext is never stored — only the
Fernet-encrypted ciphertext plus a `last_four` cosmetic hint for the UI.

One *active* credential per (workspace, provider). Re-adding for the same
provider revokes the prior row.
"""

from datetime import datetime
from enum import Enum as PyEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ProviderCredentialProvider(str, PyEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE_AI = "google_ai"


class ProviderCredentialTestStatus(str, PyEnum):
    OK = "ok"
    FAILED = "failed"


class ProviderCredential(Base, TimestampMixin):
    __tablename__ = "provider_credentials"
    __table_args__ = (
        # One active credential per (workspace, provider). When a user adds a
        # new key for a provider that already has one, the service revokes
        # the old row first, so the partial-unique index stays consistent.
        Index(
            "uq_provider_credentials_workspace_provider_active",
            "workspace_id",
            "provider",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    provider: Mapped[ProviderCredentialProvider] = mapped_column(
        Enum(
            ProviderCredentialProvider,
            name="provider_credential_provider",
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
    )
    label: Mapped[str | None] = mapped_column(String(120))
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    last_four: Mapped[str] = mapped_column(String(8), nullable=False)

    last_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_test_status: Mapped[ProviderCredentialTestStatus | None] = mapped_column(
        Enum(
            ProviderCredentialTestStatus,
            name="provider_credential_test_status",
            values_callable=lambda enum: [m.value for m in enum],
        )
    )
    last_test_error: Mapped[str | None] = mapped_column(Text)

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
