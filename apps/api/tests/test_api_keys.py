"""API key tests.

Goals:
- Owner can mint a key; plaintext returned exactly once.
- Marketer cannot mint a key (owner-only).
- Programmatic access via `Authorization: ApiKey <plaintext>` works.
- A revoked key returns 401.
- A key minted in workspace A is rejected when used against workspace B.
- Effective role is the minimum of (member role, key role) — a marketer-scoped
  key can't approve high-risk recommendations even if the creator is owner.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.api_key import ApiKey
from app.models.user import User
from app.security.passwords import hash_password
from app.security.permissions import Role


def _signup(
    client: TestClient, *, email: str = "alice@example.com"
) -> tuple[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-9", "full_name": email},
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    user_id = response.json()["user"]["id"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return token, user_id


def _create_workspace(client: TestClient) -> str:
    return client.post("/api/v1/workspaces", json={"name": "Acme"}).json()["id"]


def test_owner_can_mint_key_with_plaintext_returned_once(
    client: TestClient,
) -> None:
    _signup(client)
    workspace_id = _create_workspace(client)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/api-keys",
        json={"label": "CI ingest", "role": "marketer"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["plaintext_key"].startswith("ak_")
    assert body["label"] == "CI ingest"
    assert body["role"] == "marketer"
    assert "." in body["plaintext_key"][3:]  # prefix.secret format

    listing = client.get(f"/api/v1/workspaces/{workspace_id}/api-keys").json()
    assert len(listing) == 1
    # Listing must NEVER expose plaintext.
    assert "plaintext_key" not in listing[0]


def test_api_key_authenticates_request(client: TestClient) -> None:
    _signup(client)
    workspace_id = _create_workspace(client)
    plaintext = client.post(
        f"/api/v1/workspaces/{workspace_id}/api-keys",
        json={"label": "demo", "role": "marketer"},
    ).json()["plaintext_key"]

    # Drop the bearer token; use only the API key.
    client.headers.pop("Authorization", None)
    response = client.get(
        f"/api/v1/workspaces/{workspace_id}/agents",
        headers={"Authorization": f"ApiKey {plaintext}"},
    )
    assert response.status_code == 200, response.text


def test_revoked_key_is_rejected(client: TestClient) -> None:
    _signup(client)
    workspace_id = _create_workspace(client)
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/api-keys",
        json={"label": "demo"},
    ).json()

    revoke = client.post(
        f"/api/v1/workspaces/{workspace_id}/api-keys/{created['id']}/revoke"
    )
    assert revoke.status_code == 200
    assert revoke.json()["revoked_at"] is not None

    client.headers.pop("Authorization", None)
    response = client.get(
        f"/api/v1/workspaces/{workspace_id}/agents",
        headers={"Authorization": f"ApiKey {created['plaintext_key']}"},
    )
    assert response.status_code == 401


def test_key_for_workspace_a_rejected_in_workspace_b(
    client: TestClient,
) -> None:
    _signup(client)
    ws_a = _create_workspace(client)
    ws_b = client.post("/api/v1/workspaces", json={"name": "Other"}).json()["id"]

    created = client.post(
        f"/api/v1/workspaces/{ws_a}/api-keys", json={"label": "scoped"}
    ).json()

    client.headers.pop("Authorization", None)
    response = client.get(
        f"/api/v1/workspaces/{ws_b}/agents",
        headers={"Authorization": f"ApiKey {created['plaintext_key']}"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "workspace_not_found"


def test_invalid_key_format_returns_401(client: TestClient) -> None:
    _signup(client)
    workspace_id = _create_workspace(client)

    client.headers.pop("Authorization", None)
    response = client.get(
        f"/api/v1/workspaces/{workspace_id}/agents",
        headers={"Authorization": "ApiKey not-a-real-key"},
    )
    assert response.status_code == 401


def test_api_key_call_does_not_demote_creator_role(
    client: TestClient, db_session: Session
) -> None:
    """Regression: a previous bug mutated `member.role` on the SQLAlchemy ORM
    row when an API key with a lower role was used. Any later db.commit() in
    the same request handler would persist the demoted role to
    workspace_members, permanently demoting the user.

    This test mints an admin-scoped key as an OWNER, uses it to PATCH a
    recommendation (which hits db.commit() inside recommendation_service on
    the request's session), and verifies the owner's role is still OWNER."""

    from datetime import datetime, timezone
    from app.models.agent_run import AgentRun, AgentRunStatus
    from app.models.recommendation import (
        Recommendation,
        RecommendationStatus,
        RiskLevel,
    )
    from app.models.workspace_member import WorkspaceMember

    _, user_id = _signup(client)
    workspace_id = _create_workspace(client)
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/api-keys",
        json={"label": "admin-scoped", "role": "admin"},
    ).json()

    # Seed an OPEN low-risk recommendation directly so we don't depend on the
    # agent worker to produce one. recommendation_service.edit_recommendation
    # requires ADMIN; the admin-scoped key is exactly enough.
    run = AgentRun(
        workspace_id=UUID(workspace_id),
        triggered_by_user_id=UUID(user_id),
        agent_type="onboarding_insight",
        status=AgentRunStatus.SUCCEEDED,
        input_payload={},
        model_used="deterministic",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.flush()
    rec = Recommendation(
        workspace_id=UUID(workspace_id),
        agent_run_id=run.id,
        title="Original title",
        summary="x",
        recommendation_type="onboarding.gap.brand_voice",
        risk_level=RiskLevel.LOW,
        expected_impact="x",
        suggested_action="x",
        status=RecommendationStatus.OPEN,
    )
    db_session.add(rec)
    db_session.commit()
    rec_id = rec.id

    # Drop the bearer token; use only the admin-scoped API key.
    client.headers.pop("Authorization", None)
    response = client.patch(
        f"/api/v1/workspaces/{workspace_id}/recommendations/{rec_id}",
        json={"title": "Edited title"},
        headers={"Authorization": f"ApiKey {created['plaintext_key']}"},
    )
    assert response.status_code == 200, response.text

    # The workspace member row must still be OWNER. Force a fresh read so we
    # don't get a cached object from the outer test session.
    db_session.expire_all()
    member = (
        db_session.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == UUID(workspace_id))
        .first()
    )
    assert member is not None
    assert member.role == Role.OWNER, (
        f"Owner was demoted to {member.role.value} after API-key call — "
        f"role mutation persisted from get_current_member()."
    )
