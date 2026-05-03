"""CMS publish webhook.

Pins the contract:
  * Admin can configure publish_webhook_url + secret on a workspace
  * GET returns the URL but never the plaintext secret (only `has_secret`)
  * Publishing an approved draft POSTs the draft to the configured URL with
    Authorization: Bearer <secret>
  * The receiver's `published_url` in the response body lands as the draft's
    target_url
  * Receiver failure (4xx/5xx, timeout) surfaces as 502; the draft is NOT
    flipped to PUBLISHED so the user can retry
  * Manual-only mode (no webhook configured) still works as before
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role


def _seed_workspace(
    db: Session, *, email: str, role: Role = Role.OWNER
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


def _create_approved_draft(client: TestClient, ws_id) -> str:
    create = client.post(
        f"/api/v1/workspaces/{ws_id}/content-drafts",
        json={"type": "blog_post", "title": "T", "body": "Body"},
    )
    draft_id = create.json()["id"]
    approve = client.post(
        f"/api/v1/workspaces/{ws_id}/content-drafts/{draft_id}/approve"
    )
    assert approve.status_code == 200, approve.text
    return draft_id


# ---------------------------------------------------------------------------
# Settings endpoints
# ---------------------------------------------------------------------------


def test_get_webhook_settings_default_empty(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    resp = client.get(f"/api/v1/workspaces/{ws.id}/publish-webhook")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"publish_webhook_url": None, "has_secret": False}


def test_set_webhook_persists_url_and_encrypts_secret(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")

    resp = client.patch(
        f"/api/v1/workspaces/{ws.id}/publish-webhook",
        json={
            "publish_webhook_url": "https://cms.example.com/inbound",
            "publish_webhook_secret": "shh-this-is-secret",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["publish_webhook_url"] == "https://cms.example.com/inbound"
    assert body["has_secret"] is True

    # GET must never expose the plaintext.
    fetch = client.get(f"/api/v1/workspaces/{ws.id}/publish-webhook")
    assert "secret" not in fetch.text.lower() or "has_secret" in fetch.text
    assert "shh-this-is-secret" not in fetch.text

    # And the column actually holds an encrypted value (not plaintext).
    db_session.refresh(ws)
    assert ws.encrypted_publish_webhook_secret is not None
    assert ws.encrypted_publish_webhook_secret != "shh-this-is-secret"


def test_marketer_cannot_configure_webhook(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(
        db_session, email="alice@example.com", role=Role.MARKETER
    )
    _login(client, "alice@example.com")
    resp = client.patch(
        f"/api/v1/workspaces/{ws.id}/publish-webhook",
        json={"publish_webhook_url": "https://x.com/y"},
    )
    assert resp.status_code == 403


def test_invalid_url_rejected(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    resp = client.patch(
        f"/api/v1/workspaces/{ws.id}/publish-webhook",
        json={"publish_webhook_url": "ftp://nope.example.com"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_webhook_url"


# ---------------------------------------------------------------------------
# Publish flow
# ---------------------------------------------------------------------------


def test_publish_with_webhook_posts_draft_and_records_returned_url(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")

    client.patch(
        f"/api/v1/workspaces/{ws.id}/publish-webhook",
        json={
            "publish_webhook_url": "https://cms.example.com/inbound",
            "publish_webhook_secret": "test-secret",
        },
    )
    draft_id = _create_approved_draft(client, ws.id)

    captured: dict = {}

    class _FakeResponse:
        def __init__(self):
            self.status_code = 200
            self.content = b'{"published_url": "https://cms.example.com/posts/abc"}'
            self.text = self.content.decode()

        def json(self):
            return {"published_url": "https://cms.example.com/posts/abc"}

    def fake_post(url, headers=None, json=None, **kw):
        captured["url"] = url
        captured["headers"] = headers or {}
        captured["body"] = json
        return _FakeResponse()

    with patch(
        "app.services.publish_webhook.httpx.post", side_effect=fake_post
    ):
        publish = client.post(
            f"/api/v1/workspaces/{ws.id}/content-drafts/{draft_id}/publish"
        )
    assert publish.status_code == 200, publish.text
    body = publish.json()
    assert body["status"] == "published"
    assert body["target_url"] == "https://cms.example.com/posts/abc"

    # The webhook call carried the draft body + secret.
    assert captured["url"] == "https://cms.example.com/inbound"
    assert captured["headers"].get("Authorization") == "Bearer test-secret"
    assert captured["body"]["draft_id"] == draft_id
    assert captured["body"]["title"] == "T"
    assert captured["body"]["body"] == "Body"


def test_publish_falls_back_to_manual_when_webhook_not_configured(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    draft_id = _create_approved_draft(client, ws.id)

    with patch(
        "app.services.publish_webhook.httpx.post",
        side_effect=AssertionError("webhook must not be called when not configured"),
    ):
        publish = client.post(
            f"/api/v1/workspaces/{ws.id}/content-drafts/{draft_id}/publish",
            json={"publication_url": "https://example.com/manual"},
        )
    assert publish.status_code == 200
    assert publish.json()["target_url"] == "https://example.com/manual"


def test_explicit_publication_url_skips_webhook(
    client: TestClient, db_session: Session
) -> None:
    """If the caller passes publication_url explicitly, we record it and
    DON'T fire the webhook — the user is telling us they handled
    publication out of band."""

    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    client.patch(
        f"/api/v1/workspaces/{ws.id}/publish-webhook",
        json={
            "publish_webhook_url": "https://cms.example.com/inbound",
            "publish_webhook_secret": "test-secret",
        },
    )
    draft_id = _create_approved_draft(client, ws.id)

    with patch(
        "app.services.publish_webhook.httpx.post",
        side_effect=AssertionError("webhook must not run when explicit URL given"),
    ):
        publish = client.post(
            f"/api/v1/workspaces/{ws.id}/content-drafts/{draft_id}/publish",
            json={"publication_url": "https://override.example.com/post"},
        )
    assert publish.status_code == 200
    assert publish.json()["target_url"] == "https://override.example.com/post"


def test_webhook_failure_keeps_draft_in_approved_state(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    client.patch(
        f"/api/v1/workspaces/{ws.id}/publish-webhook",
        json={
            "publish_webhook_url": "https://cms.example.com/inbound",
            "publish_webhook_secret": "test-secret",
        },
    )
    draft_id = _create_approved_draft(client, ws.id)

    class _FailResponse:
        status_code = 502
        content = b"upstream timeout"
        text = "upstream timeout"

        def json(self):  # noqa: D401
            return {}

    with patch(
        "app.services.publish_webhook.httpx.post", return_value=_FailResponse()
    ):
        publish = client.post(
            f"/api/v1/workspaces/{ws.id}/content-drafts/{draft_id}/publish"
        )
    assert publish.status_code == 502
    assert publish.json()["error"]["code"] == "publish_webhook_failed"

    # Draft is still APPROVED so the user can fix the receiver and retry.
    fetch = client.get(
        f"/api/v1/workspaces/{ws.id}/content-drafts/{draft_id}"
    )
    assert fetch.json()["status"] == "approved"


def test_webhook_returning_no_url_still_marks_published(
    client: TestClient, db_session: Session
) -> None:
    """If the receiver does the publish but doesn't expose the URL, we still
    flip status to PUBLISHED — the receiver succeeded by returning 200."""

    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    client.patch(
        f"/api/v1/workspaces/{ws.id}/publish-webhook",
        json={"publish_webhook_url": "https://cms.example.com/inbound"},
    )
    draft_id = _create_approved_draft(client, ws.id)

    class _OkNoBody:
        status_code = 200
        content = b""
        text = ""

        def json(self):  # noqa: D401
            return {}

    with patch(
        "app.services.publish_webhook.httpx.post", return_value=_OkNoBody()
    ):
        publish = client.post(
            f"/api/v1/workspaces/{ws.id}/content-drafts/{draft_id}/publish"
        )
    assert publish.status_code == 200
    body = publish.json()
    assert body["status"] == "published"
    # No published_url returned → target_url stays None.
    assert body["target_url"] is None
