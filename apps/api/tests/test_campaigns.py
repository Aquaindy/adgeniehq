from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations.base import CampaignData, ProviderError
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


# ---------------------------------------------------------------------------
# Provider sync (mocked HTTP)
# ---------------------------------------------------------------------------


class _StubResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_meta_ads_sync_normalizes_campaigns() -> None:
    accounts_payload = {
        "data": [{"id": "act_111", "name": "Acct One", "currency": "USD"}]
    }
    campaigns_payload = {
        "data": [
            {
                "id": "100",
                "name": "Brand Awareness Q2",
                "status": "ACTIVE",
                "objective": "OUTCOME_LEADS",
                "daily_budget": "5000",
                "lifetime_budget": "0",
                "start_time": "2026-04-01T00:00:00+0000",
                "stop_time": "2026-06-30T23:59:59+0000",
            },
            {
                "id": "101",
                "name": "Retargeting",
                "status": "PAUSED",
                "daily_budget": "2000",
            },
        ]
    }

    def _fake_get(url, params=None, **kwargs):
        if "/me/adaccounts" in url:
            return _StubResponse(200, accounts_payload)
        if "/act_111/campaigns" in url:
            return _StubResponse(200, campaigns_payload)
        raise AssertionError(f"unexpected URL: {url}")

    with patch("app.integrations.meta_ads.httpx.get", side_effect=_fake_get):
        results = MetaAdsProvider.sync_campaigns(access_token="token")

    assert len(results) == 2

    first = results[0]
    assert first.external_id == "100"
    assert first.status == CampaignStatus.ACTIVE
    assert first.daily_budget_cents == 5000
    assert first.currency == "USD"
    assert first.start_date == date(2026, 4, 1)
    assert first.end_date == date(2026, 6, 30)
    assert first.external_account_id == "act_111"

    second = results[1]
    assert second.status == CampaignStatus.PAUSED
    assert second.lifetime_budget_cents is None  # "0" maps to None


def test_meta_ads_sync_skips_account_on_campaign_error() -> None:
    accounts_payload = {
        "data": [
            {"id": "act_a", "name": "A", "currency": "USD"},
            {"id": "act_b", "name": "B", "currency": "USD"},
        ]
    }

    def _fake_get(url, **_):
        if "/me/adaccounts" in url:
            return _StubResponse(200, accounts_payload)
        if "/act_a/campaigns" in url:
            return _StubResponse(403, {"error": {"message": "permission"}})
        if "/act_b/campaigns" in url:
            return _StubResponse(200, {"data": [{"id": "9", "name": "OK", "status": "ACTIVE"}]})
        raise AssertionError(url)

    with patch("app.integrations.meta_ads.httpx.get", side_effect=_fake_get):
        results = MetaAdsProvider.sync_campaigns(access_token="t")

    assert len(results) == 1
    assert results[0].external_id == "9"


def test_meta_ads_sync_raises_on_account_listing_failure() -> None:
    def _fake_get(url, **_):
        return _StubResponse(401, {})

    with patch("app.integrations.meta_ads.httpx.get", side_effect=_fake_get), pytest.raises(
        ProviderError
    ):
        MetaAdsProvider.sync_campaigns(access_token="t")


# ---------------------------------------------------------------------------
# Helpers — seed workspace + connected account directly
# ---------------------------------------------------------------------------


def _seed_workspace(
    db: Session, *, role: Role = Role.OWNER, email: str = "alice@example.com"
) -> tuple[User, Workspace]:
    user = User(email=email, hashed_password=hash_password("correct-horse-9"), is_active=True)
    db.add(user)
    db.flush()
    workspace = Workspace(name="Acme", slug=f"acme-{email.split('@')[0]}")
    db.add(workspace)
    db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=workspace.id, user_id=user.id, role=role, status=MemberStatus.ACTIVE
        )
    )
    db.commit()
    return user, workspace


def _seed_connected_account(
    db: Session, *, workspace: Workspace, user: User, provider: str
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


def _login(client: TestClient, email: str) -> None:
    token = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct-horse-9"},
    ).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})


# ---------------------------------------------------------------------------
# Sync orchestration through the API
# ---------------------------------------------------------------------------


def test_sync_409_when_no_connected_ad_accounts(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    response = client.post(f"/api/v1/workspaces/{workspace.id}/campaigns/sync")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_connected_ad_accounts"


def test_sync_full_meta_ads_flow_persists_campaigns(
    client: TestClient, db_session: Session
) -> None:
    user, workspace = _seed_workspace(db_session)
    _seed_connected_account(db_session, workspace=workspace, user=user, provider="meta_ads")

    fake = [
        CampaignData(
            external_id="100",
            name="Brand Awareness",
            status=CampaignStatus.ACTIVE,
            external_account_id="act_111",
            objective="OUTCOME_LEADS",
            daily_budget_cents=5000,
            currency="USD",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 6, 30),
            raw={"id": "100"},
        ),
        CampaignData(
            external_id="101",
            name="Retargeting",
            status=CampaignStatus.PAUSED,
            external_account_id="act_111",
            currency="USD",
            raw={"id": "101"},
        ),
    ]

    _login(client, "alice@example.com")
    with patch(
        "app.integrations.meta_ads.MetaAdsProvider.sync_campaigns", return_value=fake
    ):
        response = client.post(f"/api/v1/workspaces/{workspace.id}/campaigns/sync")
    assert response.status_code == 201
    body = response.json()
    assert len(body["providers"]) == 1
    provider_result = body["providers"][0]
    assert provider_result["provider"] == "meta_ads"
    assert provider_result["status"] == "succeeded"
    assert provider_result["upserted"] == 2

    listing = client.get(f"/api/v1/workspaces/{workspace.id}/campaigns").json()
    assert len(listing) == 2
    names = {c["name"] for c in listing}
    assert names == {"Brand Awareness", "Retargeting"}

    summary = client.get(f"/api/v1/workspaces/{workspace.id}/campaigns/summary").json()
    assert summary["total"] == 2
    assert summary["active"] == 1
    assert summary["paused"] == 1
    assert summary["per_provider"] == {"meta_ads": 2}
    # An end_date in 2026 with `today` typically set to 2026-04-25 in this env;
    # validate the field exists rather than its exact bool to avoid date drift.
    assert "stale_active" in summary


def test_sync_records_failed_log_when_provider_raises(
    client: TestClient, db_session: Session
) -> None:
    user, workspace = _seed_workspace(db_session)
    _seed_connected_account(db_session, workspace=workspace, user=user, provider="meta_ads")

    _login(client, "alice@example.com")
    with patch(
        "app.integrations.meta_ads.MetaAdsProvider.sync_campaigns",
        side_effect=ProviderError("Meta /me/adaccounts returned HTTP 401."),
    ):
        response = client.post(f"/api/v1/workspaces/{workspace.id}/campaigns/sync")
    assert response.status_code == 201
    body = response.json()
    assert body["providers"][0]["status"] == "failed"
    assert "401" in body["providers"][0]["error"]


def test_sync_filters_to_specific_provider(
    client: TestClient, db_session: Session
) -> None:
    user, workspace = _seed_workspace(db_session)
    _seed_connected_account(db_session, workspace=workspace, user=user, provider="meta_ads")
    _seed_connected_account(db_session, workspace=workspace, user=user, provider="google_ads")

    _login(client, "alice@example.com")
    with patch(
        "app.integrations.meta_ads.MetaAdsProvider.sync_campaigns", return_value=[]
    ) as meta_mock, patch(
        "app.integrations.google_ads.GoogleAdsProvider.sync_campaigns", return_value=[]
    ) as g_mock:
        response = client.post(
            f"/api/v1/workspaces/{workspace.id}/campaigns/sync?provider=meta_ads"
        )
    assert response.status_code == 201
    assert meta_mock.called
    assert not g_mock.called


# ---------------------------------------------------------------------------
# Paid Ads Agent
# ---------------------------------------------------------------------------


def _seed_campaign(
    db: Session,
    *,
    workspace_id: UUID,
    provider: str = "meta_ads",
    status: CampaignStatus = CampaignStatus.ACTIVE,
    daily_budget_cents: int | None = 5000,
    end_date: date | None = None,
    name: str = "Test campaign",
) -> Campaign:
    row = Campaign(
        workspace_id=workspace_id,
        provider=provider,
        external_id=f"ext-{name}-{datetime.now(timezone.utc).timestamp()}",
        name=name,
        status=status,
        daily_budget_cents=daily_budget_cents,
        end_date=end_date,
        last_synced_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    return row


def test_paid_ads_agent_no_campaigns_yields_no_campaigns_recommendation(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/agents/run",
        json={"agent_type": "paid_ads"},
    )
    assert response.status_code == 201
    detail = response.json()
    types = {r["recommendation_type"] for r in detail["recommendations"]}
    assert "paid_ads.no_campaigns" in types


def test_paid_ads_agent_emits_budget_and_staleness_recommendations(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    _seed_campaign(
        db_session,
        workspace_id=workspace.id,
        daily_budget_cents=None,
        name="No-budget Active",
    )
    _seed_campaign(
        db_session,
        workspace_id=workspace.id,
        end_date=date(2025, 1, 1),
        name="Stale Active",
    )
    _seed_campaign(
        db_session,
        workspace_id=workspace.id,
        daily_budget_cents=10000,
        name="Healthy Active",
    )

    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/agents/run",
        json={"agent_type": "paid_ads"},
    )
    assert response.status_code == 201
    detail = response.json()
    types = [r["recommendation_type"] for r in detail["recommendations"]]
    assert "paid_ads.budget_unset" in types
    assert "paid_ads.stale_active" in types

    # Output payload exposes counts the dashboard can rely on
    assert detail["output_payload"]["active"] == 3
    assert detail["output_payload"]["active_without_budget"] == 1
    assert detail["output_payload"]["stale_active"] == 1


def test_paid_ads_agent_flags_single_platform_concentration(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    for i in range(3):
        _seed_campaign(
            db_session, workspace_id=workspace.id, name=f"Solo-{i}", daily_budget_cents=1000
        )

    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/agents/run",
        json={"agent_type": "paid_ads"},
    )
    detail = response.json()
    types = [r["recommendation_type"] for r in detail["recommendations"]]
    assert "paid_ads.single_platform" in types


# ---------------------------------------------------------------------------
# Endpoint-level: detail + role gate on sync
# ---------------------------------------------------------------------------


def test_get_campaign_detail_404_for_unknown_id(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    response = client.get(
        f"/api/v1/workspaces/{workspace.id}/campaigns/{__import__('uuid').uuid4()}"
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "campaign_not_found"


def test_sync_requires_marketer_role(
    client: TestClient, db_session: Session
) -> None:
    user, workspace = _seed_workspace(db_session, role=Role.VIEWER, email="viewer@example.com")
    _seed_connected_account(db_session, workspace=workspace, user=user, provider="meta_ads")
    _login(client, "viewer@example.com")
    response = client.post(f"/api/v1/workspaces/{workspace.id}/campaigns/sync")
    assert response.status_code == 403
