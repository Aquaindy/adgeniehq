"""Publishing draft ad groups / ads to the platform — provider create_ad_set /
create_ad parsing (mocked HTTP) + the publish → approval → execution wiring.
Fully hermetic."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations.google_ads import GoogleAdsProvider
from app.integrations.base import ProviderError
from app.integrations.meta_ads import MetaAdsProvider
from app.models.ad_group import AdGroup, AdGroupStatus, AdObjectSource
from app.models.ad import Ad, AdStatus
from app.models.campaign import Campaign, CampaignStatus
from app.models.connected_account import ConnectedAccount, ConnectionStatus
from app.models.oauth_token import OAuthToken
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.encryption import encrypt
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role


@pytest.fixture(autouse=True)
def _provider_creds():
    keys = {
        "META_APP_ID": "x",
        "META_APP_SECRET": "y",
        "GOOGLE_CLIENT_ID": "g",
        "GOOGLE_CLIENT_SECRET": "gs",
        "GOOGLE_ADS_DEVELOPER_TOKEN": "dev",
    }
    saved = {k: os.environ.get(k) for k in keys}
    os.environ.update(keys)
    try:
        yield
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def _seed(db: Session, *, email: str, role: Role = Role.ADMIN) -> tuple[User, Workspace]:
    user = User(email=email, hashed_password=hash_password("correct-horse-9"), is_active=True)
    db.add(user)
    db.flush()
    ws = Workspace(name="Test", slug=f"test-{email.split('@')[0]}")
    db.add(ws)
    db.flush()
    db.add(
        WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=role, status=MemberStatus.ACTIVE)
    )
    db.commit()
    return user, ws


def _login(client: TestClient, email: str) -> None:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-9"})
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})


def _live_campaign(db: Session, *, ws: Workspace, user: User) -> Campaign:
    acct = ConnectedAccount(
        workspace_id=ws.id, provider="meta_ads", provider_account_id="act_42",
        display_name="A", status=ConnectionStatus.CONNECTED, connected_by=user.id,
        connected_at=datetime.now(timezone.utc),
    )
    db.add(acct)
    db.flush()
    db.add(OAuthToken(connected_account_id=acct.id, encrypted_access_token=encrypt("tok")))
    c = Campaign(
        workspace_id=ws.id, provider="meta_ads", external_id="camp1",
        external_account_id="act_42", name="Live", status=CampaignStatus.PAUSED,
        last_synced_at=datetime.now(timezone.utc), raw_payload={},
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _draft_ad_group(db: Session, *, ws: Workspace, campaign: Campaign) -> AdGroup:
    ag = AdGroup(
        workspace_id=ws.id, campaign_id=campaign.id, external_id=None,
        source=AdObjectSource.ADVANTA_DRAFT, name="AG", status=AdGroupStatus.PAUSED,
        daily_budget_cents=5000, targeting={"geo_locations": {"countries": ["US"]}},
        last_synced_at=datetime.now(timezone.utc),
    )
    db.add(ag)
    db.commit()
    db.refresh(ag)
    return ag


class _FakeResp:
    def __init__(self, body, *, status_code=200, text="", headers=None):
        self.status_code = status_code
        self._b = body
        self.text = text
        self.content = b"{}"
        self.headers = headers or {}

    def json(self):
        return self._b


# ---------------------------------------------------------------------------
# Provider create_ad_set / create_ad parsing
# ---------------------------------------------------------------------------


def test_meta_create_ad_set_builds_body() -> None:
    captured: dict = {}

    def _fake_post(url, **kwargs):
        captured["url"] = url
        captured["data"] = kwargs.get("data")
        return _FakeResp({"id": "as_99"})

    with patch.object(httpx, "post", side_effect=_fake_post):
        result = MetaAdsProvider.create_ad_set(
            access_token="t", external_account_id="act_42", campaign_external_id="camp1",
            payload={"name": "AG", "daily_budget_cents": 5000},
        )
    assert result["external_id"] == "as_99"
    assert "act_42/adsets" in captured["url"]
    data = captured["data"]
    assert data["campaign_id"] == "camp1"
    assert data["daily_budget"] == "5000"
    assert data["status"] == "PAUSED"
    assert "geo_locations" in data["targeting"]  # default targeting injected


def test_meta_create_ad_requires_creative() -> None:
    with pytest.raises(ProviderError):
        MetaAdsProvider.create_ad(
            access_token="t", external_account_id="act_42", ad_set_external_id="as_99",
            payload={"name": "Ad"},
        )


def test_meta_create_ad_with_creative_builds_body() -> None:
    captured: dict = {}

    def _fake_post(url, **kwargs):
        captured["data"] = kwargs.get("data")
        return _FakeResp({"id": "ad_7"})

    with patch.object(httpx, "post", side_effect=_fake_post):
        result = MetaAdsProvider.create_ad(
            access_token="t", external_account_id="act_42", ad_set_external_id="as_99",
            payload={"name": "Ad", "creative_id": "cr_1"},
        )
    assert result["external_id"] == "ad_7"
    assert '"creative_id": "cr_1"' in captured["data"]["creative"]
    assert captured["data"]["adset_id"] == "as_99"


def test_google_create_ad_set_parses_resource_name() -> None:
    body = {"results": [{"resourceName": "customers/123/adGroups/777"}]}
    with patch.object(httpx, "post", return_value=_FakeResp(body)):
        result = GoogleAdsProvider.create_ad_set(
            access_token="t", external_account_id="123", campaign_external_id="camp1",
            payload={"name": "AG"},
        )
    assert result["external_id"] == "777"


def test_google_create_ad_builds_rsa() -> None:
    captured: dict = {}

    def _fake_post(url, **kwargs):
        captured["json"] = kwargs.get("json")
        return _FakeResp({"results": [{"resourceName": "customers/123/adGroupAds/777~888"}]})

    with patch.object(httpx, "post", side_effect=_fake_post):
        result = GoogleAdsProvider.create_ad(
            access_token="t", external_account_id="123", ad_set_external_id="777",
            payload={
                "name": "Ad", "landing_page_url": "https://acme.com",
                "headlines": ["Fast leads", "Try AdVanta"], "descriptions": ["Grow now"],
            },
        )
    assert result["external_id"] == "777~888"
    create = captured["json"]["operations"][0]["create"]
    assert create["adGroup"].endswith("/adGroups/777")
    assert create["ad"]["finalUrls"] == ["https://acme.com"]
    assert create["ad"]["responsiveSearchAd"]["headlines"][0]["text"] == "Fast leads"


def test_google_create_ad_requires_assets() -> None:
    with pytest.raises(ProviderError):
        GoogleAdsProvider.create_ad(
            access_token="t", external_account_id="123", ad_set_external_id="777",
            payload={"name": "Ad", "landing_page_url": "https://acme.com"},  # no headlines
        )


def test_linkedin_create_ad_requires_share_urn() -> None:
    from app.integrations.linkedin_ads import LinkedInAdsProvider

    with pytest.raises(ProviderError):
        LinkedInAdsProvider.create_ad(
            access_token="t", external_account_id="acct", ad_set_external_id="555",
            payload={"name": "Ad"},
        )


def test_linkedin_create_ad_sponsors_share() -> None:
    from app.integrations.linkedin_ads import LinkedInAdsProvider

    captured: dict = {}

    def _fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return _FakeResp({}, headers={"x-restli-id": "urn:li:sponsoredCreative:999"})

    with patch.object(httpx, "post", side_effect=_fake_post):
        result = LinkedInAdsProvider.create_ad(
            access_token="t", external_account_id="acct", ad_set_external_id="555",
            payload={"name": "Ad", "share_urn": "urn:li:share:123"},
        )
    assert result["external_id"] == "urn:li:sponsoredCreative:999"
    assert captured["url"].endswith("/creatives")
    assert captured["json"]["campaign"] == "urn:li:sponsoredCampaign:555"
    assert captured["json"]["content"]["reference"] == "urn:li:share:123"


def test_enrich_ad_payload_per_provider() -> None:
    from app.models.creative import Creative, CreativeSource, CreativeType
    from app.services.ad_publish_service import enrich_ad_payload

    creative = Creative(
        workspace_id=None, type=CreativeType.SINGLE_IMAGE, source=CreativeSource.USER_UPLOADED,
        headline="Big headline", primary_text="Body copy", description="More copy",
        metadata_json={"external_ids": {"meta_ads": "cr_1", "linkedin_share": "urn:li:share:7"}},
    )
    meta_p: dict = {}
    enrich_ad_payload(meta_p, creative, "meta_ads")
    assert meta_p["creative_id"] == "cr_1"

    google_p: dict = {}
    enrich_ad_payload(google_p, creative, "google_ads")
    assert google_p["headlines"] == ["Big headline"]
    assert google_p["descriptions"] == ["Body copy", "More copy"]

    li_p: dict = {}
    enrich_ad_payload(li_p, creative, "linkedin_ads")
    assert li_p["share_urn"] == "urn:li:share:7"


# ---------------------------------------------------------------------------
# Publish wiring (service + endpoint)
# ---------------------------------------------------------------------------


def test_publish_ad_group_one_click_admin(client: TestClient, db_session: Session) -> None:
    user, ws = _seed(db_session, email="o@example.com", role=Role.ADMIN)
    campaign = _live_campaign(db_session, ws=ws, user=user)
    ag = _draft_ad_group(db_session, ws=ws, campaign=campaign)
    _login(client, "o@example.com")

    fake = {"ok": True, "external_id": "as_99", "external_account_id": "act_42", "result": {"id": "as_99"}}
    with patch.object(MetaAdsProvider, "create_ad_set", return_value=fake) as m:
        resp = client.post(f"/api/v1/workspaces/{ws.id}/ad-groups/{ag.id}/publish")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "executed"
    assert body["external_id"] == "as_99"
    m.assert_called_once()

    db_session.expire_all()
    refreshed = db_session.get(AdGroup, ag.id)
    assert refreshed.external_id == "as_99"
    assert refreshed.source == AdObjectSource.PLATFORM_SYNCED


def test_publish_ad_group_queues_for_marketer(client: TestClient, db_session: Session) -> None:
    user, ws = _seed(db_session, email="m@example.com", role=Role.MARKETER)
    campaign = _live_campaign(db_session, ws=ws, user=user)
    ag = _draft_ad_group(db_session, ws=ws, campaign=campaign)
    _login(client, "m@example.com")

    with patch.object(MetaAdsProvider, "create_ad_set") as m:
        resp = client.post(f"/api/v1/workspaces/{ws.id}/ad-groups/{ag.id}/publish")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "queued"
    m.assert_not_called()  # nothing pushed until an admin approves

    db_session.expire_all()
    refreshed = db_session.get(AdGroup, ag.id)
    assert refreshed.external_id is None
    assert refreshed.source == AdObjectSource.ADVANTA_DRAFT


def test_publish_already_live_conflicts(client: TestClient, db_session: Session) -> None:
    user, ws = _seed(db_session, email="o@example.com")
    campaign = _live_campaign(db_session, ws=ws, user=user)
    ag = AdGroup(
        workspace_id=ws.id, campaign_id=campaign.id, external_id="existing",
        source=AdObjectSource.PLATFORM_SYNCED, name="AG", status=AdGroupStatus.ACTIVE,
        last_synced_at=datetime.now(timezone.utc),
    )
    db_session.add(ag)
    db_session.commit()
    _login(client, "o@example.com")
    resp = client.post(f"/api/v1/workspaces/{ws.id}/ad-groups/{ag.id}/publish")
    assert resp.status_code == 409


def test_publish_ad_before_ad_set_published(client: TestClient, db_session: Session) -> None:
    user, ws = _seed(db_session, email="o@example.com")
    campaign = _live_campaign(db_session, ws=ws, user=user)
    ag = _draft_ad_group(db_session, ws=ws, campaign=campaign)  # no external_id yet
    ad = Ad(
        workspace_id=ws.id, campaign_id=campaign.id, ad_group_id=ag.id, external_id=None,
        source=AdObjectSource.ADVANTA_DRAFT, name="Ad", status=AdStatus.PAUSED,
        last_synced_at=datetime.now(timezone.utc),
    )
    db_session.add(ad)
    db_session.commit()
    _login(client, "o@example.com")
    resp = client.post(f"/api/v1/workspaces/{ws.id}/ads/{ad.id}/publish")
    assert resp.status_code == 422


def test_publish_ad_group_campaign_missing_account(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    # Campaign without an external_account_id — can't address an ad-set create.
    campaign = Campaign(
        workspace_id=ws.id, provider="meta_ads", external_id="camp1", external_account_id=None,
        name="Draft", status=CampaignStatus.PAUSED, last_synced_at=datetime.now(timezone.utc),
        raw_payload={},
    )
    db_session.add(campaign)
    db_session.commit()
    ag = _draft_ad_group(db_session, ws=ws, campaign=campaign)
    _login(client, "o@example.com")
    resp = client.post(f"/api/v1/workspaces/{ws.id}/ad-groups/{ag.id}/publish")
    assert resp.status_code == 422
