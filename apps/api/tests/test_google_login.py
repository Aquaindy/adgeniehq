"""Google OAuth login tests.

Goals:
- /auth/google/start returns 503 if env not configured.
- /auth/google/start (when configured) 307s to Google with state cookie.
- /auth/google/callback rejects when state cookie ≠ state param (CSRF).
- /auth/google/callback creates a new user on first login (mocked exchange).
- /auth/google/callback links Google to an existing user with the same email.
- /auth/google/callback re-uses an existing user when google_subject already set.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from app.security.passwords import hash_password


@pytest.fixture(autouse=True)
def _google_env():
    keys = {
        "GOOGLE_LOGIN_CLIENT_ID": "test-client-id.apps.googleusercontent.com",
        "GOOGLE_LOGIN_CLIENT_SECRET": "test-client-secret",
        "GOOGLE_LOGIN_REDIRECT_URI": "http://testserver/api/v1/auth/google/callback",
    }
    saved = {k: os.environ.get(k) for k in keys}
    os.environ.update(keys)
    # Re-import settings since it's cached at module load.
    from app.core import config as cfg

    for attr, value in {
        "google_login_client_id": keys["GOOGLE_LOGIN_CLIENT_ID"],
        "google_login_client_secret": keys["GOOGLE_LOGIN_CLIENT_SECRET"],
        "google_login_redirect_uri": keys["GOOGLE_LOGIN_REDIRECT_URI"],
    }.items():
        setattr(cfg.settings, attr, value)

    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for attr in (
            "google_login_client_id",
            "google_login_client_secret",
            "google_login_redirect_uri",
        ):
            setattr(cfg.settings, attr, "")


def test_start_returns_503_when_unconfigured(client: TestClient) -> None:
    from app.core import config as cfg

    cfg.settings.google_login_client_id = ""
    response = client.get("/api/v1/auth/google/start", follow_redirects=False)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "google_login_not_configured"


def test_start_redirects_to_google_with_state_cookie(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/auth/google/start", follow_redirects=False
    )
    assert response.status_code == 307
    assert response.headers["location"].startswith(
        "https://accounts.google.com/o/oauth2/v2/auth?"
    )
    assert "advanta_google_login_state" in response.cookies


def test_callback_rejects_state_mismatch_redirects_to_login(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/auth/google/callback?code=x&state=mismatched",
        follow_redirects=False,
        cookies={"advanta_google_login_state": "different-token"},
    )
    assert response.status_code == 302
    assert "error=google_invalid_state" in response.headers["location"]


def _stub_google_exchange(*, sub: str, email: str, name: str = "Test User"):
    """Patches httpx.post (token exchange) and httpx.get (userinfo)."""
    token_resp = type(
        "R",
        (),
        {"status_code": 200, "json": lambda self: {"access_token": "ya29.fake"}},
    )()
    info_resp = type(
        "R",
        (),
        {
            "status_code": 200,
            "json": lambda self: {
                "sub": sub,
                "email": email,
                "email_verified": True,
                "name": name,
            },
        },
    )()
    return patch(
        "app.services.google_login_service.httpx.post",
        return_value=token_resp,
    ), patch(
        "app.services.google_login_service.httpx.get",
        return_value=info_resp,
    )


def _start_and_get_state(client: TestClient) -> str:
    response = client.get(
        "/api/v1/auth/google/start", follow_redirects=False
    )
    return response.cookies["advanta_google_login_state"]


def test_callback_creates_user_on_first_login(
    client: TestClient, db_session: Session
) -> None:
    state = _start_and_get_state(client)

    post_patch, get_patch = _stub_google_exchange(
        sub="111111111", email="newcomer@example.com"
    )
    with post_patch, get_patch:
        response = client.get(
            f"/api/v1/auth/google/callback?code=auth-code&state={state}",
            follow_redirects=False,
            cookies={"advanta_google_login_state": state},
        )

    assert response.status_code == 302
    assert "/auth/google/finish" in response.headers["location"]
    # Refresh cookie set so the frontend can call /refresh.
    assert "advanta_refresh" in response.cookies

    user = (
        db_session.query(User)
        .filter(User.email == "newcomer@example.com")
        .first()
    )
    assert user is not None
    assert user.google_subject == "111111111"
    assert user.full_name == "Test User"


def test_callback_links_to_existing_user_with_same_email(
    client: TestClient, db_session: Session
) -> None:
    existing = User(
        email="alice@example.com",
        hashed_password=hash_password("correct-horse-9"),
        is_active=True,
    )
    db_session.add(existing)
    db_session.commit()

    state = _start_and_get_state(client)
    post_patch, get_patch = _stub_google_exchange(
        sub="222222222", email="alice@example.com", name="Alice"
    )
    with post_patch, get_patch:
        response = client.get(
            f"/api/v1/auth/google/callback?code=auth-code&state={state}",
            follow_redirects=False,
            cookies={"advanta_google_login_state": state},
        )

    assert response.status_code == 302
    db_session.refresh(existing)
    assert existing.google_subject == "222222222"  # linked, not duplicated
    # No second user created
    count = db_session.query(User).filter(User.email == "alice@example.com").count()
    assert count == 1


def test_callback_reuses_user_with_existing_google_subject(
    client: TestClient, db_session: Session
) -> None:
    existing = User(
        email="alice@example.com",
        hashed_password=hash_password("correct-horse-9"),
        is_active=True,
        google_subject="333333333",
    )
    db_session.add(existing)
    db_session.commit()

    state = _start_and_get_state(client)
    post_patch, get_patch = _stub_google_exchange(
        sub="333333333", email="alice@example.com"
    )
    with post_patch, get_patch:
        response = client.get(
            f"/api/v1/auth/google/callback?code=auth-code&state={state}",
            follow_redirects=False,
            cookies={"advanta_google_login_state": state},
        )

    assert response.status_code == 302
    count = db_session.query(User).count()
    assert count == 1
