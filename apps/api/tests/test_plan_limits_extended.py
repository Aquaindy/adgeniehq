"""Plan-limit metering across the new resources + LLM token tracking.

Each test forces the workspace onto the `free` plan (the lowest cap) and
confirms that:
  * Hitting the cap raises 402 plan_limit_exceeded
  * Successful operations record a usage event (so the meter actually ticks)
  * The billing-status endpoint surfaces the 30-day count

LLM token tracking:
  * complete_metered persists a usage event with quantity = total tokens
  * When the cap is hit, the LLM client raises PlanLimitExceededError; skills
    that catch it fall back to the deterministic path rather than failing
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations.stripe import PLANS, Plan, PlanLimits
from app.models.usage_event import UsageEvent, UsageEventType
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role
from app.services import billing_service


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


def _seed_usage(
    db: Session,
    *,
    workspace_id,
    event_type: UsageEventType,
    count: int,
    quantity_each: int = 1,
) -> None:
    """Plant historical usage to push a workspace right up against its cap."""

    for _ in range(count):
        db.add(
            UsageEvent(
                workspace_id=workspace_id,
                event_type=event_type,
                quantity=quantity_each,
                occurred_at=datetime.now(timezone.utc),
            )
        )
    db.commit()


@pytest.fixture
def free_plan_only():
    """Pin the active plan calculation to `free` so every test sees the
    lowest cap regardless of the underlying subscription state."""

    def _free(db, *, workspace_id):  # noqa: ARG001
        return PLANS["free"]

    with patch.object(billing_service, "get_active_plan", side_effect=_free):
        yield


# ---------------------------------------------------------------------------
# Content drafts
# ---------------------------------------------------------------------------


def test_content_draft_cap_blocks_at_limit(
    client: TestClient, db_session: Session, free_plan_only
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")

    cap = PLANS["free"].limits.content_drafts_per_month
    assert cap is not None
    _seed_usage(
        db_session,
        workspace_id=ws.id,
        event_type=UsageEventType.CONTENT_DRAFT,
        count=cap,
    )

    response = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts",
        json={"type": "blog_post", "title": "X", "body": "Body"},
    )
    assert response.status_code == 402
    assert response.json()["error"]["code"] == "plan_limit_exceeded"


def test_content_draft_create_ticks_meter(
    client: TestClient, db_session: Session, free_plan_only
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")

    response = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts",
        json={"type": "blog_post", "title": "X", "body": "Body"},
    )
    assert response.status_code == 200, response.text

    used = billing_service.usage_in_last_30d(
        db_session,
        workspace_id=ws.id,
        event_type=UsageEventType.CONTENT_DRAFT,
    )
    assert used == 1


# ---------------------------------------------------------------------------
# Outreach
# ---------------------------------------------------------------------------


def test_outreach_send_cap_blocks_at_limit(
    client: TestClient, db_session: Session, free_plan_only
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")

    cap = PLANS["free"].limits.outreach_emails_per_month
    assert cap is not None
    _seed_usage(
        db_session,
        workspace_id=ws.id,
        event_type=UsageEventType.OUTREACH_EMAIL_SENT,
        count=cap,
    )

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
        send = client.post(
            f"/api/v1/workspaces/{ws.id}/outreach-emails/{eid}/send"
        )
    assert send.status_code == 402
    assert send.json()["error"]["code"] == "plan_limit_exceeded"


def test_outreach_successful_send_ticks_meter(
    client: TestClient, db_session: Session, free_plan_only
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
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

    used = billing_service.usage_in_last_30d(
        db_session,
        workspace_id=ws.id,
        event_type=UsageEventType.OUTREACH_EMAIL_SENT,
    )
    assert used == 1


# ---------------------------------------------------------------------------
# A/B tests
# ---------------------------------------------------------------------------


def test_ab_test_cap_blocks_at_limit(
    client: TestClient, db_session: Session, free_plan_only
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")

    cap = PLANS["free"].limits.ab_tests_per_month
    assert cap is not None
    _seed_usage(
        db_session,
        workspace_id=ws.id,
        event_type=UsageEventType.AB_TEST_CREATED,
        count=cap,
    )

    response = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests",
        json={
            "name": "Hero copy",
            "target": "landing_page",
            "objective": "conversion_rate",
            "variants": [
                {"name": "a", "traffic_share": 0.5, "payload": {"url": "https://x.com/a"}},
                {"name": "b", "traffic_share": 0.5, "payload": {"url": "https://x.com/b"}},
            ],
        },
    )
    assert response.status_code == 402


# ---------------------------------------------------------------------------
# Outbound writes
# ---------------------------------------------------------------------------


def test_outbound_write_cap_blocks_execute(
    client: TestClient, db_session: Session, free_plan_only
) -> None:
    """When a workspace is at its outbound-writes/30d cap, /approve with
    auto-execute (or a direct /execute) must refuse before any provider
    HTTP call goes out."""

    from datetime import datetime as _dt

    from app.integrations.meta_ads import MetaAdsProvider
    from app.models.agent_run import AgentRun, AgentRunStatus
    from app.models.approval import Approval, ApprovalStatus
    from app.models.connected_account import ConnectedAccount, ConnectionStatus
    from app.models.oauth_token import OAuthToken
    from app.models.recommendation import (
        Recommendation,
        RecommendationStatus,
        RiskLevel,
    )
    from app.security.encryption import encrypt

    user, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")

    # Seed a connected meta_ads account so the recommendation is actionable.
    account = ConnectedAccount(
        workspace_id=ws.id,
        provider="meta_ads",
        provider_account_id="ext-id",
        display_name="Test acct",
        status=ConnectionStatus.CONNECTED,
        connected_by=user.id,
        connected_at=_dt.now(timezone.utc),
    )
    db_session.add(account)
    db_session.flush()
    db_session.add(
        OAuthToken(
            connected_account_id=account.id,
            encrypted_access_token=encrypt("real-access-token"),
            encrypted_refresh_token=None,
        )
    )

    # Plant outbound-writes usage right at the cap.
    cap = PLANS["free"].limits.outbound_writes_per_month
    assert cap is not None
    _seed_usage(
        db_session,
        workspace_id=ws.id,
        event_type=UsageEventType.OUTBOUND_WRITE,
        count=cap,
    )

    run = AgentRun(
        workspace_id=ws.id,
        agent_type="paid_ads",
        status=AgentRunStatus.SUCCEEDED,
    )
    db_session.add(run)
    db_session.flush()
    rec = Recommendation(
        workspace_id=ws.id,
        agent_run_id=run.id,
        title="Pause campaign",
        summary="—",
        recommendation_type="campaign.pause",
        risk_level=RiskLevel.LOW,
        expected_impact="—",
        suggested_action="—",
        status=RecommendationStatus.OPEN,
        platform="meta_ads",
        metadata_json={
            "provider": "meta_ads",
            "action": "campaign.pause",
            "external_id": "100",
            "external_account_id": "act_42",
            "payload": {},
        },
    )
    db_session.add(rec)
    db_session.flush()
    db_session.add(
        Approval(
            workspace_id=ws.id,
            recommendation_id=rec.id,
            action_type=rec.recommendation_type,
            risk_level=rec.risk_level,
            status=ApprovalStatus.PENDING,
        )
    )
    db_session.commit()

    # The provider mock should never be called — the cap blocks before
    # _resolve_connection / dispatch.
    with patch.object(
        MetaAdsProvider,
        "pause_campaign",
        side_effect=AssertionError("must not be called when capped"),
    ):
        response = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/approve"
        )
    # Approve succeeded but the auto-execute was capped — caller sees 200
    # with the FAILED execution row carrying the plan_limit_exceeded error.
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recommendation"]["status"] == "approved"
    assert body["execution"]["status"] == "failed"
    assert "plan" in (body["execution"]["error_message"] or "").lower()


# ---------------------------------------------------------------------------
# LLM token tracking
# ---------------------------------------------------------------------------


def test_llm_call_persists_token_usage(
    client: TestClient, db_session: Session, free_plan_only
) -> None:
    """A successful LLM-backed content draft must record an LLM_CALL usage
    event with quantity = total tokens (so the cap can throttle by spend)."""

    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")

    import app.llm.client as llm_client
    from app.llm.client import LlmCompletion, OpenAIClient

    fake_completion = LlmCompletion(
        text='{"title":"T","body":"long enough body.","meta_title":"T","meta_description":"D","keywords":["a"]}',
        model="gpt-test",
        prompt_tokens=320,
        completion_tokens=180,
    )

    fake = OpenAIClient(api_key="sk-test", model="gpt-test")
    llm_client._INSTANCE = fake

    try:
        with patch.object(OpenAIClient, "complete", return_value=fake_completion):
            response = client.post(
                f"/api/v1/workspaces/{ws.id}/content-drafts/generate",
                json={"type": "blog_post", "topic": "Topic"},
            )
    finally:
        llm_client._INSTANCE = None

    assert response.status_code == 200, response.text

    used = billing_service.usage_in_last_30d(
        db_session, workspace_id=ws.id, event_type=UsageEventType.LLM_CALL
    )
    assert used == 500  # 320 + 180


def test_llm_cap_falls_back_to_deterministic(
    client: TestClient, db_session: Session, free_plan_only
) -> None:
    """When the LLM token cap is hit, the content-generation skill catches
    the plan-limit error and falls back to the deterministic template — the
    user still gets a draft, no 402 surfaces."""

    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")

    cap = PLANS["free"].limits.llm_tokens_per_month
    assert cap is not None
    # Plant usage that puts the workspace right at its token cap.
    _seed_usage(
        db_session,
        workspace_id=ws.id,
        event_type=UsageEventType.LLM_CALL,
        count=1,
        quantity_each=cap,
    )

    import app.llm.client as llm_client
    from app.llm.client import OpenAIClient

    fake = OpenAIClient(api_key="sk-test", model="gpt-test")
    llm_client._INSTANCE = fake

    try:
        with patch.object(
            OpenAIClient,
            "complete",
            side_effect=AssertionError("must not be called once capped"),
        ):
            response = client.post(
                f"/api/v1/workspaces/{ws.id}/content-drafts/generate",
                json={"type": "blog_post", "topic": "Some topic"},
            )
    finally:
        llm_client._INSTANCE = None

    assert response.status_code == 200, response.text
    body = response.json()
    # Deterministic fallback signature: source=agent, model_used=None.
    assert body["source"] == "agent"
    assert body["model_used"] is None


# ---------------------------------------------------------------------------
# Billing status surfaces all the new counters
# ---------------------------------------------------------------------------


def test_billing_status_returns_all_30d_counters(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")

    _seed_usage(
        db_session,
        workspace_id=ws.id,
        event_type=UsageEventType.CONTENT_DRAFT,
        count=2,
    )
    _seed_usage(
        db_session,
        workspace_id=ws.id,
        event_type=UsageEventType.OUTBOUND_WRITE,
        count=3,
    )
    _seed_usage(
        db_session,
        workspace_id=ws.id,
        event_type=UsageEventType.LLM_CALL,
        count=1,
        quantity_each=750,
    )

    resp = client.get(f"/api/v1/workspaces/{ws.id}/billing/status")
    assert resp.status_code == 200, resp.text
    usage = resp.json()["usage"]
    assert usage["content_drafts_last_30d"] == 2
    assert usage["outbound_writes_last_30d"] == 3
    assert usage["llm_tokens_last_30d"] == 750
    # Limits surface the new caps too.
    limits = resp.json()["plan"]["limits"]
    assert "llm_tokens_per_month" in limits
    assert "outbound_writes_per_month" in limits
