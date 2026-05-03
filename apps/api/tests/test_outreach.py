"""Tests for the backlink outreach pipeline.

Covers:
  * Domain normalization + duplicate detection
  * Drafting an email uses deterministic fallback when no LLM is configured
  * Send is admin-only and refuses to send unapproved drafts
  * Send routes through email_service.send_email; failures get persisted as
    `failed` so the user knows nothing went out
  * Successful send flips the prospect to `contacted` and the email to `sent`
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.backlink_prospect import BacklinkProspect, ProspectStatus
from app.models.outreach_email import OutreachEmail, OutreachEmailStatus
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
# Prospects
# ---------------------------------------------------------------------------


def test_create_prospect_normalizes_domain(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")

    response = client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects",
        json={
            "domain": "https://www.Example.COM/some/page",
            "contact_email": "  Editor@Example.com  ",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["domain"] == "example.com"
    assert body["contact_email"] == "editor@example.com"


def test_duplicate_domain_in_workspace_rejected(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")
    client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects",
        json={"domain": "techcrunch.com"},
    )
    second = client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects",
        json={"domain": "techcrunch.com"},
    )
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "invalid_prospect"


def test_invalid_domain_rejected(client: TestClient, db_session: Session) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects",
        json={"domain": "not a domain"},
    )
    assert response.status_code == 400


def test_workspace_isolation_for_prospects(
    client: TestClient, db_session: Session
) -> None:
    _, ws_a = _seed_workspace(
        db_session, email="alice@example.com", role=Role.OWNER
    )
    _, ws_b = _seed_workspace(db_session, email="bob@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")
    create = client.post(
        f"/api/v1/workspaces/{ws_a.id}/backlink-prospects",
        json={"domain": "example.com"},
    )
    pid = create.json()["id"]
    _login(client, "bob@example.com")
    fetch = client.get(
        f"/api/v1/workspaces/{ws_b.id}/backlink-prospects/{pid}"
    )
    assert fetch.status_code == 404


# ---------------------------------------------------------------------------
# Drafting
# ---------------------------------------------------------------------------


def test_draft_email_uses_deterministic_when_no_llm(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")

    create = client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects",
        json={
            "domain": "example.com",
            "contact_name": "Sam Editor",
            "contact_email": "sam@example.com",
        },
    )
    pid = create.json()["id"]

    import app.llm.client as llm_client

    llm_client._INSTANCE = llm_client.NullClient()
    try:
        draft = client.post(
            f"/api/v1/workspaces/{ws.id}/backlink-prospects/{pid}/draft-email",
            json={"angle": "AI growth tooling"},
        )
    finally:
        llm_client._INSTANCE = None

    assert draft.status_code == 200, draft.text
    body = draft.json()
    assert body["status"] == "draft"
    assert body["source"] == "deterministic"
    assert "Sam Editor" in body["body"] or "Hi Sam" in body["body"]
    assert "AI growth tooling" in body["body"]
    assert body["to_email"] == "sam@example.com"
    assert body["model_used"] is None


def test_draft_email_requires_contact_email(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")
    create = client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects",
        json={"domain": "example.com"},  # no email
    )
    pid = create.json()["id"]
    draft = client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects/{pid}/draft-email",
        json={},
    )
    assert draft.status_code == 400
    assert draft.json()["error"]["code"] == "invalid_prospect"


# ---------------------------------------------------------------------------
# Approval + send
# ---------------------------------------------------------------------------


def test_marketer_cannot_approve_or_send(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(
        db_session, email="alice@example.com", role=Role.MARKETER
    )
    _login(client, "alice@example.com")
    create = client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects",
        json={"domain": "example.com", "contact_email": "x@example.com"},
    )
    pid = create.json()["id"]
    draft = client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects/{pid}/draft-email",
        json={},
    )
    eid = draft.json()["id"]
    approve = client.post(
        f"/api/v1/workspaces/{ws.id}/outreach-emails/{eid}/approve"
    )
    assert approve.status_code == 403


def test_send_unapproved_email_rejected(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")
    create = client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects",
        json={"domain": "example.com", "contact_email": "x@example.com"},
    )
    pid = create.json()["id"]
    draft = client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects/{pid}/draft-email",
        json={},
    )
    eid = draft.json()["id"]
    send = client.post(f"/api/v1/workspaces/{ws.id}/outreach-emails/{eid}/send")
    assert send.status_code == 409


def test_approved_send_flips_prospect_to_contacted(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")
    create = client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects",
        json={"domain": "example.com", "contact_email": "x@example.com"},
    )
    pid = create.json()["id"]
    draft = client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects/{pid}/draft-email",
        json={},
    )
    eid = draft.json()["id"]
    approve = client.post(
        f"/api/v1/workspaces/{ws.id}/outreach-emails/{eid}/approve"
    )
    assert approve.status_code == 200, approve.text

    with patch(
        "app.services.outreach_service.send_email", return_value=True
    ) as send_mock:
        send = client.post(
            f"/api/v1/workspaces/{ws.id}/outreach-emails/{eid}/send"
        )
    assert send.status_code == 200, send.text
    assert send.json()["status"] == "sent"
    assert send.json()["sent_at"] is not None
    send_mock.assert_called_once()
    # Prospect status flipped.
    fetch_p = client.get(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects/{pid}"
    )
    assert fetch_p.json()["status"] == "contacted"
    assert fetch_p.json()["last_contacted_at"] is not None


def test_send_failure_persists_failed_row(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")
    create = client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects",
        json={"domain": "example.com", "contact_email": "x@example.com"},
    )
    pid = create.json()["id"]
    draft = client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects/{pid}/draft-email",
        json={},
    )
    eid = draft.json()["id"]
    client.post(f"/api/v1/workspaces/{ws.id}/outreach-emails/{eid}/approve")

    with patch("app.services.outreach_service.send_email", return_value=False):
        send = client.post(
            f"/api/v1/workspaces/{ws.id}/outreach-emails/{eid}/send"
        )
    assert send.status_code == 502

    fetch = client.get(
        f"/api/v1/workspaces/{ws.id}/outreach-emails/{eid}"
    )
    assert fetch.json()["status"] == "failed"
    assert "SMTP" in (fetch.json()["error_message"] or "")


def test_mark_replied_won_updates_prospect(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")
    create = client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects",
        json={"domain": "example.com", "contact_email": "x@example.com"},
    )
    pid = create.json()["id"]
    draft = client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects/{pid}/draft-email",
        json={},
    )
    eid = draft.json()["id"]
    client.post(f"/api/v1/workspaces/{ws.id}/outreach-emails/{eid}/approve")
    with patch("app.services.outreach_service.send_email", return_value=True):
        client.post(f"/api/v1/workspaces/{ws.id}/outreach-emails/{eid}/send")

    replied = client.post(
        f"/api/v1/workspaces/{ws.id}/outreach-emails/{eid}/replied",
        json={"won": True, "backlink_url": "https://example.com/post-with-link"},
    )
    assert replied.status_code == 200
    assert replied.json()["status"] == "replied"

    fetch_p = client.get(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects/{pid}"
    )
    body = fetch_p.json()
    assert body["status"] == "won"
    assert body["backlink_url"] == "https://example.com/post-with-link"
    assert body["won_at"] is not None
