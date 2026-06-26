"""Remember-me: the refresh cookie is persistent when remembered, a browser
session cookie when not, and the choice survives token rotation."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _register(client: TestClient, email: str) -> None:
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-9", "full_name": "R"},
    )
    assert resp.status_code == 201, resp.text


def _refresh_set_cookie(resp) -> str | None:
    for key, value in resp.headers.multi_items():
        if key.lower() == "set-cookie" and value.startswith("advanta_refresh="):
            return value
    return None


def _login(client: TestClient, email: str, *, remember: bool):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct-horse-9", "remember_me": remember},
    )


def test_remember_me_true_sets_persistent_cookie(client: TestClient) -> None:
    _register(client, "rm-true@example.com")
    resp = _login(client, "rm-true@example.com", remember=True)
    assert resp.status_code == 200
    cookie = _refresh_set_cookie(resp)
    assert cookie is not None
    assert "max-age=" in cookie.lower()


def test_remember_me_false_sets_session_cookie(client: TestClient) -> None:
    _register(client, "rm-false@example.com")
    resp = _login(client, "rm-false@example.com", remember=False)
    assert resp.status_code == 200
    cookie = _refresh_set_cookie(resp)
    assert cookie is not None
    # A session cookie has neither Max-Age nor Expires → dropped on browser close.
    assert "max-age=" not in cookie.lower()
    assert "expires=" not in cookie.lower()


def test_refresh_preserves_session_cookie(client: TestClient) -> None:
    _register(client, "rm-rotate@example.com")
    _login(client, "rm-rotate@example.com", remember=False)
    token = client.cookies.get("advanta_refresh")
    assert token

    client.cookies.clear()
    resp = client.post(
        "/api/v1/auth/refresh", headers={"Cookie": f"advanta_refresh={token}"}
    )
    assert resp.status_code == 200
    cookie = _refresh_set_cookie(resp)
    assert cookie is not None
    # Rotation must not silently upgrade a non-remembered session to persistent.
    assert "max-age=" not in cookie.lower()
