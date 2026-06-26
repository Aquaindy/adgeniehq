from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class RefreshToken(Base, TimestampMixin):
    """Server-side ledger of issued refresh-token JTIs so sessions can be
    revoked (logout, password reset, theft) and rotated.

    Each successful ``/auth/refresh`` rotates: the presented row is marked
    ``revoked_at`` and a fresh row is issued. Presenting an already-revoked JTI
    again is treated as token REUSE (theft) and revokes every live session for
    that user."""

    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # "Remember me": True = persistent cookie (~30d), False = browser-session
    # cookie that's dropped on close. Carried across rotation so a session that
    # opted out of being remembered never silently becomes persistent.
    persistent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
