"""2FA (TOTP) flow tests.

Goals:
- Setup returns a fresh secret + provisioning URI without enabling 2FA.
- Confirming with the wrong code does NOT enable 2FA.
- Confirming with the correct code enables 2FA and returns 8 recovery codes.
- Login without otp_code is rejected (`two_factor_required`).
- Login with the correct TOTP code succeeds.
- Login with a recovery code succeeds and consumes the code.
- Disable requires a valid code.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from app.security.totp import current_code as totp_current_code


def _register(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@example.com",
            "password": "correct-horse-9",
            "full_name": "Alice",
        },
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return token


def test_setup_returns_secret_without_enabling(
    client: TestClient, db_session: Session
) -> None:
    _register(client)
    response = client.post("/api/v1/auth/2fa/setup")
    assert response.status_code == 200
    body = response.json()
    assert body["secret"]
    assert body["provisioning_uri"].startswith("otpauth://totp/")

    user = db_session.query(User).filter(User.email == "alice@example.com").first()
    db_session.refresh(user)
    assert user.two_factor_enabled is False
    assert user.two_factor_secret_encrypted is not None


def test_confirm_with_wrong_code_does_not_enable(
    client: TestClient, db_session: Session
) -> None:
    _register(client)
    client.post("/api/v1/auth/2fa/setup")
    response = client.post("/api/v1/auth/2fa/confirm", json={"code": "000000"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "two_factor_invalid_code"


def test_full_2fa_lifecycle(client: TestClient, db_session: Session) -> None:
    _register(client)
    setup = client.post("/api/v1/auth/2fa/setup").json()
    secret = setup["secret"]

    # Confirm with the right code.
    response = client.post(
        "/api/v1/auth/2fa/confirm",
        json={"code": totp_current_code(secret)},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["recovery_codes"]) == 8

    # Login without otp → 401, two_factor_required
    client.headers.pop("Authorization", None)
    no_otp = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "correct-horse-9"},
    )
    assert no_otp.status_code == 401
    assert no_otp.json()["error"]["code"] == "two_factor_required"

    # Login with current TOTP succeeds
    with_otp = client.post(
        "/api/v1/auth/login",
        json={
            "email": "alice@example.com",
            "password": "correct-horse-9",
            "otp_code": totp_current_code(secret),
        },
    )
    assert with_otp.status_code == 200
    assert with_otp.json()["user"]["email"] == "alice@example.com"


def test_recovery_code_consumed_on_use(
    client: TestClient, db_session: Session
) -> None:
    _register(client)
    setup = client.post("/api/v1/auth/2fa/setup").json()
    confirmed = client.post(
        "/api/v1/auth/2fa/confirm",
        json={"code": totp_current_code(setup["secret"])},
    ).json()
    code = confirmed["recovery_codes"][0]

    client.headers.pop("Authorization", None)
    first = client.post(
        "/api/v1/auth/login",
        json={
            "email": "alice@example.com",
            "password": "correct-horse-9",
            "otp_code": code,
        },
    )
    assert first.status_code == 200

    # Reusing the same recovery code should fail
    second = client.post(
        "/api/v1/auth/login",
        json={
            "email": "alice@example.com",
            "password": "correct-horse-9",
            "otp_code": code,
        },
    )
    assert second.status_code == 401
    assert second.json()["error"]["code"] == "two_factor_invalid_code"


def test_disable_requires_code(
    client: TestClient, db_session: Session
) -> None:
    _register(client)
    setup = client.post("/api/v1/auth/2fa/setup").json()
    client.post(
        "/api/v1/auth/2fa/confirm",
        json={"code": totp_current_code(setup["secret"])},
    )

    bad = client.post("/api/v1/auth/2fa/disable", json={"code": "000000"})
    assert bad.status_code == 401

    good = client.post(
        "/api/v1/auth/2fa/disable",
        json={"code": totp_current_code(setup["secret"])},
    )
    assert good.status_code == 204

    user = db_session.query(User).filter(User.email == "alice@example.com").first()
    db_session.refresh(user)
    assert user.two_factor_enabled is False
    assert user.two_factor_secret_encrypted is None
