from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.models.user import User
from app.security.passwords import hash_password, verify_password
from app.security.tokens import create_token


class EmailAlreadyRegisteredError(AdVantaError):
    status_code = 409
    code = "email_already_registered"


class InvalidCredentialsError(AdVantaError):
    status_code = 401
    code = "invalid_credentials"


def register_user(
    db: Session, *, email: str, password: str, full_name: str | None
) -> User:
    user = User(
        email=email.lower().strip(),
        hashed_password=hash_password(password),
        full_name=full_name,
        is_active=True,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise EmailAlreadyRegisteredError("That email is already registered.") from exc
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, *, email: str, password: str) -> User:
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if user is None or not verify_password(password, user.hashed_password):
        raise InvalidCredentialsError("Email or password is incorrect.")
    if not user.is_active:
        raise InvalidCredentialsError("This account is inactive.")
    return user


def issue_tokens(
    db: Session, user: User, *, persistent: bool = True
) -> tuple[str, datetime, str]:
    """Mint an access token plus a tracked refresh token (recorded server-side
    so it can be revoked). `persistent` records the "remember me" choice so the
    refresh cookie can be persistent (~30d) or browser-session only. Returns
    (access_token, access_exp, refresh_token)."""
    from app.services import refresh_token_service

    access_token, access_exp = create_token(subject=user.id, token_type="access")
    refresh_token = refresh_token_service.issue_refresh_token(
        db, user=user, persistent=persistent
    )
    return access_token, access_exp, refresh_token


def access_token_seconds_remaining(expires_at: datetime) -> int:
    delta = expires_at - datetime.now(timezone.utc)
    return max(0, int(delta.total_seconds()))
