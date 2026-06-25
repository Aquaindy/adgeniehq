"""Refresh-token revocation, rotation, and reuse detection.

Security properties under test:
  * logout revokes the refresh token server-side (it can't be replayed);
  * replaying an already-rotated token is detected as REUSE and revokes every
    live session for that user;
  * a password reset revokes all of the user's refresh tokens.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.security.passwords import hash_password
from app.services import password_reset_service, refresh_token_service


def _register(client: TestClient, email: str) -> dict:
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-9", "full_name": "U"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _refresh_with(client: TestClient, token: str):
    client.cookies.clear()
    return client.post(
        "/api/v1/auth/refresh", headers={"Cookie": f"advanta_refresh={token}"}
    )


def test_logout_revokes_refresh_token(client: TestClient) -> None:
    _register(client, "logout@example.com")
    token = client.cookies.get("advanta_refresh")
    assert token

    assert client.post("/api/v1/auth/logout").status_code == 204

    # The revoked token can no longer be refreshed.
    replay = _refresh_with(client, token)
    assert replay.status_code == 401


def test_replayed_token_is_reuse_and_revokes_all_sessions(client: TestClient) -> None:
    _register(client, "reuse@example.com")
    first = client.cookies.get("advanta_refresh")

    rotated = client.post("/api/v1/auth/refresh")
    assert rotated.status_code == 200
    new = client.cookies.get("advanta_refresh")
    assert new and new != first

    # Replay the FIRST (now-rotated-away) token -> reuse detected.
    replay = _refresh_with(client, first)
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "refresh_token_reuse"

    # Reuse revokes ALL sessions, so even the otherwise-valid `new` token dies.
    after = _refresh_with(client, new)
    assert after.status_code == 401


def test_password_reset_revokes_all_refresh_tokens(db_session: Session) -> None:
    user = User(
        email="reset@example.com",
        hashed_password=hash_password("correct-horse-9"),
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    refresh_token_service.issue_refresh_token(db_session, user=user)
    refresh_token_service.issue_refresh_token(db_session, user=user)
    db_session.commit()
    assert (
        db_session.query(RefreshToken)
        .filter(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .count()
        == 2
    )

    raw = "reset-token-xyz"
    user.password_reset_hash = hashlib.sha256(raw.encode()).hexdigest()
    user.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    db_session.commit()

    password_reset_service.confirm_reset(db_session, token=raw, new_password="brandnewpass1")

    live = (
        db_session.query(RefreshToken)
        .filter(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .count()
    )
    assert live == 0


def test_unknown_refresh_token_is_rejected(client: TestClient) -> None:
    # A well-formed token whose JTI was never issued (e.g. forged or pre-dates
    # tracking) must be rejected rather than minting access tokens.
    _register(client, "unknown@example.com")
    from app.security.tokens import create_token

    forged, _ = create_token(subject="00000000-0000-0000-0000-000000000000", token_type="refresh")
    resp = _refresh_with(client, forged)
    assert resp.status_code == 401
