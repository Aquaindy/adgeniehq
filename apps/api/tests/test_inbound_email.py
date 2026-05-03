"""Inbound reply / bounce detection for outreach.

Pins the auth + token-routing + status-flip behaviour of the inbound webhook.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.backlink_prospect import ProspectStatus
from app.models.outreach_email import OutreachEmailStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role


@pytest.fixture(autouse=True)
def _inbound_config():
    """Stamp test-friendly inbound config so the webhook accepts our test
    secret and the send path stamps a Reply-To we can match against."""

    saved_domain = settings.inbound_email_domain
    saved_secret = settings.inbound_email_secret
    settings.inbound_email_domain = "inbound.example.com"
    settings.inbound_email_secret = "test-inbound-secret"
    try:
        yield
    finally:
        settings.inbound_email_domain = saved_domain
        settings.inbound_email_secret = saved_secret


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


def _send_outreach(client: TestClient, ws_id, contact_email: str) -> dict:
    create = client.post(
        f"/api/v1/workspaces/{ws_id}/backlink-prospects",
        json={"domain": "example.com", "contact_email": contact_email},
    )
    pid = create.json()["id"]
    draft = client.post(
        f"/api/v1/workspaces/{ws_id}/backlink-prospects/{pid}/draft-email",
        json={},
    )
    eid = draft.json()["id"]
    client.post(f"/api/v1/workspaces/{ws_id}/outreach-emails/{eid}/approve")
    with patch(
        "app.services.outreach_service.send_email", return_value=True
    ) as send_mock:
        send_resp = client.post(
            f"/api/v1/workspaces/{ws_id}/outreach-emails/{eid}/send"
        )
    return {
        "prospect_id": pid,
        "email_id": eid,
        "send_mock": send_mock,
        "sent_payload": send_resp.json(),
    }


# ---------------------------------------------------------------------------
# Reply-To wiring
# ---------------------------------------------------------------------------


def test_send_stamps_reply_to_with_per_email_token(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    out = _send_outreach(client, ws.id, "target@example.com")
    # The send_email mock saw the draft we passed.
    args, kwargs = out["send_mock"].call_args
    draft = kwargs["draft"]
    assert draft.reply_to is not None
    assert draft.reply_to.endswith("@inbound.example.com")
    assert draft.reply_to.startswith("reply+")
    # The token persisted on the email row.
    assert out["sent_payload"]["status"] == "sent"


# ---------------------------------------------------------------------------
# Auth on /inbound/email
# ---------------------------------------------------------------------------


def test_inbound_rejects_missing_secret(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/inbound/email",
        json={"To": "reply+abc@inbound.example.com"},
    )
    assert resp.status_code == 401


def test_inbound_rejects_wrong_secret(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/inbound/email",
        json={"To": "reply+abc@inbound.example.com"},
        headers={"X-Inbound-Secret": "no-thanks"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Reply detection
# ---------------------------------------------------------------------------


def test_inbound_reply_marks_email_replied(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    out = _send_outreach(client, ws.id, "target@example.com")

    # Pull the reply token off the row we just sent.
    sent_detail = client.get(
        f"/api/v1/workspaces/{ws.id}/outreach-emails/{out['email_id']}"
    )
    assert sent_detail.status_code == 200
    # Reply token isn't in the public schema (sensitive), so read it from db.
    from app.models.outreach_email import OutreachEmail

    row = (
        db_session.query(OutreachEmail)
        .filter(OutreachEmail.id == out["email_id"])
        .first()
    )
    assert row.reply_token is not None
    token = row.reply_token

    # Strip auth — inbound is shared-secret, not user-bearer.
    client.headers.pop("Authorization", None)
    inbound = client.post(
        "/api/v1/inbound/email",
        json={
            "To": f"reply+{token}@inbound.example.com",
            "From": "Sam <target@example.com>",
            "Subject": "Re: quick note",
            "TextBody": "Sounds great, send me more info.",
        },
        headers={"X-Inbound-Secret": "test-inbound-secret"},
    )
    assert inbound.status_code == 200, inbound.text
    body = inbound.json()
    assert body["matched"] is True
    assert body["is_bounce"] is False

    db_session.refresh(row)
    assert row.status == OutreachEmailStatus.REPLIED
    assert row.replied_at is not None
    # Prospect flipped too.
    from app.models.backlink_prospect import BacklinkProspect

    prospect = (
        db_session.query(BacklinkProspect)
        .filter(BacklinkProspect.id == row.prospect_id)
        .first()
    )
    assert prospect.status == ProspectStatus.REPLIED


def test_inbound_bounce_marks_email_and_prospect_bounced(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    out = _send_outreach(client, ws.id, "target@example.com")

    from app.models.outreach_email import OutreachEmail

    row = (
        db_session.query(OutreachEmail)
        .filter(OutreachEmail.id == out["email_id"])
        .first()
    )
    token = row.reply_token

    client.headers.pop("Authorization", None)
    # Postmark-style bounce shape: top-level `Type`.
    inbound = client.post(
        "/api/v1/inbound/email",
        json={
            "To": f"reply+{token}@inbound.example.com",
            "From": "mailer-daemon@example.com",
            "Subject": "Mail Delivery Failure",
            "Type": "HardBounce",
        },
        headers={"X-Inbound-Secret": "test-inbound-secret"},
    )
    assert inbound.status_code == 200
    assert inbound.json()["is_bounce"] is True

    db_session.refresh(row)
    assert row.status == OutreachEmailStatus.BOUNCED
    from app.models.backlink_prospect import BacklinkProspect

    prospect = (
        db_session.query(BacklinkProspect)
        .filter(BacklinkProspect.id == row.prospect_id)
        .first()
    )
    assert prospect.status == ProspectStatus.BOUNCED


def test_inbound_unknown_token_returns_200_no_op(
    client: TestClient,
) -> None:
    resp = client.post(
        "/api/v1/inbound/email",
        json={
            "To": "reply+nonexistent@inbound.example.com",
            "From": "stranger@example.com",
            "Subject": "Hi",
        },
        headers={"X-Inbound-Secret": "test-inbound-secret"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] is False
    assert body["reason"] == "unknown_token"


def test_inbound_no_reply_token_in_to_returns_no_match(
    client: TestClient,
) -> None:
    resp = client.post(
        "/api/v1/inbound/email",
        json={
            "To": "support@inbound.example.com",  # no reply+token prefix
            "From": "stranger@example.com",
        },
        headers={"X-Inbound-Secret": "test-inbound-secret"},
    )
    assert resp.status_code == 200
    assert resp.json()["matched"] is False
    assert resp.json()["reason"] == "no_reply_token"


def test_inbound_handles_named_recipient_format(
    client: TestClient, db_session: Session
) -> None:
    """Some parse providers send the To field as `Name <addr>` rather than a
    bare address. The parser must still extract the token."""

    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    out = _send_outreach(client, ws.id, "target@example.com")
    from app.models.outreach_email import OutreachEmail

    row = (
        db_session.query(OutreachEmail)
        .filter(OutreachEmail.id == out["email_id"])
        .first()
    )
    token = row.reply_token

    client.headers.pop("Authorization", None)
    resp = client.post(
        "/api/v1/inbound/email",
        json={
            "To": f"AdVanta Reply <reply+{token}@inbound.example.com>",
            "From": "target@example.com",
            "Subject": "Re: quick note",
        },
        headers={"X-Inbound-Secret": "test-inbound-secret"},
    )
    assert resp.status_code == 200
    assert resp.json()["matched"] is True
