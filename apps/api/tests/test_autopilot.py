"""Autopilot Mode tests.

Goals:
- Default state is OFF; preview always returns `not_autopilot`.
- Cannot enter AUTOPILOT without complete guardrails.
- Stop-loss flag short-circuits everything.
- Risk ceiling + action allowlist + spend cap each block on their own.
- A passing rec is auto-approved with audit trail.
"""

from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.audit_log import AuditActorType, AuditLog
from app.models.autopilot_config import AutopilotMode
from app.models.recommendation import Recommendation, RiskLevel
from app.models.recommendation import RecommendationStatus
from app.services import autopilot_service


def _signup_and_workspace(client: TestClient) -> tuple[str, str]:
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "owner@example.com",
            "password": "correct-horse-9",
            "full_name": "Owner",
        },
    )
    token = register.json()["access_token"]
    user_id = register.json()["user"]["id"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    workspace = client.post("/api/v1/workspaces", json={"name": "Acme"}).json()
    return workspace["id"], user_id


def _seed_recommendation(
    db: Session,
    *,
    workspace_id: UUID,
    rec_type: str = "paid_ads.budget_unset",
    risk: RiskLevel = RiskLevel.LOW,
    metadata: dict | None = None,
) -> Recommendation:
    """Insert a stand-alone rec without requiring a real AgentRun.
    Bypasses the agent runtime; intended only for autopilot guardrail tests."""
    from app.models.agent_run import AgentRun, AgentRunStatus
    from app.models.workspace_member import WorkspaceMember

    owner = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == workspace_id)
        .first()
    )
    assert owner is not None, "Workspace must have at least one member to seed recs"

    run = AgentRun(
        workspace_id=workspace_id,
        triggered_by_user_id=owner.user_id,
        agent_type="paid_ads",
        status=AgentRunStatus.SUCCEEDED,
        input_payload={},
        model_used="deterministic",
    )
    db.add(run)
    db.flush()

    rec = Recommendation(
        workspace_id=workspace_id,
        agent_run_id=run.id,
        title="Test rec",
        summary="—",
        recommendation_type=rec_type,
        risk_level=risk,
        expected_impact="—",
        suggested_action="—",
        status=RecommendationStatus.OPEN,
        metadata_json=metadata or {},
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _enter_autopilot(client: TestClient, workspace_id: str, **overrides) -> dict:
    payload = {
        "mode": "autopilot",
        "max_daily_spend_increase_cents": 50_000,
        "max_daily_spend_total_cents": 200_000,
        "max_pct_increase_per_change": 20,
        "min_conversion_threshold": 5,
        "allowed_action_types": ["paid_ads.budget_unset"],
        "risk_ceiling": "medium",
    }
    payload.update(overrides)
    response = client.patch(
        f"/api/v1/workspaces/{workspace_id}/autopilot", json=payload
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------


def test_default_config_is_off(client: TestClient) -> None:
    workspace_id, _ = _signup_and_workspace(client)
    response = client.get(f"/api/v1/workspaces/{workspace_id}/autopilot")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "off"
    assert body["stop_loss_active"] is False


def test_cannot_enter_autopilot_without_guardrails(client: TestClient) -> None:
    workspace_id, _ = _signup_and_workspace(client)
    response = client.patch(
        f"/api/v1/workspaces/{workspace_id}/autopilot",
        json={"mode": "autopilot"},  # nothing else
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "autopilot_config_invalid"


def test_preview_marks_recs_when_autopilot_off(
    client: TestClient, db_session: Session
) -> None:
    workspace_id, _ = _signup_and_workspace(client)
    _seed_recommendation(db_session, workspace_id=UUID(workspace_id))

    response = client.get(f"/api/v1/workspaces/{workspace_id}/autopilot/preview")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["allow"] is False
    assert items[0]["reason"] == "not_autopilot"


def test_autopilot_blocks_when_risk_above_ceiling(
    client: TestClient, db_session: Session
) -> None:
    workspace_id, _ = _signup_and_workspace(client)
    _enter_autopilot(client, workspace_id, risk_ceiling="low")
    _seed_recommendation(
        db_session,
        workspace_id=UUID(workspace_id),
        risk=RiskLevel.HIGH,
    )

    response = client.get(f"/api/v1/workspaces/{workspace_id}/autopilot/preview")
    items = response.json()
    assert items[0]["allow"] is False
    assert items[0]["reason"].startswith("risk_above_ceiling")


def test_autopilot_blocks_when_action_not_allowed(
    client: TestClient, db_session: Session
) -> None:
    workspace_id, _ = _signup_and_workspace(client)
    _enter_autopilot(
        client,
        workspace_id,
        allowed_action_types=["seo.something_else"],
    )
    _seed_recommendation(
        db_session,
        workspace_id=UUID(workspace_id),
        rec_type="paid_ads.budget_unset",
    )

    items = client.get(
        f"/api/v1/workspaces/{workspace_id}/autopilot/preview"
    ).json()
    assert items[0]["allow"] is False
    assert items[0]["reason"].startswith("action_not_allowed")


def test_autopilot_blocks_when_stop_loss_active(
    client: TestClient, db_session: Session
) -> None:
    workspace_id, _ = _signup_and_workspace(client)
    _enter_autopilot(client, workspace_id)
    # Flip the stop-loss flag.
    response = client.patch(
        f"/api/v1/workspaces/{workspace_id}/autopilot",
        json={"stop_loss_active": True, "stop_loss_reason": "ROAS dropped 40%"},
    )
    assert response.status_code == 200

    _seed_recommendation(
        db_session,
        workspace_id=UUID(workspace_id),
        rec_type="paid_ads.budget_unset",
    )

    items = client.get(
        f"/api/v1/workspaces/{workspace_id}/autopilot/preview"
    ).json()
    assert items[0]["allow"] is False
    assert items[0]["reason"].startswith("stop_loss_active")


def test_autopilot_blocks_spend_above_cap(
    client: TestClient, db_session: Session
) -> None:
    workspace_id, _ = _signup_and_workspace(client)
    _enter_autopilot(client, workspace_id, max_daily_spend_increase_cents=10_000)
    _seed_recommendation(
        db_session,
        workspace_id=UUID(workspace_id),
        rec_type="paid_ads.budget_unset",
        metadata={"budget_increase_cents": 50_000},
    )
    items = client.get(
        f"/api/v1/workspaces/{workspace_id}/autopilot/preview"
    ).json()
    assert items[0]["allow"] is False
    assert items[0]["reason"] == "spend_increase_above_cap"


def test_autopilot_auto_approves_when_all_guardrails_pass(
    client: TestClient, db_session: Session
) -> None:
    workspace_id, user_id = _signup_and_workspace(client)
    _enter_autopilot(client, workspace_id)
    rec = _seed_recommendation(
        db_session,
        workspace_id=UUID(workspace_id),
        rec_type="paid_ads.budget_unset",
        metadata={
            "budget_increase_cents": 5_000,
            "pct_increase": 10,
            "recent_conversions": 12,
        },
    )

    summary = autopilot_service.auto_approve_pending(
        db_session,
        workspace_id=UUID(workspace_id),
        system_actor_id=UUID(user_id),
    )
    assert summary["approved"] == 1

    db_session.refresh(rec)
    assert rec.status == RecommendationStatus.APPROVED

    # Exactly ONE audit row per autopilot approval, tagged SYSTEM, with the
    # autopilot-specific action name. The legacy USER `recommendation.approved`
    # row must NOT be emitted in addition — that was the double-audit bug.
    autopilot_audits = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.workspace_id == UUID(workspace_id),
            AuditLog.action == "autopilot.approved",
        )
        .all()
    )
    assert len(autopilot_audits) == 1
    assert autopilot_audits[0].actor_type == AuditActorType.SYSTEM
    assert autopilot_audits[0].metadata_json.get("matched_rules"), (
        "matched_rules must be preserved on the autopilot audit row"
    )

    user_approval_audits = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.workspace_id == UUID(workspace_id),
            AuditLog.action == "recommendation.approved",
        )
        .all()
    )
    assert user_approval_audits == [], (
        "autopilot must not also emit a USER recommendation.approved row — "
        "that was the double-audit bug"
    )
