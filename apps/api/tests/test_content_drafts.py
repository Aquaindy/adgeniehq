"""Tests for the content generation pipeline.

Covers:
  * Generate via agent uses the deterministic fallback when no LLM is configured
  * Generated drafts produce real artifacts (no fabricated metrics)
  * Manual create + edit + approve + publish status flow with role gating
  * LLM path is exercised when a fake client is plugged in
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.llm.client import LlmCompletion, LlmMessage, OpenAIClient
from app.models.content_draft import ContentDraft, ContentDraftStatus, ContentDraftType
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role


def _seed_workspace(
    db: Session, *, email: str, role: Role
) -> tuple[User, Workspace]:
    user = User(
        email=email, hashed_password=hash_password("correct-horse-9"), is_active=True
    )
    db.add(user)
    db.flush()
    ws = Workspace(name="Test", slug=f"test-{email.split('@')[0]}")
    db.add(ws)
    db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=ws.id,
            user_id=user.id,
            role=role,
            status=MemberStatus.ACTIVE,
        )
    )
    db.commit()
    return user, ws


def _login(client: TestClient, email: str) -> None:
    resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-9"}
    )
    token = resp.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})


# ---------------------------------------------------------------------------
# Generate path (no LLM configured → deterministic)
# ---------------------------------------------------------------------------


def test_generate_uses_deterministic_when_no_llm_configured(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")

    # Force NullClient regardless of env.
    import app.llm.client as llm_client

    llm_client._INSTANCE = llm_client.NullClient()

    response = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts/generate",
        json={
            "type": "blog_post",
            "topic": "Why first-touch attribution misleads B2B teams",
            "keywords": ["attribution", "b2b", "marketing"],
            "audience": "demand-gen leads",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["type"] == "blog_post"
    assert body["status"] == "draft"
    assert body["source"] == "agent"
    assert body["model_used"] is None  # deterministic path doesn't claim a model
    assert "first-touch attribution" in body["title"].lower()
    assert len(body["body"]) > 200  # real content, not a placeholder
    assert "demand-gen" in body["body"].lower() or "audience" in body["body"].lower()
    assert body["agent_run_id"] is not None

    # Cleanup so other tests start fresh.
    llm_client._INSTANCE = None


def test_generate_uses_llm_when_configured(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")

    import app.llm.client as llm_client

    fake_payload = LlmCompletion(
        text='{"title": "LLM-authored", "body": "This body came from the model and is long enough to pass a sanity check.", "meta_title": "LLM authored", "meta_description": "A summary.", "keywords": ["one", "two"]}',
        model="gpt-test",
        prompt_tokens=10,
        completion_tokens=20,
    )

    fake = OpenAIClient(api_key="sk-test", model="gpt-test")

    def fake_complete(*, messages: list[LlmMessage], max_tokens: int, temperature: float):
        # Confirm we got both system + user messages.
        assert any(m.role == "system" for m in messages)
        assert any(m.role == "user" for m in messages)
        return fake_payload

    with patch.object(OpenAIClient, "complete", side_effect=fake_complete):
        llm_client._INSTANCE = fake
        try:
            response = client.post(
                f"/api/v1/workspaces/{ws.id}/content-drafts/generate",
                json={"type": "blog_post", "topic": "Anything"},
            )
        finally:
            llm_client._INSTANCE = None

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "LLM-authored"
    assert "model" in body["body"].lower()
    assert body["model_used"] == "gpt-test"
    assert body["seo_metadata"]["meta_title"] == "LLM authored"
    assert body["keywords"] == ["one", "two"]


def test_generate_rejects_unknown_type(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")

    response = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts/generate",
        json={"type": "haiku", "topic": "spring"},
    )
    assert response.status_code == 422  # pydantic enum validation


# ---------------------------------------------------------------------------
# Manual create + edit
# ---------------------------------------------------------------------------


def test_create_manual_then_edit(client: TestClient, db_session: Session) -> None:
    user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")

    create_resp = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts",
        json={
            "type": "ad_copy",
            "title": "Tighter pricing page CTA",
            "body": "Headline: Get a quote in 24 hours\nDescription: Custom pricing, real specifics.",
            "keywords": ["quote", "custom"],
        },
    )
    assert create_resp.status_code == 200
    draft_id = create_resp.json()["id"]
    assert create_resp.json()["source"] == "manual"
    assert create_resp.json()["agent_run_id"] is None

    update_resp = client.patch(
        f"/api/v1/workspaces/{ws.id}/content-drafts/{draft_id}",
        json={"title": "Pricing page CTA — round 2"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["title"] == "Pricing page CTA — round 2"


# ---------------------------------------------------------------------------
# Status flow
# ---------------------------------------------------------------------------


def test_marketer_cannot_approve_draft(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed_workspace(
        db_session, email="alice@example.com", role=Role.MARKETER
    )
    _login(client, "alice@example.com")
    create_resp = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts",
        json={"type": "social_post", "title": "T", "body": "B"},
    )
    draft_id = create_resp.json()["id"]
    approve_resp = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts/{draft_id}/approve"
    )
    assert approve_resp.status_code == 403


def test_admin_can_approve_then_publish(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.ADMIN)
    _login(client, "alice@example.com")
    create_resp = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts",
        json={"type": "blog_post", "title": "T", "body": "Body."},
    )
    draft_id = create_resp.json()["id"]

    # Cannot publish a draft that is not yet approved.
    publish_first = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts/{draft_id}/publish"
    )
    assert publish_first.status_code == 409

    approve_resp = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts/{draft_id}/approve"
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"
    assert approve_resp.json()["approved_by"] is not None

    publish_resp = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts/{draft_id}/publish",
        json={"publication_url": "https://example.com/blog/post"},
    )
    assert publish_resp.status_code == 200
    body = publish_resp.json()
    assert body["status"] == "published"
    assert body["published_at"] is not None
    assert body["target_url"] == "https://example.com/blog/post"


def test_published_drafts_cannot_be_edited(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")
    create_resp = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts",
        json={"type": "blog_post", "title": "T", "body": "B"},
    )
    draft_id = create_resp.json()["id"]
    client.post(f"/api/v1/workspaces/{ws.id}/content-drafts/{draft_id}/approve")
    client.post(f"/api/v1/workspaces/{ws.id}/content-drafts/{draft_id}/publish")

    edit_resp = client.patch(
        f"/api/v1/workspaces/{ws.id}/content-drafts/{draft_id}",
        json={"title": "no"},
    )
    assert edit_resp.status_code == 409
    assert edit_resp.json()["error"]["code"] == "invalid_draft_state"


def test_workspace_isolation(client: TestClient, db_session: Session) -> None:
    user_a, ws_a = _seed_workspace(
        db_session, email="alice@example.com", role=Role.OWNER
    )
    user_b, ws_b = _seed_workspace(
        db_session, email="bob@example.com", role=Role.OWNER
    )
    _login(client, "alice@example.com")
    create_resp = client.post(
        f"/api/v1/workspaces/{ws_a.id}/content-drafts",
        json={"type": "blog_post", "title": "T", "body": "B"},
    )
    draft_id = create_resp.json()["id"]
    _login(client, "bob@example.com")
    fetch = client.get(
        f"/api/v1/workspaces/{ws_b.id}/content-drafts/{draft_id}"
    )
    assert fetch.status_code == 404
