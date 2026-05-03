"""Provider webhook tests.

Goals:
- Refuse if the per-provider secret is missing → 503.
- Refuse missing/invalid HMAC signature → 401.
- Unrecognized account is 200-acked but not stored.
- Recognized account + campaign.status_changed updates the matching Campaign row.
- Audit log records actor_type=SYSTEM.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.audit_log import AuditActorType, AuditLog
from app.models.campaign import Campaign, CampaignStatus
from app.models.connected_account import ConnectedAccount, ConnectionStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role


_SECRET = "test-google-ads-webhook-secret"


@pytest.fixture(autouse=True)
def _set_secret():
    os.environ["GOOGLE_ADS_WEBHOOK_SECRET"] = _SECRET
    try:
        yield
    finally:
        os.environ.pop("GOOGLE_ADS_WEBHOOK_SECRET", None)


def _seed_account_and_campaign(db: Session) -> tuple[ConnectedAccount, Campaign]:
    user = User(
        email="owner@example.com",
        hashed_password=hash_password("correct-horse-9"),
        is_active=True,
    )
    db.add(user)
    db.flush()
    ws = Workspace(name="Acme", slug="acme-test-webhook")
    db.add(ws)
    db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=ws.id,
            user_id=user.id,
            role=Role.OWNER,
            status=MemberStatus.ACTIVE,
        )
    )
    account = ConnectedAccount(
        workspace_id=ws.id,
        provider="google_ads",
        provider_account_id="ext-acct-123",
        display_name="Test Acct",
        status=ConnectionStatus.CONNECTED,
        connected_by=user.id,
        connected_at=datetime.now(timezone.utc),
    )
    db.add(account)
    db.flush()
    campaign = Campaign(
        workspace_id=ws.id,
        connected_account_id=account.id,
        provider="google_ads",
        external_id="cmp-42",
        external_account_id="ext-acct-123",
        name="Lead Gen Spring",
        status=CampaignStatus.ACTIVE,
        last_synced_at=datetime.now(timezone.utc),
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    db.refresh(account)
    return account, campaign


def _sign(body: bytes, secret: str = _SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------


def test_webhook_returns_503_when_secret_missing(client: TestClient) -> None:
    os.environ.pop("GOOGLE_ADS_WEBHOOK_SECRET", None)
    response = client.post(
        "/api/v1/provider-webhooks/google_ads",
        content=b"{}",
        headers={"X-Provider-Signature": "anything"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_webhook_not_configured"


def test_webhook_rejects_missing_signature(client: TestClient) -> None:
    response = client.post(
        "/api/v1/provider-webhooks/google_ads", content=b"{}"
    )
    assert response.status_code == 401


def test_webhook_rejects_invalid_signature(client: TestClient) -> None:
    response = client.post(
        "/api/v1/provider-webhooks/google_ads",
        content=b"{}",
        headers={"X-Provider-Signature": "deadbeef"},
    )
    assert response.status_code == 401


def test_webhook_acks_unrecognized_account(
    client: TestClient, db_session: Session
) -> None:
    body = json.dumps(
        {
            "event_type": "campaign.status_changed",
            "account_id": "not-our-account",
            "campaign_id": "x",
            "status": "paused",
        }
    ).encode()
    response = client.post(
        "/api/v1/provider-webhooks/google_ads",
        content=body,
        headers={"X-Provider-Signature": _sign(body)},
    )
    assert response.status_code == 200
    body_resp = response.json()
    assert body_resp["matched"] is False
    assert body_resp["rows_updated"] == 0
    assert body_resp["reason"] == "unrecognized_account"


def test_webhook_updates_matching_campaign_status(
    client: TestClient, db_session: Session
) -> None:
    account, campaign = _seed_account_and_campaign(db_session)
    payload = {
        "event_type": "campaign.status_changed",
        "account_id": account.provider_account_id,
        "campaign_id": campaign.external_id,
        "status": "paused",
    }
    body = json.dumps(payload).encode()
    response = client.post(
        "/api/v1/provider-webhooks/google_ads",
        content=body,
        headers={"X-Provider-Signature": _sign(body)},
    )
    assert response.status_code == 200, response.text
    db_session.refresh(campaign)
    assert campaign.status == CampaignStatus.PAUSED

    # Audit row created with system actor.
    audits = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.workspace_id == account.workspace_id,
            AuditLog.action.like("provider_webhook.google_ads.%"),
        )
        .all()
    )
    assert len(audits) == 1
    assert audits[0].actor_type == AuditActorType.SYSTEM


def test_webhook_with_sha256_prefix_accepted(client: TestClient) -> None:
    """Some providers send the digest with a `sha256=` prefix."""
    body = b'{"event_type":"unknown","account_id":"x"}'
    sig = "sha256=" + _sign(body)
    response = client.post(
        "/api/v1/provider-webhooks/google_ads",
        content=body,
        headers={"X-Provider-Signature": sig},
    )
    assert response.status_code == 200
