"""Password reset.

`request` accepts an email; if a user with that email exists we mint a
single-use token and email the link. The endpoint always returns 200 to
avoid leaking which emails are registered.

`confirm` swaps the token for a new password."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AdVantaError
from app.core.logging import get_logger
from app.models.user import User
from app.security.passwords import hash_password
from app.services.email_service import EmailMessageDraft, send_email

log = get_logger(__name__)

RESET_TTL_HOURS = 2


class InvalidResetTokenError(AdVantaError):
    status_code = 400
    code = "invalid_reset_token"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# We persist reset tokens directly on the User row to avoid a new table for
# something that's strictly single-use + short-lived. Two columns:
# `password_reset_hash` and `password_reset_expires_at`.


def request_reset(db: Session, *, email: str) -> None:
    """Always returns silently — never reveals whether the email exists."""

    normalized = (email or "").strip().lower()
    if not normalized or "@" not in normalized:
        return
    user = db.query(User).filter(User.email == normalized).first()
    if user is None or not user.is_active:
        return

    token = secrets.token_urlsafe(32)
    user.password_reset_hash = _hash(token)
    user.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(
        hours=RESET_TTL_HOURS
    )
    db.commit()

    base = (settings.frontend_url or "").rstrip("/")
    link = f"{base}/reset-password?token={token}"
    draft = EmailMessageDraft(
        subject="Reset your AdVanta AI password",
        text_body=(
            "You (or someone on your behalf) requested a password reset for "
            f"{normalized}.\n\nReset your password: {link}\n\n"
            f"This link expires in {RESET_TTL_HOURS} hours. "
            "If you didn't request this, you can safely ignore this email."
        ),
        html_body=(
            f"<p>You requested a password reset for <strong>{normalized}</strong>.</p>"
            f"<p><a href=\"{link}\">Reset your password</a></p>"
            f"<p style=\"color:#94A3B8;font-size:12px;\">This link expires in "
            f"{RESET_TTL_HOURS} hours. If you didn't request this, ignore "
            "this email.</p>"
        ),
    )
    send_email(to=normalized, draft=draft)


def confirm_reset(
    db: Session, *, token: str, new_password: str
) -> User:
    if not token or not token.strip():
        raise InvalidResetTokenError("Token is required.")
    if not new_password or len(new_password) < 8:
        raise InvalidResetTokenError("New password must be at least 8 characters.")

    user = (
        db.query(User)
        .filter(User.password_reset_hash == _hash(token.strip()))
        .first()
    )
    if user is None:
        raise InvalidResetTokenError("Token is invalid or has already been used.")
    if user.password_reset_expires_at is None or user.password_reset_expires_at < datetime.now(timezone.utc):
        raise InvalidResetTokenError("Token has expired — request a new reset.")

    user.hashed_password = hash_password(new_password)
    user.password_reset_hash = None
    user.password_reset_expires_at = None
    # A password reset invalidates every existing session — revoke all of the
    # user's live refresh tokens so a leaked/old token can't survive the reset.
    from app.services import refresh_token_service

    refresh_token_service.revoke_all_for_user(db, user_id=user.id)
    db.commit()
    db.refresh(user)
    return user
