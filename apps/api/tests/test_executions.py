"""Tests for the outbound-write execution pipeline.

Covers:
  * Approval auto-executes when metadata carries an actionable plan
  * The right provider write method is called with the right args
  * prior_state is captured so revert is possible
  * Provider failures land as FAILED execution rows (approval still recorded)
  * Revert applies the inverse change and marks the original REVERTED
  * Revert is admin-only and can't be applied twice
"""

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
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.approval import Approval, ApprovalStatus
from app.models.connected_account import ConnectedAccount, ConnectionStatus
from app.models.oauth_token import OAuthToken
from app.models.recommendation import Recommendation, RecommendationStatus, RiskLevel
from app.models.recommendation_execution import (
    ExecutionStatus,
    RecommendationExecution,
)
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
    db: Session, *, email: str, role: Role
) -> tuple[User, Workspace, WorkspaceMember]:
    user = User(
        email=email, hashed_password=hash_password("correct-horse-9"), is_active=True
    )
    db.add(user)
    db.flush()
    ws = Workspace(name="Test", slug=f"test-{email.split('@')[0]}")
    db.add(ws)
    db.flush()
    member = WorkspaceMember(
        workspace_id=ws.id,
        user_id=user.id,
        role=role,
        status=MemberStatus.ACTIVE,
    )
    db.add(member)
    db.commit()
    return user, ws, member


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


def _seed_actionable_recommendation(
    db: Session,
    *,
    workspace: Workspace,
    risk: RiskLevel = RiskLevel.LOW,
    provider: str = "meta_ads",
    action: str = "campaign.pause",
    payload: dict | None = None,
) -> Recommendation:
    run = AgentRun(
        workspace_id=workspace.id,
        agent_type="paid_ads",
        status=AgentRunStatus.SUCCEEDED,
    )
    db.add(run)
    db.flush()

    rec = Recommendation(
        workspace_id=workspace.id,
        agent_run_id=run.id,
        title=f"{action}",
        summary="Wasted spend on a paused-objective campaign.",
        recommendation_type=action,
        risk_level=risk,
        expected_impact="Reduce daily spend by 30%.",
        suggested_action=f"Pause campaign and review.",
        status=RecommendationStatus.OPEN,
        platform=provider,
        metadata_json={
            "provider": provider,
            "action": action,
            "external_id": "100",
            "external_account_id": "act_42",
            "payload": payload or {},
        },
    )
    db.add(rec)
    db.flush()

    db.add(
        Approval(
            workspace_id=workspace.id,
            recommendation_id=rec.id,
            action_type=rec.recommendation_type,
            risk_level=risk,
            status=ApprovalStatus.PENDING,
        )
    )
    db.commit()
    db.refresh(rec)
    return rec


def _login(client: TestClient, email: str) -> None:
    resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-9"}
    )
    token = resp.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})


@pytest.fixture(autouse=True)
def _meta_creds():
    """Provider classes refuse to dispatch unless the env credentials look set;
    we provide harmless dummies for every test in this module."""

    keys = {
        "META_APP_ID": "test-app",
        "META_APP_SECRET": "test-secret",
        "GOOGLE_CLIENT_ID": "g",
        "GOOGLE_CLIENT_SECRET": "s",
        "GOOGLE_ADS_DEVELOPER_TOKEN": "dev-token",
        "LINKEDIN_CLIENT_ID": "li",
        "LINKEDIN_CLIENT_SECRET": "li-s",
    }
    saved = {k: os.environ.get(k) for k in keys}
    os.environ.update(keys)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# Approve + auto-execute
# ---------------------------------------------------------------------------


def test_approve_auto_executes_meta_pause(
    client: TestClient, db_session: Session
) -> None:
    user, ws, _ = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _seed_connected_account(db_session, workspace=ws, user=user, provider="meta_ads")
    rec = _seed_actionable_recommendation(
        db_session, workspace=ws, provider="meta_ads", action="campaign.pause"
    )

    captured: dict = {}

    def fake_pause(*, access_token, external_account_id, external_id):
        captured["access_token"] = access_token
        captured["external_account_id"] = external_account_id
        captured["external_id"] = external_id
        return {
            "ok": True,
            "prior_state": {"status": "ACTIVE"},
            "result": {"id": external_id, "status": "PAUSED"},
        }

    _login(client, "alice@example.com")
    with patch.object(MetaAdsProvider, "pause_campaign", side_effect=fake_pause):
        response = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/approve"
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recommendation"]["status"] == "executed"
    assert body["recommendation"]["approval"]["status"] == "executed"
    assert body["execution"]["status"] == "succeeded"
    assert body["execution"]["prior_state"] == {"status": "ACTIVE"}
    assert body["execution"]["target_external_id"] == "100"
    # Provider got the decrypted token, not the encrypted one.
    assert captured["access_token"] == "real-access-token"
    assert captured["external_id"] == "100"


def test_approve_skips_execute_when_no_metadata_action(
    client: TestClient, db_session: Session
) -> None:
    """Recommendations without metadata.action must not trigger any provider call."""

    user, ws, _ = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _seed_connected_account(db_session, workspace=ws, user=user, provider="meta_ads")
    run = AgentRun(
        workspace_id=ws.id, agent_type="paid_ads", status=AgentRunStatus.SUCCEEDED
    )
    db_session.add(run)
    db_session.flush()
    rec = Recommendation(
        workspace_id=ws.id,
        agent_run_id=run.id,
        title="advisor-only",
        summary="No action plan.",
        recommendation_type="paid_ads.note",
        risk_level=RiskLevel.LOW,
        expected_impact="—",
        suggested_action="—",
        status=RecommendationStatus.OPEN,
        platform="meta_ads",
        metadata_json={},  # no `action` key
    )
    db_session.add(rec)
    db_session.flush()
    db_session.add(
        Approval(
            workspace_id=ws.id,
            recommendation_id=rec.id,
            action_type="paid_ads.note",
            risk_level=RiskLevel.LOW,
            status=ApprovalStatus.PENDING,
        )
    )
    db_session.commit()

    _login(client, "alice@example.com")
    with patch.object(
        MetaAdsProvider,
        "pause_campaign",
        side_effect=AssertionError("must not be called"),
    ):
        response = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/approve"
        )
    assert response.status_code == 200
    assert response.json()["execution"] is None
    assert response.json()["recommendation"]["status"] == "approved"


def test_approve_with_auto_execute_false_does_not_execute(
    client: TestClient, db_session: Session
) -> None:
    user, ws, _ = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _seed_connected_account(db_session, workspace=ws, user=user, provider="meta_ads")
    rec = _seed_actionable_recommendation(db_session, workspace=ws)

    _login(client, "alice@example.com")
    with patch.object(
        MetaAdsProvider, "pause_campaign", side_effect=AssertionError("nope")
    ):
        response = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/approve",
            json={"auto_execute": False},
        )
    assert response.status_code == 200
    assert response.json()["execution"] is None
    assert response.json()["recommendation"]["status"] == "approved"


def test_provider_failure_records_failed_execution_row(
    client: TestClient, db_session: Session
) -> None:
    """A 4xx from the provider should end up as a FAILED execution row + audit
    log entry; the approval status stays 'approved' so the user can retry."""

    user, ws, _ = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _seed_connected_account(db_session, workspace=ws, user=user, provider="meta_ads")
    rec = _seed_actionable_recommendation(db_session, workspace=ws)

    from app.integrations.base import ProviderError

    _login(client, "alice@example.com")
    with patch.object(
        MetaAdsProvider, "pause_campaign", side_effect=ProviderError("Meta says no.")
    ):
        response = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/approve"
        )
    # Approval succeeded (decision is recorded); the execution row reflects the
    # provider failure so the user can retry once the underlying issue is fixed.
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recommendation"]["status"] == "approved"
    assert body["execution"]["status"] == "failed"
    assert "Meta says no" in (body["execution"]["error_message"] or "")
    rows = (
        db_session.query(RecommendationExecution)
        .filter(RecommendationExecution.recommendation_id == rec.id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].status == ExecutionStatus.FAILED


def test_execute_endpoint_supports_retry_after_failure(
    client: TestClient, db_session: Session
) -> None:
    user, ws, _ = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _seed_connected_account(db_session, workspace=ws, user=user, provider="meta_ads")
    rec = _seed_actionable_recommendation(db_session, workspace=ws)

    from app.integrations.base import ProviderError

    _login(client, "alice@example.com")
    with patch.object(
        MetaAdsProvider, "pause_campaign", side_effect=ProviderError("transient")
    ):
        client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/approve",
            json={"auto_execute": False},
        )
        retry_fail = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/execute"
        )
    assert retry_fail.status_code == 502

    # Now succeed.
    with patch.object(
        MetaAdsProvider,
        "pause_campaign",
        return_value={
            "ok": True,
            "prior_state": {"status": "ACTIVE"},
            "result": {"id": "100"},
        },
    ):
        retry_ok = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/execute"
        )
    assert retry_ok.status_code == 200
    assert retry_ok.json()["status"] == "succeeded"


# ---------------------------------------------------------------------------
# Revert
# ---------------------------------------------------------------------------


def test_revert_reapplies_prior_status(
    client: TestClient, db_session: Session
) -> None:
    user, ws, _ = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _seed_connected_account(db_session, workspace=ws, user=user, provider="meta_ads")
    rec = _seed_actionable_recommendation(db_session, workspace=ws)

    _login(client, "alice@example.com")
    with patch.object(
        MetaAdsProvider,
        "pause_campaign",
        return_value={
            "ok": True,
            "prior_state": {"status": "ACTIVE"},
            "result": {"id": "100", "status": "PAUSED"},
        },
    ):
        approve_resp = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/approve"
        )
    exec_id = approve_resp.json()["execution"]["id"]

    with patch.object(
        MetaAdsProvider,
        "resume_campaign",
        return_value={
            "ok": True,
            "prior_state": {"status": "PAUSED"},
            "result": {"id": "100", "status": "ACTIVE"},
        },
    ) as resume_mock:
        revert_resp = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/executions/{exec_id}/revert"
        )
    assert revert_resp.status_code == 200, revert_resp.text
    assert revert_resp.json()["is_revert"] is True
    assert revert_resp.json()["status"] == "succeeded"
    resume_mock.assert_called_once()

    # Original execution flips to REVERTED.
    db_session.expire_all()
    original = (
        db_session.query(RecommendationExecution)
        .filter(RecommendationExecution.id == exec_id)
        .first()
    )
    assert original.status == ExecutionStatus.REVERTED


def test_revert_requires_admin(
    client: TestClient, db_session: Session
) -> None:
    user, ws, _ = _seed_workspace(
        db_session, email="alice@example.com", role=Role.MARKETER
    )
    _seed_connected_account(db_session, workspace=ws, user=user, provider="meta_ads")
    rec = _seed_actionable_recommendation(db_session, workspace=ws)

    _login(client, "alice@example.com")
    with patch.object(
        MetaAdsProvider,
        "pause_campaign",
        return_value={
            "ok": True,
            "prior_state": {"status": "ACTIVE"},
            "result": {"id": "100"},
        },
    ):
        approve_resp = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/approve"
        )
    exec_id = approve_resp.json()["execution"]["id"]

    revert_resp = client.post(
        f"/api/v1/workspaces/{ws.id}/recommendations/executions/{exec_id}/revert"
    )
    assert revert_resp.status_code == 403


def test_revert_of_revert_rejected(
    client: TestClient, db_session: Session
) -> None:
    user, ws, _ = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _seed_connected_account(db_session, workspace=ws, user=user, provider="meta_ads")
    rec = _seed_actionable_recommendation(db_session, workspace=ws)

    _login(client, "alice@example.com")
    with patch.object(
        MetaAdsProvider,
        "pause_campaign",
        return_value={
            "ok": True,
            "prior_state": {"status": "ACTIVE"},
            "result": {"id": "100"},
        },
    ), patch.object(
        MetaAdsProvider,
        "resume_campaign",
        return_value={"ok": True, "result": {"id": "100"}},
    ):
        approve_resp = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/approve"
        )
        exec_id = approve_resp.json()["execution"]["id"]
        revert_resp = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/executions/{exec_id}/revert"
        )
        revert_id = revert_resp.json()["id"]
        # Try to revert the revert.
        second = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/executions/{revert_id}/revert"
        )
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "invalid_action"


# ---------------------------------------------------------------------------
# Provider write methods (mocked HTTP)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, body: dict | None = None, headers: dict | None = None):
        self.status_code = status_code
        self._body = body or {}
        self.headers = headers or {}
        self.content = b"" if body is None else b"x"
        self.text = ""

    def json(self):
        return self._body


def test_meta_pause_campaign_calls_graph_api():
    calls: list = []

    def fake_get(url, params=None, **kw):
        calls.append(("get", url))
        return _FakeResponse(200, {"id": "100", "status": "ACTIVE"})

    def fake_post(url, data=None, **kw):
        calls.append(("post", url, data))
        return _FakeResponse(200, {"success": True})

    with patch.object(httpx, "get", side_effect=fake_get), patch.object(
        httpx, "post", side_effect=fake_post
    ):
        result = MetaAdsProvider.pause_campaign(
            access_token="tok", external_account_id="act_42", external_id="100"
        )
    assert result["prior_state"] == {"status": "ACTIVE"}
    # First a GET to read prior, then a POST to flip status to PAUSED.
    assert calls[0][0] == "get"
    assert calls[1][0] == "post"
    # POST body carries status=PAUSED.
    assert calls[1][2]["status"] == "PAUSED"


def test_linkedin_partial_update_uses_required_header():
    headers_seen: dict = {}

    def fake_get(url, headers=None, **kw):
        headers_seen["get"] = headers or {}
        return _FakeResponse(200, {"status": "ACTIVE", "dailyBudget": {"amount": "10.00", "currencyCode": "USD"}})

    def fake_post(url, headers=None, json=None, **kw):
        headers_seen["post"] = headers or {}
        headers_seen["body"] = json
        return _FakeResponse(204, body=None)

    with patch.object(httpx, "get", side_effect=fake_get), patch.object(
        httpx, "post", side_effect=fake_post
    ):
        LinkedInAdsProvider.update_campaign_budget(
            access_token="tok",
            external_account_id="500001",
            external_id="200",
            daily_budget_cents=2500,
        )
    assert headers_seen["post"]["X-RestLi-Method"] == "PARTIAL_UPDATE"
    assert headers_seen["body"]["patch"]["$set"]["dailyBudget"]["amount"] == "25.00"


def test_google_ads_update_budget_resolves_budget_id():
    seen: list = []

    def fake_post(url, headers=None, json=None, **kw):
        seen.append((url, json))
        # First call: the SELECT for prior state.
        if "googleAds:search" in url:
            return _FakeResponse(
                200,
                {
                    "results": [
                        {
                            "campaign": {
                                "id": "100",
                                "name": "X",
                                "status": "ENABLED",
                                "campaignBudget": "customers/42/campaignBudgets/77",
                            },
                            "campaignBudget": {"id": "77", "amountMicros": "10000000"},
                        }
                    ]
                },
            )
        return _FakeResponse(200, {"results": [{"resourceName": "customers/42/campaignBudgets/77"}]})

    with patch.object(httpx, "post", side_effect=fake_post):
        result = GoogleAdsProvider.update_campaign_budget(
            access_token="tok",
            external_account_id="42",
            external_id="100",
            daily_budget_cents=5000,
        )
    # Three POSTs: one search (prior), one mutate.
    assert any("googleAds:search" in url for url, _ in seen)
    assert any("campaignBudgets:mutate" in url for url, _ in seen)
    # 5000 cents => 50_000_000 micros
    mutate_call = next((b for url, b in seen if "campaignBudgets:mutate" in url), None)
    assert mutate_call["operations"][0]["update"]["amountMicros"] == "50000000"
    assert result["prior_state"]["daily_budget_cents"] == 1000  # 10_000_000 micros / 10_000


# ---------------------------------------------------------------------------
# Google Ads audience update — prior_state must capture created resourceNames
# so the revert path can build inverse `remove` ops, not re-apply the same
# create ops.
# ---------------------------------------------------------------------------


def test_google_ads_audience_update_captures_created_resource_names():
    def fake_post(url, headers=None, json=None, **kw):
        return _FakeResponse(
            200,
            {
                "results": [
                    {"resourceName": "customers/42/adGroupCriteria/1~2001"},
                    {"resourceName": "customers/42/adGroupCriteria/1~2002"},
                ]
            },
        )

    create_ops = [
        {"create": {"adGroup": "customers/42/adGroups/1", "keyword": {"text": "foo"}}},
        {"create": {"adGroup": "customers/42/adGroups/1", "keyword": {"text": "bar"}}},
    ]
    with patch.object(httpx, "post", side_effect=fake_post):
        result = GoogleAdsProvider.update_campaign_audience(
            access_token="tok",
            external_account_id="42",
            external_id="100",
            targeting={"operations": create_ops},
        )
    assert result["prior_state"]["created_resource_names"] == [
        "customers/42/adGroupCriteria/1~2001",
        "customers/42/adGroupCriteria/1~2002",
    ]
    # Original ops are kept for diagnostics but are NOT what we use to revert.
    assert result["prior_state"]["operations"] == create_ops


def test_revert_google_ads_audience_create_sends_remove_ops(
    client: TestClient, db_session: Session
) -> None:
    """End-to-end: approve a Google Ads audience-add recommendation, then
    revert. The revert must call update_campaign_audience again — but with
    `remove` ops targeting the resourceNames returned by the original mutate."""

    user, ws, _ = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _seed_connected_account(db_session, workspace=ws, user=user, provider="google_ads")
    rec = _seed_actionable_recommendation(
        db_session,
        workspace=ws,
        provider="google_ads",
        action="campaign.update_audience",
        payload={
            "targeting": {
                "operations": [
                    {"create": {"adGroup": "customers/42/adGroups/1", "keyword": {"text": "foo"}}},
                ]
            }
        },
    )

    captured: list[dict] = []

    def fake_audience_update(*, access_token, external_account_id, external_id, targeting):
        captured.append(targeting)
        if len(captured) == 1:
            # Initial approval — mimic the real provider's prior_state shape.
            return {
                "ok": True,
                "prior_state": {
                    "operations": targeting.get("operations"),
                    "created_resource_names": [
                        "customers/42/adGroupCriteria/1~2001",
                    ],
                    "removed_resource_names": [],
                },
                "result": {"results": [{"resourceName": "customers/42/adGroupCriteria/1~2001"}]},
            }
        # Second call (the revert) — return success regardless of payload.
        return {"ok": True, "prior_state": {}, "result": {"results": []}}

    _login(client, "alice@example.com")
    with patch.object(
        GoogleAdsProvider,
        "update_campaign_audience",
        side_effect=fake_audience_update,
    ):
        approve = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/approve"
        )
        assert approve.status_code == 200, approve.text
        exec_id = approve.json()["execution"]["id"]

        revert = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/executions/{exec_id}/revert"
        )

    assert revert.status_code == 200, revert.text
    # Two calls: original create + the revert.
    assert len(captured) == 2
    revert_ops = captured[1].get("operations") or []
    # The revert must turn the created resourceName into a remove op.
    assert revert_ops == [{"remove": "customers/42/adGroupCriteria/1~2001"}]


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_execute_with_same_idempotency_key_returns_existing_row(
    client: TestClient, db_session: Session
) -> None:
    """A retried POST with the same Idempotency-Key must replay the prior
    execution — never dispatch a second provider call."""

    user, ws, _ = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _seed_connected_account(db_session, workspace=ws, user=user, provider="meta_ads")
    rec = _seed_actionable_recommendation(db_session, workspace=ws)

    _login(client, "alice@example.com")
    # First approve normally so the recommendation is APPROVED but not yet executed.
    with patch.object(
        MetaAdsProvider,
        "pause_campaign",
        side_effect=AssertionError("must not run on approve"),
    ):
        approve = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/approve",
            json={"auto_execute": False},
        )
    assert approve.status_code == 200, approve.text

    call_count = {"n": 0}

    def fake_pause(*, access_token, external_account_id, external_id):
        call_count["n"] += 1
        return {
            "ok": True,
            "prior_state": {"status": "ACTIVE"},
            "result": {"id": external_id, "call_index": call_count["n"]},
        }

    key = "retry-abc-123"
    with patch.object(MetaAdsProvider, "pause_campaign", side_effect=fake_pause):
        first = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/execute",
            headers={"Idempotency-Key": key},
        )
        second = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/execute",
            headers={"Idempotency-Key": key},
        )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]
    # Critically: only one provider call was made.
    assert call_count["n"] == 1


def test_execute_without_key_blocks_double_dispatch_when_succeeded(
    client: TestClient, db_session: Session
) -> None:
    """Without an Idempotency-Key, a second /execute on a recommendation that
    already has a SUCCEEDED execution must 409 — not run a second write."""

    user, ws, _ = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _seed_connected_account(db_session, workspace=ws, user=user, provider="meta_ads")
    rec = _seed_actionable_recommendation(db_session, workspace=ws)

    _login(client, "alice@example.com")
    with patch.object(
        MetaAdsProvider,
        "pause_campaign",
        return_value={
            "ok": True,
            "prior_state": {"status": "ACTIVE"},
            "result": {"id": "100"},
        },
    ):
        approve = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/approve"
        )
    assert approve.status_code == 200

    # /execute without a key — should refuse with 409 because we already have
    # a SUCCEEDED execution from the auto-execute on approve.
    with patch.object(
        MetaAdsProvider,
        "pause_campaign",
        side_effect=AssertionError("must not run a second time"),
    ):
        retry = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/execute"
        )
    assert retry.status_code == 409
    assert retry.json()["error"]["code"] == "duplicate_execution"


def test_failed_execution_can_be_retried_without_key(
    client: TestClient, db_session: Session
) -> None:
    """A FAILED prior execution shouldn't block a retry — that's the whole
    point of /execute."""

    user, ws, _ = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _seed_connected_account(db_session, workspace=ws, user=user, provider="meta_ads")
    rec = _seed_actionable_recommendation(db_session, workspace=ws)

    from app.integrations.base import ProviderError

    _login(client, "alice@example.com")
    with patch.object(
        MetaAdsProvider, "pause_campaign", side_effect=ProviderError("transient")
    ):
        client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/approve",
            json={"auto_execute": False},
        )
        first = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/execute"
        )
    assert first.status_code == 502

    # Now succeed.
    with patch.object(
        MetaAdsProvider,
        "pause_campaign",
        return_value={
            "ok": True,
            "prior_state": {"status": "ACTIVE"},
            "result": {"id": "100"},
        },
    ):
        second = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/execute"
        )
    assert second.status_code == 200
    assert second.json()["status"] == "succeeded"


def test_retried_approve_does_not_double_execute(
    client: TestClient, db_session: Session
) -> None:
    """Even if the user manages to send POST /approve twice (network retry),
    the auto-derived idempotency key (`approval:<id>`) means the second call
    returns the same execution row — no second provider write."""

    user, ws, _ = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _seed_connected_account(db_session, workspace=ws, user=user, provider="meta_ads")
    rec = _seed_actionable_recommendation(db_session, workspace=ws)

    call_count = {"n": 0}

    def fake_pause(*, access_token, external_account_id, external_id):
        call_count["n"] += 1
        return {
            "ok": True,
            "prior_state": {"status": "ACTIVE"},
            "result": {"id": external_id},
        }

    _login(client, "alice@example.com")
    with patch.object(MetaAdsProvider, "pause_campaign", side_effect=fake_pause):
        first = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/approve"
        )
    # First approve succeeds + auto-executes.
    assert first.status_code == 200
    assert first.json()["execution"]["status"] == "succeeded"

    # Second POST /approve — the recommendation is already APPROVED so the
    # decision step refuses with 409. Confirms we never get as far as
    # double-firing the provider call.
    with patch.object(
        MetaAdsProvider,
        "pause_campaign",
        side_effect=AssertionError("must not be called twice"),
    ):
        second = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/approve"
        )
    assert second.status_code == 409
    assert call_count["n"] == 1


def test_revert_google_ads_audience_remove_only_fails_loudly(
    client: TestClient, db_session: Session
) -> None:
    """We can't restore a removed criterion — it requires a snapshot we don't
    capture. Surface that gap as a clear 4xx instead of pretending to revert."""

    user, ws, _ = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _seed_connected_account(db_session, workspace=ws, user=user, provider="google_ads")
    rec = _seed_actionable_recommendation(
        db_session,
        workspace=ws,
        provider="google_ads",
        action="campaign.update_audience",
        payload={
            "targeting": {
                "operations": [
                    {"remove": "customers/42/adGroupCriteria/1~2001"},
                ]
            }
        },
    )

    def remove_only(*, access_token, external_account_id, external_id, targeting):
        return {
            "ok": True,
            "prior_state": {
                "operations": targeting.get("operations"),
                "created_resource_names": [],
                "removed_resource_names": ["customers/42/adGroupCriteria/1~2001"],
            },
            "result": {"results": []},
        }

    _login(client, "alice@example.com")
    with patch.object(
        GoogleAdsProvider,
        "update_campaign_audience",
        side_effect=remove_only,
    ):
        approve = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/approve"
        )
        exec_id = approve.json()["execution"]["id"]
        revert = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/executions/{exec_id}/revert"
        )

    assert revert.status_code == 400
    assert revert.json()["error"]["code"] == "invalid_action"
    assert "snapshot" in revert.json()["error"]["message"].lower()


def test_execute_refuses_when_account_missing_write_scope(
    client: TestClient, db_session: Session
) -> None:
    """When the connected account's recorded scopes don't include the
    provider's write_scopes, _resolve_connection refuses the write rather
    than letting the integration round-trip a 403 from the platform."""
    user, ws, _ = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    account = _seed_connected_account(
        db_session, workspace=ws, user=user, provider="meta_ads"
    )
    # Connect the account with READ-ONLY scopes — no `ads_management`.
    account.scopes = ["ads_read", "business_management"]
    db_session.commit()

    rec = _seed_actionable_recommendation(db_session, workspace=ws)

    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/approve"
    )
    # The approve still succeeds (the recommendation is approved + the
    # FAILED execution row is recorded); the guard surfaces in the row's
    # error_message.
    assert response.status_code == 200
    body = response.json()
    assert body["execution"] is not None
    assert body["execution"]["status"] == "failed"
    assert "missing write scopes" in (
        body["execution"].get("error_message") or ""
    ).lower()


def test_execute_succeeds_when_write_scope_present(
    client: TestClient, db_session: Session
) -> None:
    """Sanity counter-test: with the right write scope, the guard passes."""
    user, ws, _ = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    account = _seed_connected_account(
        db_session, workspace=ws, user=user, provider="meta_ads"
    )
    account.scopes = ["ads_read", "ads_management", "business_management"]
    db_session.commit()

    rec = _seed_actionable_recommendation(db_session, workspace=ws)

    _login(client, "alice@example.com")
    with patch.object(
        MetaAdsProvider,
        "pause_campaign",
        return_value={
            "external_id": "cmp-1",
            "external_account_id": "act_1",
            "prior_state": {"status": "active"},
            "result": {"id": "cmp-1", "status": "paused"},
        },
    ):
        response = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/approve"
        )
    assert response.status_code == 200
    assert response.json()["execution"]["status"] == "succeeded"
