"""Email verification: register hook, confirm (single-use + expiry), resend."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from app.services import email_verification_service


def _register(client: TestClient, email: str) -> dict:
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-9", "full_name": "V"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _seed_token(db: Session, email: str, token: str, *, hours: int) -> None:
    user = db.query(User).filter(User.email == email).first()
    assert user is not None
    user.email_verification_hash = hashlib.sha256(token.encode()).hexdigest()
    user.email_verification_expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)
    db.commit()


def test_register_issues_unverified_user_with_token(
    client: TestClient, db_session: Session
) -> None:
    _register(client, "newuser@example.com")
    user = db_session.query(User).filter(User.email == "newuser@example.com").first()
    assert user is not None
    assert user.email_verified_at is None
    assert user.email_verification_hash is not None
    assert user.email_verification_expires_at is not None


def test_confirm_marks_verified_and_is_single_use(
    client: TestClient, db_session: Session
) -> None:
    _register(client, "confirm@example.com")
    _seed_token(db_session, "confirm@example.com", "known-token-123", hours=1)

    resp = client.post(
        "/api/v1/auth/verify-email/confirm", json={"token": "known-token-123"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["email_verified_at"] is not None

    db_session.expire_all()
    user = db_session.query(User).filter(User.email == "confirm@example.com").first()
    assert user.email_verified_at is not None
    assert user.email_verification_hash is None

    # Replaying the now-consumed token is rejected.
    replay = client.post(
        "/api/v1/auth/verify-email/confirm", json={"token": "known-token-123"}
    )
    assert replay.status_code == 400


def test_confirm_rejects_expired_token(
    client: TestClient, db_session: Session
) -> None:
    _register(client, "expired@example.com")
    _seed_token(db_session, "expired@example.com", "expired-token", hours=-1)

    resp = client.post(
        "/api/v1/auth/verify-email/confirm", json={"token": "expired-token"}
    )
    assert resp.status_code == 400


def test_confirm_rejects_unknown_token(client: TestClient) -> None:
    resp = client.post("/api/v1/auth/verify-email/confirm", json={"token": "nope"})
    assert resp.status_code == 400


def test_resend_requires_auth(client: TestClient) -> None:
    assert client.post("/api/v1/auth/verify-email/resend").status_code == 401


def test_resend_issues_new_token(client: TestClient, db_session: Session) -> None:
    body = _register(client, "resend@example.com")
    user = db_session.query(User).filter(User.email == "resend@example.com").first()
    user.email_verification_hash = None
    db_session.commit()

    resp = client.post(
        "/api/v1/auth/verify-email/resend",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert resp.status_code == 204

    db_session.expire_all()
    user = db_session.query(User).filter(User.email == "resend@example.com").first()
    assert user.email_verification_hash is not None


def test_send_verification_is_noop_when_already_verified(
    db_session: Session,
) -> None:
    user = User(
        email="already@example.com",
        hashed_password="x",
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()

    email_verification_service.send_verification(db_session, user=user)
    db_session.refresh(user)
    assert user.email_verification_hash is None
