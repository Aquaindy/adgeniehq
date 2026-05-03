from fastapi.testclient import TestClient


def _register(client: TestClient, email: str, password: str = "correct-horse-9") -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Test User"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_register_returns_access_token_and_sets_refresh_cookie(client: TestClient) -> None:
    body = _register(client, "owner@example.com")

    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert body["user"]["email"] == "owner@example.com"
    assert body["user"]["full_name"] == "Test User"
    assert "advanta_refresh" in client.cookies


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    _register(client, "dup@example.com")
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "dup@example.com", "password": "another-pass-1"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_already_registered"


def test_register_validates_password_length(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "short@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_login_with_correct_password(client: TestClient) -> None:
    _register(client, "login@example.com", "supersecret-1")
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "supersecret-1"},
    )
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "login@example.com"
    assert "advanta_refresh" in client.cookies


def test_login_rejects_wrong_password(client: TestClient) -> None:
    _register(client, "wrong@example.com", "supersecret-1")
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "wrong@example.com", "password": "WRONG-pass-1"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_returns_user_with_bearer(client: TestClient) -> None:
    body = _register(client, "me@example.com")
    token = body["access_token"]

    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"


def test_refresh_rotates_token_and_clears_on_logout(client: TestClient) -> None:
    body = _register(client, "rotate@example.com")
    initial_refresh = client.cookies.get("advanta_refresh")
    assert initial_refresh

    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    new_body = response.json()
    assert new_body["access_token"] != body["access_token"]
    assert client.cookies.get("advanta_refresh") != initial_refresh

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 204


def test_refresh_without_cookie_returns_401(client: TestClient) -> None:
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "refresh_not_provided"
