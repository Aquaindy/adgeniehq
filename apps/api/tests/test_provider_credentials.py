"""BYOK provider credentials tests.

Goals:
- Admin can add an OpenAI/Anthropic/Google AI credential.
- Plaintext is encrypted at rest (raw row != plaintext) and only `last_four`
  is exposed in responses.
- One active credential per (workspace, provider) — re-adding revokes prior.
- Marketer cannot add (admin+ only).
- Workspace isolation: can't list/test/revoke a credential from another ws.
- get_secret_or_none + get_llm_client_for_workspace honor the saved key.
- Test endpoint stamps last_test_status without leaking the secret.
"""

from __future__ import annotations

import os
from typing import Any
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# Provide a usable Fernet key before any app code runs that touches encryption.
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))


def _signup(
    client: TestClient, *, email: str = "admin@example.com"
) -> tuple[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-9", "full_name": email},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    client.headers.update({"Authorization": f"Bearer {body['access_token']}"})
    return body["access_token"], body["user"]["id"]


def _create_workspace(client: TestClient, name: str = "Acme") -> str:
    return client.post("/api/v1/workspaces", json={"name": name}).json()["id"]


# ---------------------------------------------------------------------------
# Happy path: add → list → test → revoke
# ---------------------------------------------------------------------------


def test_admin_can_add_credential_and_list_excludes_secret(
    client: TestClient,
) -> None:
    _signup(client)
    workspace_id = _create_workspace(client)

    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/provider-credentials",
        json={
            "provider": "openai",
            "secret": "sk-test-abcdefghijklmnop",
            "label": "Acme prod",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["provider"] == "openai"
    assert body["label"] == "Acme prod"
    # last_four is the cosmetic hint; plaintext must NEVER appear.
    assert body["last_four"] == "mnop"
    assert "secret" not in body
    assert "encrypted_secret" not in body

    listing = client.get(
        f"/api/v1/workspaces/{workspace_id}/provider-credentials"
    ).json()
    assert len(listing) == 1
    assert "secret" not in listing[0]
    assert listing[0]["last_four"] == "mnop"


def test_secret_is_fernet_encrypted_at_rest(
    client: TestClient, db_session: Session
) -> None:
    from app.models.provider_credential import ProviderCredential

    _signup(client)
    workspace_id = _create_workspace(client)
    plaintext = "sk-test-abcdefghijklmnop"
    client.post(
        f"/api/v1/workspaces/{workspace_id}/provider-credentials",
        json={"provider": "openai", "secret": plaintext},
    )
    cred = db_session.query(ProviderCredential).first()
    assert cred is not None
    assert cred.encrypted_secret != plaintext
    assert plaintext not in cred.encrypted_secret


# ---------------------------------------------------------------------------
# One active per (workspace, provider) — replace by adding again
# ---------------------------------------------------------------------------


def test_re_adding_same_provider_revokes_prior(client: TestClient) -> None:
    _signup(client)
    workspace_id = _create_workspace(client)
    first = client.post(
        f"/api/v1/workspaces/{workspace_id}/provider-credentials",
        json={"provider": "openai", "secret": "sk-test-firstkeyxxxxxxx"},
    ).json()
    second = client.post(
        f"/api/v1/workspaces/{workspace_id}/provider-credentials",
        json={"provider": "openai", "secret": "sk-test-secondkeyxxxxxxx"},
    ).json()
    assert first["id"] != second["id"]

    listing = client.get(
        f"/api/v1/workspaces/{workspace_id}/provider-credentials"
    ).json()
    active = [c for c in listing if c["revoked_at"] is None]
    assert len(active) == 1
    assert active[0]["id"] == second["id"]


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


def test_marketer_cannot_add_credential(client: TestClient) -> None:
    _signup(client, email="owner@example.com")
    workspace_id = _create_workspace(client)

    # Demote ourselves to marketer by inviting a second user as owner — easier
    # path: directly set the role on the WorkspaceMember row.
    from app.models.workspace_member import WorkspaceMember
    from app.security.permissions import Role
    from tests.conftest import TestSessionLocal

    s = TestSessionLocal()
    try:
        member = (
            s.query(WorkspaceMember)
            .filter(WorkspaceMember.workspace_id == UUID(workspace_id))
            .first()
        )
        member.role = Role.MARKETER
        s.commit()
    finally:
        s.close()

    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/provider-credentials",
        json={"provider": "openai", "secret": "sk-test-abcdefghijklmnop"},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Workspace isolation
# ---------------------------------------------------------------------------


def test_credential_isolated_to_workspace(client: TestClient) -> None:
    _signup(client)
    ws_a = _create_workspace(client, name="Workspace A")
    ws_b = _create_workspace(client, name="Workspace B")

    cred = client.post(
        f"/api/v1/workspaces/{ws_a}/provider-credentials",
        json={"provider": "openai", "secret": "sk-test-abcdefghijklmnop"},
    ).json()

    # Listing the OTHER workspace must not include this credential.
    other_listing = client.get(
        f"/api/v1/workspaces/{ws_b}/provider-credentials"
    ).json()
    assert other_listing == []

    # Revoking via the wrong workspace path should 404 — same id is not
    # findable when scoped to ws_b.
    response = client.delete(
        f"/api/v1/workspaces/{ws_b}/provider-credentials/{cred['id']}"
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Revoke
# ---------------------------------------------------------------------------


def test_revoke_marks_credential_revoked(client: TestClient) -> None:
    _signup(client)
    workspace_id = _create_workspace(client)
    cred = client.post(
        f"/api/v1/workspaces/{workspace_id}/provider-credentials",
        json={"provider": "anthropic", "secret": "sk-ant-test-keyxxxxxx"},
    ).json()

    response = client.delete(
        f"/api/v1/workspaces/{workspace_id}/provider-credentials/{cred['id']}"
    )
    assert response.status_code == 200, response.text
    assert response.json()["revoked_at"] is not None


# ---------------------------------------------------------------------------
# get_secret_or_none + workspace-aware client routing
# ---------------------------------------------------------------------------


def test_get_secret_returns_decrypted_plaintext(
    client: TestClient, db_session: Session
) -> None:
    from app.models.provider_credential import ProviderCredentialProvider
    from app.services import provider_credentials_service

    _signup(client)
    workspace_id = _create_workspace(client)
    plaintext = "sk-test-aaabbbcccdddeee1"
    client.post(
        f"/api/v1/workspaces/{workspace_id}/provider-credentials",
        json={"provider": "openai", "secret": plaintext},
    )

    db_session.expire_all()
    secret = provider_credentials_service.get_secret_or_none(
        db_session,
        workspace_id=UUID(workspace_id),
        provider=ProviderCredentialProvider.OPENAI,
    )
    assert secret == plaintext


def test_workspace_aware_client_uses_byok_key(
    client: TestClient, db_session: Session
) -> None:
    from app.llm.client import OpenAIClient, get_llm_client_for_workspace

    _signup(client)
    workspace_id = _create_workspace(client)
    client.post(
        f"/api/v1/workspaces/{workspace_id}/provider-credentials",
        json={"provider": "openai", "secret": "sk-test-byok-keyxxxxxxxx"},
    )

    db_session.expire_all()
    chosen = get_llm_client_for_workspace(db_session, UUID(workspace_id))
    assert isinstance(chosen, OpenAIClient)
    assert chosen.api_key == "sk-test-byok-keyxxxxxxxx"


def test_workspace_aware_client_falls_back_to_env(
    client: TestClient, db_session: Session
) -> None:
    """No saved credential -> the env-default singleton is used."""
    from app.llm.client import get_llm_client, get_llm_client_for_workspace

    _signup(client)
    workspace_id = _create_workspace(client)

    # Sanity: no credentials added.
    listing = client.get(
        f"/api/v1/workspaces/{workspace_id}/provider-credentials"
    ).json()
    assert listing == []

    chosen = get_llm_client_for_workspace(db_session, UUID(workspace_id))
    # Identity-equal to the env-default singleton.
    assert chosen is get_llm_client()


# ---------------------------------------------------------------------------
# Test endpoint stamps a result without exposing the secret
# ---------------------------------------------------------------------------


def test_test_endpoint_records_status(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signup(client)
    workspace_id = _create_workspace(client)
    cred = client.post(
        f"/api/v1/workspaces/{workspace_id}/provider-credentials",
        json={"provider": "openai", "secret": "sk-test-pingkeyxxxxxxxxx"},
    ).json()

    # Fake the provider ping so no real HTTP request is made.
    captured: dict[str, Any] = {}

    def fake_ping(provider, secret):  # type: ignore[no-untyped-def]
        captured["provider"] = provider
        captured["secret"] = secret
        return True, None

    from app.services import provider_credentials_service as svc

    monkeypatch.setattr(svc, "_ping_provider", fake_ping)

    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/provider-credentials/{cred['id']}/test"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["last_test_status"] == "ok"
    assert body["last_test_error"] is None
    # The secret was decrypted and forwarded to the ping helper, but never
    # surfaces in the response body.
    assert captured["secret"] == "sk-test-pingkeyxxxxxxxxx"
    assert "secret" not in body
