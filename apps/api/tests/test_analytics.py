"""Campaign analytics: KPI derivation, series, workspace summary, insights sync."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations.google_ads import GoogleAdsProvider
from app.integrations.linkedin_ads import LinkedInAdsProvider
from app.integrations.meta_ads import MetaAdsProvider
from app.models.campaign import Campaign, CampaignStatus
from app.models.connected_account import ConnectedAccount, ConnectionStatus
from app.models.oauth_token import OAuthToken
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.encryption import encrypt
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role
from app.services import metrics_service


def _seed(db: Session, *, email: str, role: Role = Role.OWNER) -> tuple[User, Workspace]:
    user = User(email=email, hashed_password=hash_password("correct-horse-9"), is_active=True)
    db.add(user)
    db.flush()
    ws = Workspace(name="Test", slug=f"test-{email.split('@')[0]}")
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=role, status=MemberStatus.ACTIVE))
    db.commit()
    return user, ws


def _campaign(db: Session, *, ws: Workspace, name: str = "Camp", provider: str = "meta_ads") -> Campaign:
    c = Campaign(
        workspace_id=ws.id, provider=provider, external_id="100", external_account_id="act_42",
        name=name, status=CampaignStatus.ACTIVE, daily_budget_cents=4000, currency="USD",
        last_synced_at=datetime.now(timezone.utc), raw_payload={},
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _login(client: TestClient, email: str) -> None:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-9"})
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})


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


# ---------------------------------------------------------------------------
# KPI derivation + Meta insights parsing (pure)
# ---------------------------------------------------------------------------


def test_derive_kpis() -> None:
    k = metrics_service.derive_kpis(
        impressions=1000, clicks=50, spend_cents=1234, conversions=5, conversion_value_cents=10000
    )
    assert k["ctr"] == 0.05
    assert k["cpc_cents"] == 25  # 1234/50
    assert k["cpa_cents"] == 247  # 1234/5
    assert k["roas"] == 8.1  # 10000/1234 ≈ 8.1
    assert k["conversion_rate"] == 0.1


class _FakeResp:
    def __init__(self, body):
        self.status_code = 200
        self._b = body
        self.text = ""

    def json(self):
        return self._b


def test_meta_fetch_insights_parses_rows() -> None:
    body = {
        "data": [
            {
                "date_start": "2026-06-01",
                "impressions": "1000",
                "clicks": "50",
                "spend": "12.34",
                "actions": [{"action_type": "lead", "value": "5"}, {"action_type": "link_click", "value": "50"}],
                "action_values": [{"action_type": "purchase", "value": "100.00"}],
            }
        ]
    }
    with patch.object(httpx, "get", return_value=_FakeResp(body)):
        rows = MetaAdsProvider.fetch_insights(
            access_token="t", external_account_id="act_42", external_id="100",
            date_from="2026-06-01", date_to="2026-06-02",
        )
    assert len(rows) == 1
    r = rows[0]
    assert r["date"] == "2026-06-01"
    assert r["impressions"] == 1000
    assert r["clicks"] == 50
    assert r["spend_cents"] == 1234
    assert r["conversions"] == 5  # only the 'lead' action counts
    assert r["conversion_value_cents"] == 10000


def test_google_fetch_insights_parses_rows() -> None:
    body = {
        "results": [
            {
                "segments": {"date": "2026-06-01"},
                "metrics": {
                    "impressions": "1000",
                    "clicks": "50",
                    "costMicros": "12340000",  # $12.34 → 1234 cents
                    "conversions": 5,
                    "conversionsValue": 100.0,
                },
            }
        ]
    }
    with patch.dict(os.environ, {"GOOGLE_ADS_DEVELOPER_TOKEN": "dev"}):
        with patch.object(httpx, "post", return_value=_FakeResp(body)):
            rows = GoogleAdsProvider.fetch_insights(
                access_token="t", external_account_id="123", external_id="100",
                date_from="2026-06-01", date_to="2026-06-02",
            )
    assert len(rows) == 1
    r = rows[0]
    assert r["date"] == "2026-06-01"
    assert r["impressions"] == 1000
    assert r["clicks"] == 50
    assert r["spend_cents"] == 1234
    assert r["conversions"] == 5
    assert r["conversion_value_cents"] == 10000


def test_linkedin_fetch_insights_parses_rows() -> None:
    body = {
        "elements": [
            {
                "dateRange": {"start": {"year": 2026, "month": 6, "day": 1}},
                "impressions": 2000,
                "clicks": 80,
                "costInLocalCurrency": "40.00",
                "externalWebsiteConversions": 8,
            }
        ]
    }
    captured: dict = {}

    def _fake_get(url, **kwargs):
        captured["url"] = url
        return _FakeResp(body)

    with patch.object(httpx, "get", side_effect=_fake_get):
        rows = LinkedInAdsProvider.fetch_insights(
            access_token="t", external_account_id="acct", external_id="777",
            date_from="2026-06-01", date_to="2026-06-24",
        )
    assert len(rows) == 1
    r = rows[0]
    assert r["date"] == "2026-06-01"
    assert r["impressions"] == 2000
    assert r["clicks"] == 80
    assert r["spend_cents"] == 4000
    assert r["conversions"] == 8
    # URN encoded, date tuple + List() literal preserved.
    assert "urn%3Ali%3AsponsoredCampaign%3A777" in captured["url"]
    assert "dateRange=(start:(year:2026,month:6,day:1)" in captured["url"]


# ---------------------------------------------------------------------------
# Series + summary
# ---------------------------------------------------------------------------


def test_campaign_series_and_summary(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    c = _campaign(db_session, ws=ws)
    today = datetime.now(timezone.utc).date()
    metrics_service.upsert_daily(
        db_session, campaign=c, on_date=today, impressions=1000, clicks=50, spend_cents=1234, conversions=5, conversion_value_cents=10000
    )
    db_session.commit()

    _login(client, "o@example.com")
    series = client.get(f"/api/v1/workspaces/{ws.id}/campaigns/{c.id}/metrics?days=30").json()
    assert len(series["points"]) == 1
    assert series["totals"]["spend_cents"] == 1234
    assert series["totals"]["ctr"] == 0.05

    summary = client.get(f"/api/v1/workspaces/{ws.id}/analytics/summary?days=30").json()
    assert summary["has_data"] is True
    assert summary["totals"]["clicks"] == 50
    assert summary["by_provider"]["meta_ads"]["spend_cents"] == 1234
    assert summary["top_campaigns"][0]["name"] == "Camp"
    assert len(summary["daily"]) == 1


def test_upsert_is_idempotent_per_day(db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    c = _campaign(db_session, ws=ws)
    today = datetime.now(timezone.utc).date()
    metrics_service.upsert_daily(db_session, campaign=c, on_date=today, impressions=10, clicks=1, spend_cents=100, conversions=0)
    metrics_service.upsert_daily(db_session, campaign=c, on_date=today, impressions=20, clicks=2, spend_cents=200, conversions=1)
    db_session.commit()
    from app.models.campaign_metric import CampaignMetric

    rows = db_session.query(CampaignMetric).filter(CampaignMetric.campaign_id == c.id).all()
    assert len(rows) == 1  # same day overwrites
    assert rows[0].spend_cents == 200


def test_empty_summary_has_no_data(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    _login(client, "o@example.com")
    summary = client.get(f"/api/v1/workspaces/{ws.id}/analytics/summary").json()
    assert summary["has_data"] is False
    assert summary["totals"]["spend_cents"] == 0


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


def test_sync_pulls_insights_and_upserts(client: TestClient, db_session: Session) -> None:
    user, ws = _seed(db_session, email="o@example.com")
    c = _campaign(db_session, ws=ws)
    acct = ConnectedAccount(
        workspace_id=ws.id, provider="meta_ads", provider_account_id="act_42", display_name="A",
        status=ConnectionStatus.CONNECTED, connected_by=user.id, connected_at=datetime.now(timezone.utc),
    )
    db_session.add(acct)
    db_session.flush()
    db_session.add(OAuthToken(connected_account_id=acct.id, encrypted_access_token=encrypt("tok"), encrypted_refresh_token=None))
    db_session.commit()

    today = datetime.now(timezone.utc).date().isoformat()
    fake_rows = [{"date": today, "impressions": 2000, "clicks": 80, "spend_cents": 4000, "conversions": 8, "conversion_value_cents": 20000}]

    _login(client, "o@example.com")
    with patch.object(MetaAdsProvider, "fetch_insights", return_value=fake_rows) as m:
        sync = client.post(f"/api/v1/workspaces/{ws.id}/analytics/sync?days=7")
    assert sync.status_code == 200, sync.text
    assert sync.json()["upserted"] == 1
    m.assert_called_once()

    summary = client.get(f"/api/v1/workspaces/{ws.id}/analytics/summary?days=7").json()
    assert summary["totals"]["spend_cents"] == 4000
    assert summary["totals"]["conversions"] == 8


def test_sync_requires_marketer(client: TestClient, db_session: Session) -> None:
    _seed(db_session, email="a@example.com", role=Role.ANALYST)
    _login(client, "a@example.com")
    ws_id = client.get("/api/v1/workspaces").json()[0]["id"]
    resp = client.post(f"/api/v1/workspaces/{ws_id}/analytics/sync")
    assert resp.status_code == 403


def test_analytics_isolation(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    _seed(db_session, email="evil@example.com")
    _login(client, "evil@example.com")
    resp = client.get(f"/api/v1/workspaces/{ws.id}/analytics/summary")
    assert resp.status_code == 404
