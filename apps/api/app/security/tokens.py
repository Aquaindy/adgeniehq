from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import AdVantaError

ALGORITHM = "HS256"

TokenType = Literal["access", "refresh"]


class InvalidTokenError(AdVantaError):
    status_code = 401
    code = "invalid_token"


def _expiry_for(token_type: TokenType) -> datetime:
    now = datetime.now(timezone.utc)
    if token_type == "access":
        return now + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    return now + timedelta(days=settings.jwt_refresh_token_expire_days)


def create_token(*, subject: UUID | str, token_type: TokenType) -> tuple[str, datetime]:
    expires_at = _expiry_for(token_type)
    payload = {
        "sub": str(subject),
        "type": token_type,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": str(uuid4()),
    }
    token = jwt.encode(payload, settings.app_secret_key, algorithm=ALGORITHM)
    return token, expires_at


def decode_token(token: str, *, expected_type: TokenType) -> dict:
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise InvalidTokenError("Token is invalid or expired.") from exc

    if payload.get("type") != expected_type:
        raise InvalidTokenError("Token type mismatch.")

    sub = payload.get("sub")
    if not sub:
        raise InvalidTokenError("Token missing subject.")

    return payload
