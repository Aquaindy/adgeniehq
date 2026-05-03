"""Signed state tokens for OAuth round-trips.

Carry workspace_id + user_id + provider through the redirect dance, signed with
APP_SECRET_KEY so the callback can validate authenticity and prevent CSRF."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import AdVantaError

ALGORITHM = "HS256"
TOKEN_TYPE = "oauth_state"
EXPIRY_MINUTES = 10


class InvalidStateError(AdVantaError):
    status_code = 400
    code = "invalid_oauth_state"


def issue_state(*, workspace_id: UUID, user_id: UUID, provider: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "type": TOKEN_TYPE,
        "ws": str(workspace_id),
        "uid": str(user_id),
        "p": provider,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=EXPIRY_MINUTES)).timestamp()),
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm=ALGORITHM)


def parse_state(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise InvalidStateError("OAuth state is invalid or expired.") from exc

    if payload.get("type") != TOKEN_TYPE:
        raise InvalidStateError("OAuth state has wrong type.")
    if not payload.get("ws") or not payload.get("uid") or not payload.get("p"):
        raise InvalidStateError("OAuth state is missing required fields.")
    return payload
