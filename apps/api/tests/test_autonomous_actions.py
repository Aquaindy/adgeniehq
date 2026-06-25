"""Agent -> executable-action bridge: detectors produce executable recs gated by
the autopilot allowlist; the autopilot loop then runs them within guardrails."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations.meta_ads import MetaAdsProvider
from app.models.ad_group import AdGroup, AdGroupStatus, AdObjectSource
from app.models.autopilot_config import AutopilotConfig, AutopilotMode
from app.models.campaign import Campaign, CampaignStatus
from app.models.connected_account import ConnectedAccount, ConnectionStatus
from app.models.oauth_token import OAuthToken
from app.models.recommendation import Recommendation, RecommendationStatus, RiskLevel
from app.models.recommendation_execution import ExecutionStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.encryption import encrypt
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role
from app.services import autonomous_action_service, autopilot_service, metrics_service


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


def _seed(db: Session, *, email: str = "o@example.com") -> tuple[User, Workspace]:
    user = User(email=email, hashed_password=hash_password("correct-horse-9"), is_active=True)
    db.add(user)
    db.flush()
    ws = Workspace(name="Test", slug=f"test-{email.split('@')[0]}")
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=Role.OWNER, status=MemberStatus.ACTIVE))
    db.commit()
    return user, ws


def _login(client: TestClient, email: str) -> None:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-9"})
    client.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})


def _campaign(db, *, ws, name="C", budget=4000, end_date=None, status=CampaignStatus.ACTIVE) -> Campaign:
    c = Campaign(
        workspace_id=ws.id, provider="meta_ads", external_id="100", external_account_id="act_42",
        name=name, status=status, daily_budget_cents=budget, currency="USD", end_date=end_date,
        objective="Lead generation", last_synced_at=datetime.now(timezone.utc), raw_payload={},
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _config(db, *, ws, mode=AutopilotMode.OFF, allowed=None, ceiling=RiskLevel.LOW) -> AutopilotConfig:
    cfg = AutopilotConfig(
        workspace_id=ws.id, mode=mode, risk_ceiling=ceiling,
        allowed_action_types=allowed or [], max_daily_spend_increase_cents=100000,
        max_daily_spend_total_cents=1000000, max_pct_increase_per_change=25,
        min_conversion_threshold=5,
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------


def test_pause_stale_generates_when_allowlisted(db_session: Session) -> None:
    user, ws = _seed(db_session)
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=2))
    _campaign(db_session, ws=ws, name="Stale", end_date=yesterday)
    cfg = _config(db_session, ws=ws, allowed=["campaign.pause"])

    created = autonomous_action_service.generate_for_workspace(
        db_session, workspace_id=ws.id, system_actor_id=user.id, config=cfg
    )
    assert len(created) == 1
    assert created[0].recommendation_type == "campaign.pause"
    assert created[0].risk_level == RiskLevel.LOW
    md = created[0].metadata_json
    assert md["action"] == "campaign.pause" and md["provider"] == "meta_ads"
    assert md["external_id"] == "100" and md["external_account_id"] == "act_42"


def test_not_generated_when_not_allowlisted(db_session: Session) -> None:
    user, ws = _seed(db_session)
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=2)
    _campaign(db_session, ws=ws, end_date=yesterday)
    cfg = _config(db_session, ws=ws, allowed=[])  # nothing opted in
    created = autonomous_action_service.generate_for_workspace(
        db_session, workspace_id=ws.id, system_actor_id=user.id, config=cfg
    )
    assert created == []


def test_dedup_no_duplicate_within_cooldown(db_session: Session) -> None:
    user, ws = _seed(db_session)
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=2)
    _campaign(db_session, ws=ws, end_date=yesterday)
    cfg = _config(db_session, ws=ws, allowed=["campaign.pause"])
    first = autonomous_action_service.generate_for_workspace(
        db_session, workspace_id=ws.id, system_actor_id=user.id, config=cfg
    )
    second = autonomous_action_service.generate_for_workspace(
        db_session, workspace_id=ws.id, system_actor_id=user.id, config=cfg
    )
    assert len(first) == 1 and len(second) == 0


def test_budget_trim_on_cpa_spike(db_session: Session) -> None:
    user, ws = _seed(db_session)
    c = _campaign(db_session, ws=ws, name="Spiky", budget=10000)
    today = datetime.now(timezone.utc).date()
    # Recent (today): high CPA. Older (10d ago): efficient → 30d baseline far lower.
    metrics_service.upsert_daily(db_session, campaign=c, on_date=today, impressions=5000, clicks=200, spend_cents=20000, conversions=2)
    metrics_service.upsert_daily(db_session, campaign=c, on_date=today - timedelta(days=10), impressions=5000, clicks=460, spend_cents=23000, conversions=23)
    db_session.commit()

    cfg = _config(db_session, ws=ws, allowed=["campaign.update_budget"])
    created = autonomous_action_service.generate_for_workspace(
        db_session, workspace_id=ws.id, system_actor_id=user.id, config=cfg
    )
    trims = [r for r in created if r.metadata_json["dedup"].startswith("trim:")]
    assert len(trims) == 1
    rec = trims[0]
    assert rec.risk_level == RiskLevel.LOW  # a decrease
    assert rec.metadata_json["payload"]["daily_budget_cents"] == 7500  # 25% off


def test_scale_winner_increase_carries_guardrail_metadata(db_session: Session) -> None:
    user, ws = _seed(db_session)
    c = _campaign(db_session, ws=ws, name="Winner", budget=10000)
    today = datetime.now(timezone.utc).date()
    metrics_service.upsert_daily(db_session, campaign=c, on_date=today, impressions=5000, clicks=300, spend_cents=10000, conversions=10, conversion_value_cents=30000)
    db_session.commit()

    cfg = _config(db_session, ws=ws, allowed=["campaign.update_budget"])
    created = autonomous_action_service.generate_for_workspace(
        db_session, workspace_id=ws.id, system_actor_id=user.id, config=cfg
    )
    scales = [r for r in created if r.metadata_json["dedup"].startswith("scale:")]
    assert len(scales) == 1
    rec = scales[0]
    assert rec.risk_level == RiskLevel.MEDIUM  # an increase
    md = rec.metadata_json
    # These fields are exactly what the autopilot spend guardrails evaluate.
    # Default scale is 20%, never exceeding the config per-change cap (25%) → 20%.
    assert md["budget_increase_cents"] == 2000  # 20% of 10000
    assert md["pct_increase"] == 20
    assert md["recent_conversions"] == 10
    assert md["payload"]["daily_budget_cents"] == 12000


def test_publish_draft_ad_set(db_session: Session) -> None:
    user, ws = _seed(db_session)
    c = _campaign(db_session, ws=ws)  # live campaign (has external_id)
    ag = AdGroup(
        workspace_id=ws.id, campaign_id=c.id, external_id=None, source=AdObjectSource.ADVANTA_DRAFT,
        name="Draft AG", status=AdGroupStatus.PAUSED, daily_budget_cents=3000,
        targeting={"geo_locations": {"countries": ["US"]}}, last_synced_at=datetime.now(timezone.utc),
    )
    db_session.add(ag)
    db_session.commit()

    cfg = _config(db_session, ws=ws, allowed=["ad_set.create"], ceiling=RiskLevel.MEDIUM)
    created = autonomous_action_service.generate_for_workspace(
        db_session, workspace_id=ws.id, system_actor_id=user.id, config=cfg
    )
    assert len(created) == 1
    rec = created[0]
    assert rec.recommendation_type == "ad_set.create"
    assert rec.metadata_json["local_object_id"] == str(ag.id)
    assert rec.metadata_json["external_id"] == "100"  # parent campaign


# ---------------------------------------------------------------------------
# End-to-end: generate -> autopilot executes within guardrails
# ---------------------------------------------------------------------------


def test_autopilot_executes_generated_pause(db_session: Session) -> None:
    user, ws = _seed(db_session)
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=2)
    _campaign(db_session, ws=ws, name="Stale", end_date=yesterday)
    # Connected account + token so the executor can resolve the provider.
    acct = ConnectedAccount(
        workspace_id=ws.id, provider="meta_ads", provider_account_id="act_42",
        status=ConnectionStatus.CONNECTED, connected_by=user.id, connected_at=datetime.now(timezone.utc),
    )
    db_session.add(acct)
    db_session.flush()
    db_session.add(OAuthToken(connected_account_id=acct.id, encrypted_access_token=encrypt("tok")))
    cfg = _config(
        db_session, ws=ws, mode=AutopilotMode.AUTOPILOT,
        allowed=["campaign.pause"], ceiling=RiskLevel.LOW,
    )

    created = autonomous_action_service.generate_for_workspace(
        db_session, workspace_id=ws.id, system_actor_id=user.id, config=cfg
    )
    assert len(created) == 1

    fake = {"ok": True, "prior_state": {"status": "ACTIVE"}, "result": {"id": "100"}}
    with patch.object(MetaAdsProvider, "pause_campaign", return_value=fake) as m:
        summary = autopilot_service.auto_approve_pending(
            db_session, workspace_id=ws.id, system_actor_id=user.id
        )
    assert summary["approved"] == 1
    m.assert_called_once()
    db_session.expire_all()
    rec = db_session.get(Recommendation, created[0].id)
    assert rec.status == RecommendationStatus.EXECUTED


def test_medium_risk_blocked_by_low_ceiling(db_session: Session) -> None:
    """A scale (MEDIUM) is generated but NOT executed when the ceiling is LOW."""
    user, ws = _seed(db_session)
    c = _campaign(db_session, ws=ws, name="Winner", budget=10000)
    today = datetime.now(timezone.utc).date()
    metrics_service.upsert_daily(db_session, campaign=c, on_date=today, impressions=5000, clicks=300, spend_cents=10000, conversions=10, conversion_value_cents=30000)
    db_session.commit()
    cfg = _config(
        db_session, ws=ws, mode=AutopilotMode.AUTOPILOT,
        allowed=["campaign.update_budget"], ceiling=RiskLevel.LOW,
    )
    autonomous_action_service.generate_for_workspace(
        db_session, workspace_id=ws.id, system_actor_id=user.id, config=cfg
    )
    summary = autopilot_service.auto_approve_pending(
        db_session, workspace_id=ws.id, system_actor_id=user.id
    )
    # The scale rec is MEDIUM > LOW ceiling → declined, nothing executed.
    assert summary["approved"] == 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def test_generate_endpoint_requires_owner_and_creates(client: TestClient, db_session: Session) -> None:
    user, ws = _seed(db_session)
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=2)
    _campaign(db_session, ws=ws, end_date=yesterday)
    _config(db_session, ws=ws, allowed=["campaign.pause"])
    _login(client, "o@example.com")
    resp = client.post(f"/api/v1/workspaces/{ws.id}/autopilot/generate")
    assert resp.status_code == 200, resp.text
    assert resp.json()["generated"] == 1


def test_candidates_preview_does_not_write(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session)
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=2)
    _campaign(db_session, ws=ws, end_date=yesterday)
    _config(db_session, ws=ws, allowed=[])  # not opted in
    _login(client, "o@example.com")
    resp = client.get(f"/api/v1/workspaces/{ws.id}/autopilot/candidates")
    assert resp.status_code == 200
    items = resp.json()
    assert any(i["action"] == "campaign.pause" and i["allowed"] is False for i in items)
    # Nothing written.
    assert db_session.query(Recommendation).filter(Recommendation.workspace_id == ws.id).count() == 0
