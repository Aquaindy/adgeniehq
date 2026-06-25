"""Campaign launch (Phase 2): create + launch through the approval/execution stack.

Covers:
  * permitted role launches → executes, creates the local Campaign row (paused),
    and accrues the one-time listing fee
  * insufficient role → queued, no provider call, no campaign
  * provider-not-connected, validation, role floor, pre-launch fee quote
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations.meta_ads import MetaAdsProvider
from app.models.campaign import Campaign, CampaignStatus
from app.models.connected_account import ConnectedAccount, ConnectionStatus
from app.models.fee_accrual import FeeAccrual, FeeType
from app.models.oauth_token import OAuthToken
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.encryption import encrypt
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role


def _seed(db: Session, *, email: str, role: Role) -> tuple[User, Workspace]:
    user = User(email=email, hashed_password=hash_password("correct-horse-9"), is_active=True)
    db.add(user)
    db.flush()
    ws = Workspace(name="Test", slug=f"test-{email.split('@')[0]}")
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=role, status=MemberStatus.ACTIVE))
    db.commit()
    return user, ws


def _connect(db: Session, *, ws: Workspace, user: User, provider: str = "meta_ads") -> ConnectedAccount:
    acct = ConnectedAccount(
        workspace_id=ws.id,
        provider=provider,
        provider_account_id="act_42",
        display_name="Acct",
        status=ConnectionStatus.CONNECTED,
        connected_by=user.id,
        connected_at=datetime.now(timezone.utc),
    )
    db.add(acct)
    db.flush()
    db.add(OAuthToken(connected_account_id=acct.id, encrypted_access_token=encrypt("tok"), encrypted_refresh_token=None))
    db.commit()
    return acct


def _login(client: TestClient, email: str) -> None:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-9"})
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})


_CREATE_OK = {
    "ok": True,
    "external_id": "999",
    "external_account_id": "act_42",
    "result": {"id": "999", "name": "Summer Launch"},
}


@pytest.fixture(autouse=True)
def _meta_creds():
    keys = {"META_APP_ID": "x", "META_APP_SECRET": "y"}
    saved = {k: os.environ.get(k) for k in keys}
    os.environ.update(keys)
    try:
        yield
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def test_owner_launch_executes_creates_campaign_and_accrues_listing_fee(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed(db_session, email="o@example.com", role=Role.OWNER)
    _connect(db_session, ws=ws, user=user)

    _login(client, "o@example.com")
    with patch.object(MetaAdsProvider, "create_campaign", return_value=_CREATE_OK) as m:
        resp = client.post(
            f"/api/v1/workspaces/{ws.id}/campaigns/launch",
            json={"provider": "meta_ads", "name": "Summer Launch", "campaign_type": "leads", "daily_budget_cents": 5000},
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "executed"
    assert body["campaign"] is not None
    assert body["campaign"]["external_id"] == "999"
    assert body["campaign"]["status"] == "paused"  # launched safe
    m.assert_called_once()
    # Provider got our objective-mapped payload.
    assert m.call_args.kwargs["payload"]["objective"] == "OUTCOME_LEADS"

    # Local campaign row exists + listing fee accrued.
    campaign = db_session.query(Campaign).filter(Campaign.external_id == "999").first()
    assert campaign is not None
    listing = (
        db_session.query(FeeAccrual)
        .filter(FeeAccrual.campaign_id == campaign.id, FeeAccrual.fee_type == FeeType.LISTING)
        .all()
    )
    assert len(listing) == 1
    assert listing[0].amount_cents == 2500  # default listing fee


def test_marketer_launch_is_queued(client: TestClient, db_session: Session) -> None:
    user, ws = _seed(db_session, email="m@example.com", role=Role.MARKETER)
    _connect(db_session, ws=ws, user=user)

    _login(client, "m@example.com")
    with patch.object(MetaAdsProvider, "create_campaign", side_effect=AssertionError("queued; no write")):
        resp = client.post(
            f"/api/v1/workspaces/{ws.id}/campaigns/launch",
            json={"provider": "meta_ads", "name": "Test", "campaign_type": "leads", "daily_budget_cents": 5000},
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["required_role"] == "admin"
    assert body["campaign"] is None
    assert db_session.query(Campaign).count() == 0


def test_launch_requires_connected_provider(client: TestClient, db_session: Session) -> None:
    _seed(db_session, email="o@example.com", role=Role.OWNER)  # no connected account
    _login(client, "o@example.com")
    ws_id = client.get("/api/v1/workspaces").json()[0]["id"]
    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/campaigns/launch",
        json={"provider": "meta_ads", "name": "Test", "campaign_type": "leads", "daily_budget_cents": 5000},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "provider_not_connected"


def test_launch_validation_rejects_zero_budget(client: TestClient, db_session: Session) -> None:
    user, ws = _seed(db_session, email="o@example.com", role=Role.OWNER)
    _connect(db_session, ws=ws, user=user)
    _login(client, "o@example.com")
    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/campaigns/launch",
        json={"provider": "meta_ads", "name": "Test", "campaign_type": "leads", "daily_budget_cents": 0},
    )
    assert resp.status_code == 422


def test_analyst_cannot_launch(client: TestClient, db_session: Session) -> None:
    user, ws = _seed(db_session, email="a@example.com", role=Role.ANALYST)
    _connect(db_session, ws=ws, user=user)
    _login(client, "a@example.com")
    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/campaigns/launch",
        json={"provider": "meta_ads", "name": "Test", "campaign_type": "leads", "daily_budget_cents": 5000},
    )
    assert resp.status_code == 403


def test_prelaunch_fee_quote(client: TestClient, db_session: Session) -> None:
    _seed(db_session, email="o@example.com", role=Role.OWNER)
    _login(client, "o@example.com")
    ws_id = client.get("/api/v1/workspaces").json()[0]["id"]
    resp = client.get(
        f"/api/v1/workspaces/{ws_id}/billing/fee-quote",
        params={"provider": "meta_ads", "campaign_type": "leads", "daily_budget_cents": 5000},
    )
    assert resp.status_code == 200, resp.text
    q = resp.json()
    assert q["listing_fee_cents"] == 2500
    # 5000/day * 30 = 150000 spend; 10% = 15000 monthly run fee
    assert q["est_monthly_run_fee_cents"] == 15000
    assert q["est_first_month_total_cents"] == 17500
