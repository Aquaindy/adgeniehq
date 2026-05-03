from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Password reset (single-use, short-lived). Hash stored at rest; the
    # plaintext travels in the reset-link email only.
    password_reset_hash: Mapped[str | None] = mapped_column(String(128), unique=True)
    password_reset_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # 2FA (TOTP). Secret is Fernet-encrypted at rest. Recovery codes are
    # SHA-256 hashed (one-time use; consumed on verify).
    two_factor_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    two_factor_secret_encrypted: Mapped[str | None] = mapped_column(String(512))
    two_factor_recovery_hashes: Mapped[list[str] | None] = mapped_column(JSONB)

    # Google OAuth login linkage. `google_subject` is Google's stable `sub`
    # claim — survives the user changing their email at Google. We link by
    # `sub` first, then fall back to email (e.g. for users created via
    # password signup who later add Google sign-in).
    google_subject: Mapped[str | None] = mapped_column(String(64), unique=True)

    memberships = relationship(
        "WorkspaceMember", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} email={self.email}>"
