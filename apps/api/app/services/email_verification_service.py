"""Email verification.

`send_verification` mints a single-use token for an unverified user and emails
the confirm link. `confirm` swaps a valid token for a verified timestamp.
`resend` re-issues for an authenticated, still-unverified user.

Verification is *soft*: it never blocks login. The frontend shows a banner with
a resend action until `email_verified_at` is set. Google-login users arrive
pre-verified (Google asserts `email_verified`), so they never see the flow.

Same storage pattern as password reset: only the SHA-256 hash of the token is
persisted; the plaintext travels in the link email only.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AdVantaError
from app.core.logging import get_logger
from app.models.user import User
from app.services.email_service import EmailMessageDraft, send_email

log = get_logger(__name__)

VERIFY_TTL_HOURS = 48


class InvalidVerificationTokenError(AdVantaError):
    status_code = 400
    code = "invalid_verification_token"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def send_verification(db: Session, *, user: User) -> None:
    """Mint a fresh token and email the confirm link. No-op if already verified.

    Best-effort on delivery: if no email transport is configured the draft is
    structure-logged and the token is still stored (the user can verify via a
    resend once email is wired up)."""
    if user.email_verified_at is not None:
        return

    token = secrets.token_urlsafe(32)
    user.email_verification_hash = _hash(token)
    user.email_verification_expires_at = datetime.now(timezone.utc) + timedelta(
        hours=VERIFY_TTL_HOURS
    )
    db.commit()

    base = (settings.frontend_url or "").rstrip("/")
    link = f"{base}/verify-email?token={token}"
    draft = EmailMessageDraft(
        subject="Verify your AdVanta email",
        text_body=(
            "Welcome to AdVanta!\n\n"
            f"Confirm your email address to secure your account:\n{link}\n\n"
            f"This link expires in {VERIFY_TTL_HOURS} hours. If you didn't "
            "create an AdVanta account, you can ignore this email."
        ),
        html_body=(
            "<p>Welcome to <strong>AdVanta</strong>!</p>"
            "<p>Confirm your email address to secure your account:</p>"
            f'<p><a href="{link}">Verify your email</a></p>'
            '<p style="color:#94A3B8;font-size:12px;">This link expires in '
            f"{VERIFY_TTL_HOURS} hours. If you didn't create an AdVanta "
            "account, you can ignore this email.</p>"
        ),
    )
    send_email(to=user.email, draft=draft)


def confirm(db: Session, *, token: str) -> User:
    """Validate a token and mark the user verified. Single-use: the token is
    cleared on success so a replayed link 400s."""
    if not token or not token.strip():
        raise InvalidVerificationTokenError("Token is required.")

    user = (
        db.query(User)
        .filter(User.email_verification_hash == _hash(token.strip()))
        .first()
    )
    if user is None:
        raise InvalidVerificationTokenError(
            "Token is invalid or has already been used."
        )
    if (
        user.email_verification_expires_at is None
        or user.email_verification_expires_at < datetime.now(timezone.utc)
    ):
        raise InvalidVerificationTokenError(
            "Token has expired — request a new verification link."
        )

    user.email_verified_at = datetime.now(timezone.utc)
    user.email_verification_hash = None
    user.email_verification_expires_at = None
    db.commit()
    db.refresh(user)
    return user


def resend(db: Session, *, user: User) -> None:
    """Re-issue verification for an authenticated, still-unverified user."""
    send_verification(db, user=user)
