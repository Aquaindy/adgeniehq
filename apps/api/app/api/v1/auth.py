from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AdVantaError
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.users import UserPublic
from app.security.dependencies import get_current_user
from app.security.tokens import create_token
from app.services.auth_service import (
    access_token_seconds_remaining,
    authenticate_user,
    issue_tokens,
    register_user,
)

router = APIRouter()

REFRESH_COOKIE_NAME = "advanta_refresh"
REFRESH_COOKIE_PATH = f"{settings.api_v1_prefix}/auth"


class RefreshNotProvidedError(AdVantaError):
    status_code = 401
    code = "refresh_not_provided"


def _set_refresh_cookie(response: Response, refresh_token: str, *, max_age_seconds: int) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=max_age_seconds,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


def _build_token_response(response: Response, user: User, db: Session) -> TokenResponse:
    access_token, access_exp, refresh_token = issue_tokens(db, user)
    db.commit()  # persist the refresh-token ledger row
    refresh_max_age = settings.jwt_refresh_token_expire_days * 24 * 60 * 60
    _set_refresh_cookie(response, refresh_token, max_age_seconds=refresh_max_age)
    return TokenResponse(
        access_token=access_token,
        expires_in=access_token_seconds_remaining(access_exp),
        user=UserPublic.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = register_user(
        db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
    )
    return _build_token_response(response, user, db)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = authenticate_user(db, email=payload.email, password=payload.password)
    if user.two_factor_enabled:
        from app.core.exceptions import AdVantaError
        from app.services import two_factor_service

        if not payload.otp_code:
            class _TwoFactorRequiredError(AdVantaError):
                status_code = 401
                code = "two_factor_required"

            raise _TwoFactorRequiredError("2FA code required.")
        if not two_factor_service.verify_login_code(
            db, user=user, code=payload.otp_code
        ):
            raise two_factor_service.TwoFactorInvalidCodeError("Invalid 2FA code.")
    return _build_token_response(response, user, db)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    response: Response,
    db: Session = Depends(get_db),
    advanta_refresh: str | None = Cookie(default=None),
) -> TokenResponse:
    if not advanta_refresh:
        raise RefreshNotProvidedError("Refresh token cookie missing.")

    from app.services import refresh_token_service

    try:
        user, new_refresh_token = refresh_token_service.rotate(
            db, presented_token=advanta_refresh
        )
    except (AdVantaError):
        # Invalid / reused / expired refresh token — clear the cookie so the
        # client stops presenting it, and surface 401.
        db.commit()  # persist any reuse-triggered mass revocation
        _clear_refresh_cookie(response)
        raise
    db.commit()

    access_token, access_exp = create_token(subject=user.id, token_type="access")
    refresh_max_age = settings.jwt_refresh_token_expire_days * 24 * 60 * 60
    _set_refresh_cookie(response, new_refresh_token, max_age_seconds=refresh_max_age)

    return TokenResponse(
        access_token=access_token,
        expires_in=access_token_seconds_remaining(access_exp),
        user=UserPublic.model_validate(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    db: Session = Depends(get_db),
    advanta_refresh: str | None = Cookie(default=None),
) -> Response:
    # Revoke the presented refresh token server-side so it can't be reused.
    from app.services import refresh_token_service

    refresh_token_service.revoke_token_value(db, token=advanta_refresh)
    db.commit()
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(user)


class _PasswordResetRequest(BaseModel):
    email: EmailStr


class _PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=512)


@router.post("/password-reset/request", status_code=status.HTTP_204_NO_CONTENT)
def password_reset_request(
    payload: _PasswordResetRequest,
    db: Session = Depends(get_db),
) -> Response:
    """Always 204 — never reveals whether the email is registered."""

    from app.services import password_reset_service

    password_reset_service.request_reset(db, email=payload.email)
    return Response(status_code=204)


@router.post("/password-reset/confirm", response_model=UserPublic)
def password_reset_confirm(
    payload: _PasswordResetConfirm,
    db: Session = Depends(get_db),
) -> UserPublic:
    from app.services import password_reset_service

    user = password_reset_service.confirm_reset(
        db, token=payload.token, new_password=payload.new_password
    )
    return UserPublic.model_validate(user)


# ---------------------------------------------------------------------------
# 2FA (TOTP)
# ---------------------------------------------------------------------------


class _TwoFactorSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str
    issuer: str


class _TwoFactorConfirmRequest(BaseModel):
    code: str = Field(min_length=4, max_length=32)


class _TwoFactorConfirmResponse(BaseModel):
    recovery_codes: list[str]


class _TwoFactorDisableRequest(BaseModel):
    code: str = Field(min_length=4, max_length=32)


@router.post("/2fa/setup", response_model=_TwoFactorSetupResponse)
def two_factor_setup(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> _TwoFactorSetupResponse:
    from app.services import two_factor_service

    return _TwoFactorSetupResponse(**two_factor_service.start_setup(db, user=user))


@router.post("/2fa/confirm", response_model=_TwoFactorConfirmResponse)
def two_factor_confirm(
    payload: _TwoFactorConfirmRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> _TwoFactorConfirmResponse:
    from app.services import two_factor_service

    return _TwoFactorConfirmResponse(
        **two_factor_service.confirm_setup(db, user=user, code=payload.code)
    )


@router.post("/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
def two_factor_disable(
    payload: _TwoFactorDisableRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    from app.services import two_factor_service

    two_factor_service.disable(db, user=user, code=payload.code)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Google OAuth login
# ---------------------------------------------------------------------------


_GOOGLE_STATE_COOKIE = "advanta_google_login_state"


@router.get("/google/start", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
def google_login_start(response: Response, redirect_to: str | None = None):
    """Build the Google authorize URL and 307-redirect the browser to it.
    A short-lived state JWT is set as an httpOnly cookie so the callback can
    verify the round-trip wasn't forged."""
    from fastapi.responses import RedirectResponse
    from app.services import google_login_service

    if not google_login_service.is_configured():
        raise google_login_service.GoogleLoginNotConfiguredError(
            "Google login is not enabled on this server."
        )

    auth_url, state_token = google_login_service.build_authorize_url(
        frontend_redirect_to=redirect_to
    )
    redirect = RedirectResponse(url=auth_url, status_code=307)
    redirect.set_cookie(
        key=_GOOGLE_STATE_COOKIE,
        value=state_token,
        max_age=600,  # 10 minutes — matches the JWT TTL
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        path="/api/v1/auth",
    )
    return redirect


@router.get("/google/callback")
def google_login_callback(
    response: Response,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    advanta_google_login_state: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    """Handles the Google OAuth callback. Verifies state, exchanges the code,
    creates-or-links the user, sets the AdVanta refresh cookie, and 302's the
    browser back to the frontend success URL.

    On any failure we redirect to `${FRONTEND_URL}/login?error=...` so the
    user lands somewhere usable instead of a JSON error."""

    from fastapi.responses import RedirectResponse
    from app.services import google_login_service

    frontend = settings.frontend_url.rstrip("/")

    if error:
        return RedirectResponse(
            url=f"{frontend}/login?error=google_{error}", status_code=302
        )

    # The state we just received from Google must match the cookie we set
    # at /start. Without the cookie, this is a CSRF attempt.
    if not advanta_google_login_state or advanta_google_login_state != state:
        return RedirectResponse(
            url=f"{frontend}/login?error=google_invalid_state", status_code=302
        )

    try:
        state_payload = google_login_service.verify_state(state)
    except google_login_service.GoogleLoginInvalidStateError:
        return RedirectResponse(
            url=f"{frontend}/login?error=google_invalid_state", status_code=302
        )

    if not code:
        return RedirectResponse(
            url=f"{frontend}/login?error=google_no_code", status_code=302
        )

    try:
        info = google_login_service.exchange_code_for_userinfo(code)
    except google_login_service.GoogleLoginExchangeError:
        return RedirectResponse(
            url=f"{frontend}/login?error=google_exchange_failed", status_code=302
        )

    user = google_login_service.find_or_create_user(db, info=info)
    if not user.is_active:
        return RedirectResponse(
            url=f"{frontend}/login?error=account_disabled", status_code=302
        )

    redirect_to = state_payload.get("redirect_to") or "/"
    if not redirect_to.startswith("/"):
        redirect_to = "/"

    redirect = RedirectResponse(
        url=f"{frontend}/auth/google/finish?to={redirect_to}", status_code=302
    )
    # Clear the state cookie now that we've consumed it.
    redirect.delete_cookie(
        key=_GOOGLE_STATE_COOKIE, path="/api/v1/auth"
    )
    # Set the same advanta_refresh cookie a normal /login sets — the frontend
    # /auth/google/finish page calls /auth/refresh on mount to get the access
    # token, then routes to `redirect_to`.
    _, _access_exp, refresh_token = issue_tokens(db, user)
    db.commit()  # persist the refresh-token ledger row
    refresh_max_age = settings.jwt_refresh_token_expire_days * 24 * 60 * 60
    redirect.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=refresh_max_age,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )
    return redirect
