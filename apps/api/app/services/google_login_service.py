"""Google OAuth login.

Lifecycle:
1. Browser hits `GET /auth/google/start` → backend builds the Google
   authorize URL with a `state` JWT signed by APP_SECRET_KEY and 302-redirects.
2. Google redirects back to `/auth/google/callback?code=...&state=...`.
3. Backend verifies the state JWT, exchanges the code for tokens, fetches
   the userinfo (sub, email, email_verified, name).
4. Backend creates or links the User row and returns it. The route then
   issues an AdVanta access JWT + refresh cookie just like a normal login.

We use a separate OAuth client from the GA / Search Console / Google Ads
integrations: those need broad data scopes; login needs only `openid email
profile`. Keeping the consent screen narrow gives us a cleaner UX and lets
us eventually offer Google login without the user worrying about granting
ad-data access.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import AdVantaError
from app.models.user import User
from app.security.passwords import hash_password


_STATE_TYPE = "google_login_state"
_STATE_TTL_SECONDS = 600  # 10-minute window between /start and /callback
_JWT_ALG = "HS256"


_GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

_LOGIN_SCOPES = ["openid", "email", "profile"]


class GoogleLoginNotConfiguredError(AdVantaError):
    status_code = 503
    code = "google_login_not_configured"


class GoogleLoginInvalidStateError(AdVantaError):
    status_code = 400
    code = "google_login_invalid_state"


class GoogleLoginExchangeError(AdVantaError):
    status_code = 502
    code = "google_login_exchange_failed"


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------


def is_configured() -> bool:
    return bool(
        settings.google_login_client_id
        and settings.google_login_client_secret
        and settings.google_login_redirect_uri
    )


def _require_configured() -> None:
    if not is_configured():
        raise GoogleLoginNotConfiguredError(
            "GOOGLE_LOGIN_CLIENT_ID/SECRET/REDIRECT_URI must be set."
        )


# ---------------------------------------------------------------------------
# Step 1: build the authorize URL with a signed state token
# ---------------------------------------------------------------------------


def build_authorize_url(*, frontend_redirect_to: str | None = None) -> tuple[str, str]:
    """Returns (authorize_url, state_jwt). The caller stamps `state_jwt` onto
    a short-lived httpOnly cookie scoped to /api/v1/auth, then 302-redirects
    the browser to `authorize_url`. Google echoes `state_jwt` back on the
    callback so we can verify it didn't come from a CSRF attack."""

    _require_configured()

    nonce = secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc)
    state_token = jwt.encode(
        {
            "type": _STATE_TYPE,
            "nonce": nonce,
            "redirect_to": frontend_redirect_to or "/",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=_STATE_TTL_SECONDS)).timestamp()),
        },
        settings.app_secret_key,
        algorithm=_JWT_ALG,
    )

    from urllib.parse import urlencode

    params = {
        "client_id": settings.google_login_client_id,
        "redirect_uri": settings.google_login_redirect_uri,
        "response_type": "code",
        "scope": " ".join(_LOGIN_SCOPES),
        "state": state_token,
        "access_type": "online",
        "include_granted_scopes": "true",
        "prompt": "select_account",
    }
    return f"{_GOOGLE_AUTHORIZE_URL}?{urlencode(params)}", state_token


def verify_state(state_token: str) -> dict[str, Any]:
    """Decode and verify the state JWT. Raises if it's missing, malformed,
    expired, or wasn't signed by us."""
    if not state_token:
        raise GoogleLoginInvalidStateError("Missing state token.")
    try:
        payload = jwt.decode(
            state_token, settings.app_secret_key, algorithms=[_JWT_ALG]
        )
    except JWTError as exc:
        raise GoogleLoginInvalidStateError(
            f"Invalid state token: {exc}"
        ) from exc
    if payload.get("type") != _STATE_TYPE:
        raise GoogleLoginInvalidStateError("State token type mismatch.")
    return payload


# ---------------------------------------------------------------------------
# Step 2: exchange the code for userinfo
# ---------------------------------------------------------------------------


def exchange_code_for_userinfo(code: str) -> dict[str, Any]:
    """POSTs to Google's token endpoint, then GETs userinfo with the
    returned access token. Returns the userinfo dict (`sub`, `email`,
    `email_verified`, `name`)."""

    _require_configured()
    if not code:
        raise GoogleLoginExchangeError("Missing authorization code.")

    try:
        token_resp = httpx.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_login_client_id,
                "client_secret": settings.google_login_client_secret,
                "redirect_uri": settings.google_login_redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise GoogleLoginExchangeError(
            f"Could not reach Google token endpoint: {exc}"
        ) from exc

    if token_resp.status_code >= 400:
        raise GoogleLoginExchangeError(
            f"Google rejected the code: HTTP {token_resp.status_code}"
        )

    payload = token_resp.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise GoogleLoginExchangeError("Google returned no access_token.")

    try:
        userinfo_resp = httpx.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise GoogleLoginExchangeError(
            f"Could not fetch userinfo: {exc}"
        ) from exc

    if userinfo_resp.status_code >= 400:
        raise GoogleLoginExchangeError(
            f"Google userinfo returned HTTP {userinfo_resp.status_code}"
        )

    info = userinfo_resp.json()
    if not info.get("sub") or not info.get("email"):
        raise GoogleLoginExchangeError("Google userinfo missing sub/email.")
    return info


# ---------------------------------------------------------------------------
# Step 3: link the user (create-or-link)
# ---------------------------------------------------------------------------


def find_or_create_user(db, *, info: dict[str, Any]) -> User:
    """Look up by `sub` first, then by `email`. Create a new user if neither
    matches. New users get a random sentinel password they'll never use —
    they can set a real password later via /auth/password-reset/request."""

    google_sub: str = info["sub"]
    email: str = info["email"].strip().lower()
    name: str | None = info.get("name")

    user = (
        db.query(User).filter(User.google_subject == google_sub).first()
        or db.query(User).filter(User.email == email).first()
    )

    if user is None:
        from datetime import datetime, timezone

        sentinel = secrets.token_urlsafe(32)
        user = User(
            email=email,
            full_name=name,
            hashed_password=hash_password(sentinel),
            is_active=True,
            email_verified_at=(
                datetime.now(timezone.utc)
                if info.get("email_verified") in (True, "true")
                else None
            ),
            google_subject=google_sub,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    # Existing user: link the Google subject if it isn't already linked. We
    # never overwrite an existing google_subject — that would let a user with
    # the same email at a different Google account hijack the account.
    if user.google_subject is None:
        user.google_subject = google_sub
    if not user.full_name and name:
        user.full_name = name
    db.commit()
    db.refresh(user)
    return user
