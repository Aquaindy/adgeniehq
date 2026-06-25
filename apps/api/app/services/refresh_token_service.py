"""Server-side refresh-token lifecycle: issue, rotate (with reuse detection),
and revoke. Backs logout / password-reset / theft response so a stolen or
logged-out refresh token cannot keep minting access tokens for 30 days.

Flow:
  * issue     — mint a refresh JWT with a fresh JTI and record it.
  * rotate    — on /auth/refresh, validate the presented JTI, revoke it, and
                issue a new one. A presented JTI that is unknown or already
                revoked is rejected; an already-revoked JTI means REUSE
                (the rightful token was rotated away) → revoke ALL the user's
                live sessions.
  * revoke*   — single (logout) or all (password reset / theft).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.security.tokens import InvalidTokenError, create_token, decode_token


class RefreshTokenReuseError(AdVantaError):
    status_code = 401
    code = "refresh_token_reuse"


def issue_refresh_token(db: Session, *, user: User) -> str:
    """Mint + persist a new refresh token. Returns the signed token."""
    jti = str(uuid4())
    token, expires_at = create_token(subject=user.id, token_type="refresh", jti=jti)
    db.add(RefreshToken(user_id=user.id, jti=jti, expires_at=expires_at))
    db.flush()
    return token


def rotate(db: Session, *, presented_token: str) -> tuple[User, str]:
    """Validate + rotate a presented refresh token. Returns (user, new_token).
    Raises InvalidTokenError (unknown/expired/forged) or RefreshTokenReuseError
    (already-revoked JTI replayed → all sessions revoked)."""
    payload = decode_token(presented_token, expected_type="refresh")  # raises if bad/expired
    jti = payload.get("jti")
    user_id = UUID(payload["sub"])

    row = (
        db.query(RefreshToken).filter(RefreshToken.jti == jti).first() if jti else None
    )
    if row is None:
        # Unknown JTI — forged, or issued before tracking existed. Reject; the
        # user simply re-logs in.
        raise InvalidTokenError("Refresh token is not recognized.")

    if row.revoked_at is not None:
        # The rightful holder already rotated this token away; seeing it again
        # means it leaked. Burn every live session for the user.
        revoke_all_for_user(db, user_id=row.user_id)
        db.flush()
        raise RefreshTokenReuseError("Refresh token reuse detected; sessions revoked.")

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        row.revoked_at = datetime.now(timezone.utc)
        db.flush()
        raise InvalidTokenError("Refresh subject is invalid.")

    row.revoked_at = datetime.now(timezone.utc)
    new_token = issue_refresh_token(db, user=user)
    return user, new_token


def revoke(db: Session, *, jti: str) -> None:
    row = (
        db.query(RefreshToken)
        .filter(RefreshToken.jti == jti, RefreshToken.revoked_at.is_(None))
        .first()
    )
    if row is not None:
        row.revoked_at = datetime.now(timezone.utc)


def revoke_all_for_user(db: Session, *, user_id: UUID) -> int:
    now = datetime.now(timezone.utc)
    rows = (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .all()
    )
    for row in rows:
        row.revoked_at = now
    return len(rows)


def revoke_token_value(db: Session, *, token: str | None) -> None:
    """Best-effort revoke from a raw token string (logout). A missing/invalid
    token is a silent no-op — logout should always succeed."""
    if not token:
        return
    try:
        payload = decode_token(token, expected_type="refresh")
    except InvalidTokenError:
        return
    jti = payload.get("jti")
    if jti:
        revoke(db, jti=jti)
