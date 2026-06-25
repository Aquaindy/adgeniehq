from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.integrations.base import ProviderAccountInfo, ProviderTokens
from app.security.encryption import decrypt, encrypt
from app.security.oauth_state import InvalidStateError, issue_state, parse_state


# ---------------------------------------------------------------------------
# Encryption + state helpers
# ---------------------------------------------------------------------------


def test_encryption_roundtrip() -> None:
    plaintext = "ya29.real-google-token-shape-here"
    cipher = encrypt(plaintext)
    assert cipher != plaintext
    assert decrypt(cipher) == plaintext


def test_oauth_state_roundtrip() -> None:
    from uuid import uuid4

    ws = uuid4()
    user = uuid4()
    token = issue_state(workspace_id=ws, user_id=user, provider="google_ads")
    payload = parse_state(token)
    assert payload["ws"] == str(ws)
    assert payload["uid"] == str(user)
    assert payload["p"] == "google_ads"


def test_oauth_state_rejects_garbage() -> None:
    with pytest.raises(InvalidStateError):
        parse_state("not-a-jwt")


def test_oauth_state_is_single_use(db_session) -> None:
    """A state token can be consumed exactly once — a replay (e.g. a leaked
    code+state pair) is rejected even within its TTL."""
    from app.models.connected_account import ConnectionStatus
    from app.models.user import User
    from app.models.workspace import Workspace
    from app.models.workspace_member import WorkspaceMember
    from app.security.passwords import hash_password
    from app.security.permissions import MemberStatus, Role
    from app.services import integration_service

    user = User(
        email="oauth-su@example.com",
        hashed_password=hash_password("correct-horse-9"),
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    ws = Workspace(name="W", slug="w-oauth-su")
    db_session.add(ws)
    db_session.flush()
    db_session.add(
        WorkspaceMember(
            workspace_id=ws.id, user_id=user.id, role=Role.OWNER, status=MemberStatus.ACTIVE
        )
    )
    db_session.commit()

    state = issue_state(workspace_id=ws.id, user_id=user.id, provider="google_ads")

    # First use: the provider "denied" so we hit the error branch (no network
    # exchange) — but the state is still consumed.
    _, _, status, _ = integration_service.handle_oauth_callback(
        db_session, provider_id="google_ads", code=None, state_token=state, error="access_denied"
    )
    assert status == ConnectionStatus.ERROR
    db_session.commit()

    # Replaying the same state is now rejected.
    with pytest.raises(InvalidStateError):
        integration_service.handle_oauth_callback(
            db_session, provider_id="google_ads", code=None, state_token=state, error="access_denied"
        )


# ---------------------------------------------------------------------------
# Helpers for the rest of the file
# ---------------------------------------------------------------------------


def _signup_and_workspace(client: TestClient, email: str = "alice@example.com") -> str:
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-9", "full_name": "Alice"},
    )
    token = register.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client.post("/api/v1/workspaces", json={"name": "Acme"}).json()["id"]


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def test_list_integrations_returns_all_providers_disconnected(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client)
    response = client.get(f"/api/v1/workspaces/{workspace_id}/integrations")
    assert response.status_code == 200
    body = response.json()
    providers = {entry["provider"] for entry in body}
    assert providers == {
        "google_ads",
        "meta_ads",
        "linkedin_ads",
        "google_analytics",
        "google_search_console",
    }
    assert all(entry["status"] == "disconnected" for entry in body)
    # Without env vars, none of the providers are "configured"
    assert all(entry["configured"] is False for entry in body)


# ---------------------------------------------------------------------------
# Connect URL
# ---------------------------------------------------------------------------


def test_connect_url_503_when_provider_unconfigured(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client)
    response = client.get(
        f"/api/v1/workspaces/{workspace_id}/integrations/google_ads/connect-url"
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_not_configured"


def test_connect_url_404_for_unknown_provider(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client)
    response = client.get(
        f"/api/v1/workspaces/{workspace_id}/integrations/madeup_provider/connect-url"
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_provider"


def test_connect_url_succeeds_when_credentials_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")

    workspace_id = _signup_and_workspace(client)
    response = client.get(
        f"/api/v1/workspaces/{workspace_id}/integrations/google_ads/connect-url"
    )
    assert response.status_code == 200
    body = response.json()
    assert "accounts.google.com" in body["authorization_url"]
    assert "google_ads/callback" in body["redirect_uri"]
    assert body["state"]


# ---------------------------------------------------------------------------
# Write-scope at connect-time
# ---------------------------------------------------------------------------


def test_scopes_for_mode_drops_write_scopes() -> None:
    from app.integrations.meta_ads import MetaAdsProvider

    full = MetaAdsProvider.scopes_for_mode("write")
    read = MetaAdsProvider.scopes_for_mode("read")
    assert "ads_management" in full  # the write scope
    assert "ads_management" not in read
    assert "ads_read" in read  # read scopes preserved


def test_connect_url_scope_mode_read_vs_write(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("META_APP_ID", "x")
    monkeypatch.setenv("META_APP_SECRET", "y")
    ws = _signup_and_workspace(client)
    read = client.get(
        f"/api/v1/workspaces/{ws}/integrations/meta_ads/connect-url?scope_mode=read"
    )
    assert read.status_code == 200
    assert "ads_management" not in read.json()["authorization_url"]
    write = client.get(
        f"/api/v1/workspaces/{ws}/integrations/meta_ads/connect-url?scope_mode=write"
    )
    assert "ads_management" in write.json()["authorization_url"]


def test_connect_url_rejects_bad_scope_mode(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("META_APP_ID", "x")
    monkeypatch.setenv("META_APP_SECRET", "y")
    ws = _signup_and_workspace(client)
    resp = client.get(
        f"/api/v1/workspaces/{ws}/integrations/meta_ads/connect-url?scope_mode=bogus"
    )
    assert resp.status_code == 422


def test_integration_status_can_write_reflects_scopes(client: TestClient, db_session) -> None:
    from uuid import UUID

    from app.models.connected_account import ConnectedAccount, ConnectionStatus

    ws = _signup_and_workspace(client)
    acct = ConnectedAccount(
        workspace_id=UUID(ws),
        provider="meta_ads",
        status=ConnectionStatus.CONNECTED,
        scopes=["ads_read", "ads_management"],
        connected_at=datetime.now(timezone.utc),
    )
    db_session.add(acct)
    db_session.commit()

    body = client.get(f"/api/v1/workspaces/{ws}/integrations").json()
    meta = next(e for e in body if e["provider"] == "meta_ads")
    assert meta["can_write"] is True
    assert "ads_management" in meta["write_scopes"]

    # Drop the write scope → read-only.
    acct.scopes = ["ads_read"]
    db_session.commit()
    body2 = client.get(f"/api/v1/workspaces/{ws}/integrations").json()
    meta2 = next(e for e in body2 if e["provider"] == "meta_ads")
    assert meta2["can_write"] is False


# ---------------------------------------------------------------------------
# Callback (mocked HTTP)
# ---------------------------------------------------------------------------


def test_callback_full_flow_with_mocked_provider(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")

    workspace_id = _signup_and_workspace(client)
    me = client.get("/api/v1/auth/me").json()
    user_id = me["id"]

    state = issue_state(
        workspace_id=__import__("uuid").UUID(workspace_id),
        user_id=__import__("uuid").UUID(user_id),
        provider="google_ads",
    )

    fake_tokens = ProviderTokens(
        access_token="ya29.fake-access",
        refresh_token="1//fake-refresh",
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=3600),
        scopes=["openid", "https://www.googleapis.com/auth/adwords"],
        raw=None,
    )
    fake_info = ProviderAccountInfo(
        provider_account_id="123456789",
        display_name="Alice via Google",
    )

    with patch(
        "app.integrations.google_ads.GoogleAdsProvider.exchange_code", return_value=fake_tokens
    ), patch(
        "app.integrations.google_ads.GoogleAdsProvider.fetch_account_info",
        return_value=fake_info,
    ):
        response = client.get(
            "/api/v1/integrations/google_ads/callback",
            params={"code": "auth-code-here", "state": state},
            follow_redirects=False,
        )

    # Backend redirects back to the frontend Integrations Center on success.
    assert response.status_code in (302, 307)
    assert "/integrations" in response.headers["location"]
    assert "status=success" in response.headers["location"]

    listing = client.get(f"/api/v1/workspaces/{workspace_id}/integrations").json()
    google_ads = next(e for e in listing if e["provider"] == "google_ads")
    assert google_ads["status"] == "connected"
    assert google_ads["display_account_name"] == "Alice via Google"
    assert google_ads["provider_account_id"] == "123456789"


def test_callback_redirects_with_error_on_provider_denial(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")

    workspace_id = _signup_and_workspace(client)
    me = client.get("/api/v1/auth/me").json()

    state = issue_state(
        workspace_id=__import__("uuid").UUID(workspace_id),
        user_id=__import__("uuid").UUID(me["id"]),
        provider="google_ads",
    )

    response = client.get(
        "/api/v1/integrations/google_ads/callback",
        params={
            "state": state,
            "error": "access_denied",
            "error_description": "User denied the request.",
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "status=error" in response.headers["location"]

    listing = client.get(f"/api/v1/workspaces/{workspace_id}/integrations").json()
    google_ads = next(e for e in listing if e["provider"] == "google_ads")
    assert google_ads["status"] == "error"
    assert "denied" in (google_ads["last_error"] or "")


def test_callback_400_with_garbage_state(client: TestClient) -> None:
    # Even pointing at an unknown state shouldn't return 200 with success
    response = client.get(
        "/api/v1/integrations/google_ads/callback",
        params={"code": "x", "state": "garbage"},
        follow_redirects=False,
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Disconnect + sync
# ---------------------------------------------------------------------------


def test_disconnect_drops_token_and_audits(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")

    workspace_id = _signup_and_workspace(client)
    me = client.get("/api/v1/auth/me").json()

    state = issue_state(
        workspace_id=__import__("uuid").UUID(workspace_id),
        user_id=__import__("uuid").UUID(me["id"]),
        provider="google_ads",
    )

    fake_tokens = ProviderTokens(
        access_token="ya29.fake",
        refresh_token=None,
        expires_at=None,
        scopes=None,
    )
    with patch(
        "app.integrations.google_ads.GoogleAdsProvider.exchange_code", return_value=fake_tokens
    ), patch(
        "app.integrations.google_ads.GoogleAdsProvider.fetch_account_info",
        return_value=ProviderAccountInfo(provider_account_id="x", display_name="X"),
    ):
        client.get(
            "/api/v1/integrations/google_ads/callback",
            params={"code": "c", "state": state},
            follow_redirects=False,
        )

    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/integrations/google_ads/disconnect"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "disconnected"


def test_sync_409_when_not_connected(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/integrations/google_ads/sync"
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "account_not_connected"


def test_sync_records_succeeded_log_when_connected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")

    workspace_id = _signup_and_workspace(client)
    me = client.get("/api/v1/auth/me").json()
    state = issue_state(
        workspace_id=__import__("uuid").UUID(workspace_id),
        user_id=__import__("uuid").UUID(me["id"]),
        provider="google_ads",
    )

    fake_tokens = ProviderTokens(
        access_token="ya29.fake", refresh_token=None, expires_at=None, scopes=None
    )
    with patch(
        "app.integrations.google_ads.GoogleAdsProvider.exchange_code", return_value=fake_tokens
    ), patch(
        "app.integrations.google_ads.GoogleAdsProvider.fetch_account_info",
        return_value=ProviderAccountInfo(provider_account_id="x", display_name="X"),
    ):
        client.get(
            "/api/v1/integrations/google_ads/callback",
            params={"code": "c", "state": state},
            follow_redirects=False,
        )

    with patch(
        "app.integrations.google_ads.GoogleAdsProvider.fetch_account_info",
        return_value=ProviderAccountInfo(provider_account_id="x", display_name="X"),
    ):
        sync = client.post(
            f"/api/v1/workspaces/{workspace_id}/integrations/google_ads/sync"
        )
    assert sync.status_code == 201
    body = sync.json()
    assert body["status"] == "succeeded"
    assert body["error_message"] is None
    assert body["completed_at"] is not None

    listing = client.get(f"/api/v1/workspaces/{workspace_id}/integrations").json()
    google_ads = next(e for e in listing if e["provider"] == "google_ads")
    assert google_ads["last_sync_at"] is not None
    assert len(google_ads["recent_syncs"]) == 1
