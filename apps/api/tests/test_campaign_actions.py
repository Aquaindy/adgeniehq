"""User-initiated campaign management actions (pause / resume / edit budget).

Covers the "manage from the app" path that routes a button click through the
approval + execution engine:
  * actor whose role can approve the risk -> executes on the platform now
  * actor who can't -> queued as a pending approval (no provider call)
  * spend-direction risk model (pause/decrease = low; resume/increase = higher)
  * state guards (already paused/active), not-found, isolation, role floor
  * provider failure surfaces as status="failed" without mutating local state
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations.meta_ads import MetaAdsProvider
from app.models.approval import Approval, ApprovalStatus
from app.models.campaign import Campaign, CampaignStatus
from app.models.connected_account import ConnectedAccount, ConnectionStatus
from app.models.oauth_token import OAuthToken
from app.models.recommendation import Recommendation, RecommendationStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.encryption import encrypt
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_workspace(
    db: Session, *, email: str, role: Role, slug: str | None = None
) -> tuple[User, Workspace, WorkspaceMember]:
    user = User(
        email=email, hashed_password=hash_password("correct-horse-9"), is_active=True
    )
    db.add(user)
    db.flush()
    ws = Workspace(name="Test", slug=slug or f"test-{email.split('@')[0]}")
    db.add(ws)
    db.flush()
    member = WorkspaceMember(
        workspace_id=ws.id, user_id=user.id, role=role, status=MemberStatus.ACTIVE
    )
    db.add(member)
    db.commit()
    return user, ws, member


def _seed_connected_account(
    db: Session, *, workspace: Workspace, user: User, provider: str = "meta_ads"
) -> ConnectedAccount:
    account = ConnectedAccount(
        workspace_id=workspace.id,
        provider=provider,
        provider_account_id="ext-id",
        display_name="Test acct",
        status=ConnectionStatus.CONNECTED,
        connected_by=user.id,
        connected_at=datetime.now(timezone.utc),
    )
    db.add(account)
    db.flush()
    db.add(
        OAuthToken(
            connected_account_id=account.id,
            encrypted_access_token=encrypt("real-access-token"),
            encrypted_refresh_token=None,
        )
    )
    db.commit()
    return account


def _seed_campaign(
    db: Session,
    *,
    workspace: Workspace,
    connected_account: ConnectedAccount | None = None,
    provider: str = "meta_ads",
    status: CampaignStatus = CampaignStatus.ACTIVE,
    daily_budget_cents: int | None = 4000,
    external_id: str = "100",
    external_account_id: str | None = "act_42",
) -> Campaign:
    campaign = Campaign(
        workspace_id=workspace.id,
        connected_account_id=connected_account.id if connected_account else None,
        provider=provider,
        external_id=external_id,
        external_account_id=external_account_id,
        name="Summer Sale",
        status=status,
        objective="OUTCOME_LEADS",
        daily_budget_cents=daily_budget_cents,
        currency="USD",
        last_synced_at=datetime.now(timezone.utc),
        raw_payload={},
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


def _login(client: TestClient, email: str) -> None:
    resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-9"}
    )
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})


_PAUSE_OK = {
    "ok": True,
    "prior_state": {"status": "ACTIVE"},
    "result": {"id": "100", "status": "PAUSED"},
}
_RESUME_OK = {
    "ok": True,
    "prior_state": {"status": "PAUSED"},
    "result": {"id": "100", "status": "ACTIVE"},
}
_BUDGET_OK = {
    "ok": True,
    "prior_state": {"daily_budget_cents": 4000},
    "result": {"id": "100"},
}


@pytest.fixture(autouse=True)
def _meta_creds():
    keys = {"META_APP_ID": "test-app", "META_APP_SECRET": "test-secret"}
    saved = {k: os.environ.get(k) for k in keys}
    os.environ.update(keys)
    try:
        yield
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


# ---------------------------------------------------------------------------
# One-click execution (permitted)
# ---------------------------------------------------------------------------


def test_marketer_can_one_click_pause(client: TestClient, db_session: Session) -> None:
    user, ws, _ = _seed_workspace(db_session, email="m@example.com", role=Role.MARKETER)
    acct = _seed_connected_account(db_session, workspace=ws, user=user)
    campaign = _seed_campaign(db_session, workspace=ws, connected_account=acct)

    _login(client, "m@example.com")
    with patch.object(MetaAdsProvider, "pause_campaign", return_value=_PAUSE_OK) as m:
        resp = client.post(
            f"/api/v1/workspaces/{ws.id}/campaigns/{campaign.id}/pause"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "executed"
    assert body["risk_level"] == "low"
    assert body["execution_status"] == "succeeded"
    assert body["campaign"]["status"] == "paused"
    m.assert_called_once()


def test_budget_decrease_is_low_and_executes_for_marketer(
    client: TestClient, db_session: Session
) -> None:
    user, ws, _ = _seed_workspace(db_session, email="m@example.com", role=Role.MARKETER)
    acct = _seed_connected_account(db_session, workspace=ws, user=user)
    campaign = _seed_campaign(db_session, workspace=ws, connected_account=acct, daily_budget_cents=4000)

    _login(client, "m@example.com")
    with patch.object(MetaAdsProvider, "update_campaign_budget", return_value=_BUDGET_OK) as m:
        resp = client.post(
            f"/api/v1/workspaces/{ws.id}/campaigns/{campaign.id}/budget",
            json={"daily_budget_cents": 2000},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "executed"
    assert body["risk_level"] == "low"
    assert body["campaign"]["daily_budget_cents"] == 2000
    m.assert_called_once()


def test_owner_budget_increase_executes(client: TestClient, db_session: Session) -> None:
    user, ws, _ = _seed_workspace(db_session, email="o@example.com", role=Role.OWNER)
    acct = _seed_connected_account(db_session, workspace=ws, user=user)
    campaign = _seed_campaign(db_session, workspace=ws, connected_account=acct, daily_budget_cents=4000)

    _login(client, "o@example.com")
    with patch.object(MetaAdsProvider, "update_campaign_budget", return_value=_BUDGET_OK):
        resp = client.post(
            f"/api/v1/workspaces/{ws.id}/campaigns/{campaign.id}/budget",
            json={"daily_budget_cents": 8000},  # +100% => HIGH
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "executed"
    assert body["risk_level"] == "high"
    assert body["campaign"]["daily_budget_cents"] == 8000


# ---------------------------------------------------------------------------
# Queued (actor can't approve the risk level)
# ---------------------------------------------------------------------------


def test_marketer_budget_increase_is_queued(client: TestClient, db_session: Session) -> None:
    user, ws, _ = _seed_workspace(db_session, email="m@example.com", role=Role.MARKETER)
    acct = _seed_connected_account(db_session, workspace=ws, user=user)
    campaign = _seed_campaign(db_session, workspace=ws, connected_account=acct, daily_budget_cents=4000)

    _login(client, "m@example.com")
    with patch.object(
        MetaAdsProvider,
        "update_campaign_budget",
        side_effect=AssertionError("must not write while queued"),
    ):
        resp = client.post(
            f"/api/v1/workspaces/{ws.id}/campaigns/{campaign.id}/budget",
            json={"daily_budget_cents": 8000},  # HIGH -> needs OWNER
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["risk_level"] == "high"
    assert body["required_role"] == "owner"
    assert body["execution_id"] is None
    # Local budget unchanged until executed.
    assert body["campaign"]["daily_budget_cents"] == 4000

    # A pending approval + open recommendation now exist for an owner to act on.
    rec = db_session.query(Recommendation).filter(Recommendation.id == body["recommendation_id"]).first()
    assert rec.status == RecommendationStatus.OPEN
    approval = db_session.query(Approval).filter(Approval.recommendation_id == rec.id).first()
    assert approval.status == ApprovalStatus.PENDING


def test_marketer_resume_is_queued_for_admin(client: TestClient, db_session: Session) -> None:
    user, ws, _ = _seed_workspace(db_session, email="m@example.com", role=Role.MARKETER)
    acct = _seed_connected_account(db_session, workspace=ws, user=user)
    campaign = _seed_campaign(
        db_session, workspace=ws, connected_account=acct, status=CampaignStatus.PAUSED
    )

    _login(client, "m@example.com")
    with patch.object(
        MetaAdsProvider, "resume_campaign", side_effect=AssertionError("queued; no write")
    ):
        resp = client.post(
            f"/api/v1/workspaces/{ws.id}/campaigns/{campaign.id}/resume"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["risk_level"] == "medium"
    assert body["required_role"] == "admin"


# ---------------------------------------------------------------------------
# Guards + failures
# ---------------------------------------------------------------------------


def test_pause_already_paused_conflicts(client: TestClient, db_session: Session) -> None:
    user, ws, _ = _seed_workspace(db_session, email="o@example.com", role=Role.OWNER)
    acct = _seed_connected_account(db_session, workspace=ws, user=user)
    campaign = _seed_campaign(
        db_session, workspace=ws, connected_account=acct, status=CampaignStatus.PAUSED
    )
    _login(client, "o@example.com")
    resp = client.post(f"/api/v1/workspaces/{ws.id}/campaigns/{campaign.id}/pause")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "invalid_campaign_action"


def test_failed_execution_when_not_connected(client: TestClient, db_session: Session) -> None:
    # Owner + campaign, but NO connected account -> execution fails (account not ready).
    user, ws, _ = _seed_workspace(db_session, email="o@example.com", role=Role.OWNER)
    campaign = _seed_campaign(db_session, workspace=ws, connected_account=None)

    _login(client, "o@example.com")
    resp = client.post(f"/api/v1/workspaces/{ws.id}/campaigns/{campaign.id}/pause")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "failed"
    assert body["execution_status"] == "failed"
    # Local status must NOT change on a failed write.
    assert body["campaign"]["status"] == "active"


def test_budget_must_be_positive(client: TestClient, db_session: Session) -> None:
    user, ws, _ = _seed_workspace(db_session, email="o@example.com", role=Role.OWNER)
    acct = _seed_connected_account(db_session, workspace=ws, user=user)
    campaign = _seed_campaign(db_session, workspace=ws, connected_account=acct)
    _login(client, "o@example.com")
    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/campaigns/{campaign.id}/budget",
        json={"daily_budget_cents": 0},
    )
    assert resp.status_code == 422


def test_campaign_not_found(client: TestClient, db_session: Session) -> None:
    user, ws, _ = _seed_workspace(db_session, email="o@example.com", role=Role.OWNER)
    _login(client, "o@example.com")
    import uuid

    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/campaigns/{uuid.uuid4()}/pause"
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "campaign_not_found"


def test_analyst_cannot_initiate_actions(client: TestClient, db_session: Session) -> None:
    user, ws, _ = _seed_workspace(db_session, email="a@example.com", role=Role.ANALYST)
    acct = _seed_connected_account(db_session, workspace=ws, user=user)
    campaign = _seed_campaign(db_session, workspace=ws, connected_account=acct)
    _login(client, "a@example.com")
    resp = client.post(f"/api/v1/workspaces/{ws.id}/campaigns/{campaign.id}/pause")
    assert resp.status_code == 403


def test_workspace_isolation(client: TestClient, db_session: Session) -> None:
    owner, ws, _ = _seed_workspace(db_session, email="o@example.com", role=Role.OWNER)
    acct = _seed_connected_account(db_session, workspace=ws, user=owner)
    campaign = _seed_campaign(db_session, workspace=ws, connected_account=acct)
    # An outsider with their own workspace.
    _seed_workspace(db_session, email="evil@example.com", role=Role.OWNER, slug="evil")

    _login(client, "evil@example.com")
    resp = client.post(f"/api/v1/workspaces/{ws.id}/campaigns/{campaign.id}/pause")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "workspace_not_found"
