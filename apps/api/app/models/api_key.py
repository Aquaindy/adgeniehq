"""Workspace-scoped API keys.

Wire format: `ak_<8-char-prefix>.<base64url-secret>` — the prefix is also
stored on the row so we can look up the matching key in O(1) instead of
brute-forcing the secret hash table. The full secret is SHA-256 hashed at
rest and never recoverable.

Each key carries the role it grants when used (defaults to MARKETER), the
workspace, the creating user, and a `last_used_at` for visibility.

Keys are cleartext exactly once — at creation time.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.security.permissions import Role


class ApiKey(Base, TimestampMixin):
    __tablename__ = "api_keys"
    __table_args__ = (
        UniqueConstraint("prefix", name="uq_api_keys_prefix"),
        UniqueConstraint("secret_hash", name="uq_api_keys_secret_hash"),
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
    created_by: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="workspace_member_role", create_type=False),
        nullable=False,
        default=Role.MARKETER,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
