from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.approval import Approval, ApprovalStatus
from app.models.recommendation import Recommendation, RecommendationStatus, RiskLevel
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role


def _seed_workspace_with_member(
    db: Session, *, email: str, role: Role
) -> tuple[User, Workspace, WorkspaceMember]:
    user = User(email=email, hashed_password=hash_password("correct-horse-9"), is_active=True)
    db.add(user)
    db.flush()

    workspace = Workspace(name="Test", slug=f"test-{email.split('@')[0]}")
    db.add(workspace)
    db.flush()

    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=user.id,
        role=role,
        status=MemberStatus.ACTIVE,
    )
    db.add(member)
    db.commit()
    return user, workspace, member


def _seed_recommendation(
    db: Session, *, workspace_id, risk: RiskLevel
) -> Recommendation:
    run = AgentRun(
        workspace_id=workspace_id,
        agent_type="onboarding_insight",
        status=AgentRunStatus.SUCCEEDED,
    )
    db.add(run)
    db.flush()

    rec = Recommendation(
        workspace_id=workspace_id,
        agent_run_id=run.id,
        title="Tighten offer",
        summary="Expand to 2-3 sentences.",
        recommendation_type="onboarding.gap.offer",
        risk_level=risk,
        expected_impact="Sharpens generated copy.",
        suggested_action="Edit offer in onboarding.",
        status=RecommendationStatus.OPEN,
    )
    db.add(rec)
    db.flush()

    db.add(
        Approval(
            workspace_id=workspace_id,
            recommendation_id=rec.id,
            action_type=rec.recommendation_type,
            risk_level=risk,
            status=ApprovalStatus.PENDING,
        )
    )
    db.commit()
    db.refresh(rec)
    return rec


def _login(client: TestClient, email: str, password: str = "correct-horse-9") -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    token = response.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})


# ---------------------------------------------------------------------------
# Listing now includes approval state
# ---------------------------------------------------------------------------


def test_list_recommendations_includes_approval_snapshot(
    client: TestClient, db_session: Session
) -> None:
    _, workspace, _ = _seed_workspace_with_member(
        db_session, email="alice@example.com", role=Role.OWNER
    )
    _seed_recommendation(db_session, workspace_id=workspace.id, risk=RiskLevel.LOW)

    _login(client, "alice@example.com")
    response = client.get(f"/api/v1/workspaces/{workspace.id}/recommendations")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["approval"]["status"] == "pending"


# ---------------------------------------------------------------------------
# Approve flow
# ---------------------------------------------------------------------------


def test_approve_low_risk_succeeds_for_marketer(
    client: TestClient, db_session: Session
) -> None:
    _, workspace, _ = _seed_workspace_with_member(
        db_session, email="alice@example.com", role=Role.MARKETER
    )
    rec = _seed_recommendation(db_session, workspace_id=workspace.id, risk=RiskLevel.LOW)

    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/recommendations/{rec.id}/approve"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    rec_body = body["recommendation"]
    assert body["execution"] is None
    assert rec_body["status"] == "approved"
    assert rec_body["approval"]["status"] == "approved"
    assert rec_body["approval"]["approved_by"] is not None


def test_approve_medium_risk_blocked_for_marketer(
    client: TestClient, db_session: Session
) -> None:
    _, workspace, _ = _seed_workspace_with_member(
        db_session, email="alice@example.com", role=Role.MARKETER
    )
    rec = _seed_recommendation(db_session, workspace_id=workspace.id, risk=RiskLevel.MEDIUM)

    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/recommendations/{rec.id}/approve"
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_approve_high_risk_blocked_for_admin(
    client: TestClient, db_session: Session
) -> None:
    _, workspace, _ = _seed_workspace_with_member(
        db_session, email="alice@example.com", role=Role.ADMIN
    )
    rec = _seed_recommendation(db_session, workspace_id=workspace.id, risk=RiskLevel.HIGH)

    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/recommendations/{rec.id}/approve"
    )
    assert response.status_code == 403


def test_approve_high_risk_succeeds_for_owner(
    client: TestClient, db_session: Session
) -> None:
    _, workspace, _ = _seed_workspace_with_member(
        db_session, email="owner@example.com", role=Role.OWNER
    )
    rec = _seed_recommendation(db_session, workspace_id=workspace.id, risk=RiskLevel.HIGH)

    _login(client, "owner@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/recommendations/{rec.id}/approve"
    )
    assert response.status_code == 200
    assert response.json()["recommendation"]["approval"]["status"] == "approved"


# ---------------------------------------------------------------------------
# Reject + status transitions
# ---------------------------------------------------------------------------


def test_reject_then_re_approve_flips_status(
    client: TestClient, db_session: Session
) -> None:
    _, workspace, _ = _seed_workspace_with_member(
        db_session, email="alice@example.com", role=Role.OWNER
    )
    rec = _seed_recommendation(db_session, workspace_id=workspace.id, risk=RiskLevel.LOW)

    _login(client, "alice@example.com")
    rejected = client.post(
        f"/api/v1/workspaces/{workspace.id}/recommendations/{rec.id}/reject",
        json={"reason": "Already done."},
    )
    assert rejected.status_code == 200
    assert rejected.json()["approval"]["status"] == "rejected"

    re_approved = client.post(
        f"/api/v1/workspaces/{workspace.id}/recommendations/{rec.id}/approve"
    )
    assert re_approved.status_code == 200
    body = re_approved.json()["recommendation"]
    assert body["approval"]["status"] == "approved"
    assert body["approval"]["rejected_by"] is None


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


def test_edit_recommendation_requires_admin(
    client: TestClient, db_session: Session
) -> None:
    _, workspace, _ = _seed_workspace_with_member(
        db_session, email="alice@example.com", role=Role.MARKETER
    )
    rec = _seed_recommendation(db_session, workspace_id=workspace.id, risk=RiskLevel.LOW)

    _login(client, "alice@example.com")
    response = client.patch(
        f"/api/v1/workspaces/{workspace.id}/recommendations/{rec.id}",
        json={"title": "Edited title"},
    )
    assert response.status_code == 403


def test_edit_recommendation_succeeds_for_admin(
    client: TestClient, db_session: Session
) -> None:
    _, workspace, _ = _seed_workspace_with_member(
        db_session, email="admin@example.com", role=Role.ADMIN
    )
    rec = _seed_recommendation(db_session, workspace_id=workspace.id, risk=RiskLevel.LOW)

    _login(client, "admin@example.com")
    response = client.patch(
        f"/api/v1/workspaces/{workspace.id}/recommendations/{rec.id}",
        json={"title": "Edited title", "summary": "Edited summary."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Edited title"
    assert body["summary"] == "Edited summary."


# ---------------------------------------------------------------------------
# Audit log endpoint
# ---------------------------------------------------------------------------


def test_audit_log_records_approve_and_reject(
    client: TestClient, db_session: Session
) -> None:
    _, workspace, _ = _seed_workspace_with_member(
        db_session, email="owner@example.com", role=Role.OWNER
    )
    rec = _seed_recommendation(db_session, workspace_id=workspace.id, risk=RiskLevel.LOW)

    _login(client, "owner@example.com")
    client.post(f"/api/v1/workspaces/{workspace.id}/recommendations/{rec.id}/approve")
    client.post(
        f"/api/v1/workspaces/{workspace.id}/recommendations/{rec.id}/reject",
        json={"reason": "Changed my mind."},
    )

    response = client.get(
        f"/api/v1/workspaces/{workspace.id}/recommendations/{rec.id}/audit-logs"
    )
    assert response.status_code == 200
    entries = response.json()
    assert [e["action"] for e in entries] == ["recommendation.approved", "recommendation.rejected"]
    assert all(e["actor_type"] == "user" for e in entries)
    assert entries[1]["metadata"]["reason"] == "Changed my mind."


# ---------------------------------------------------------------------------
# Cross-workspace isolation
# ---------------------------------------------------------------------------


def test_cannot_approve_recommendation_from_other_workspace(
    client: TestClient, db_session: Session
) -> None:
    _, workspace_a, _ = _seed_workspace_with_member(
        db_session, email="alice@example.com", role=Role.OWNER
    )
    rec = _seed_recommendation(db_session, workspace_id=workspace_a.id, risk=RiskLevel.LOW)

    _, workspace_b, _ = _seed_workspace_with_member(
        db_session, email="bob@example.com", role=Role.OWNER
    )

    _login(client, "bob@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace_b.id}/recommendations/{rec.id}/approve"
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "recommendation_not_found"


# ---------------------------------------------------------------------------
# Runtime auto-creates an approval per recommendation (M5 invariant)
# ---------------------------------------------------------------------------


def test_running_agent_auto_creates_pending_approvals(
    client: TestClient,
) -> None:
    register = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "correct-horse-9"},
    )
    token = register.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    workspace_id = client.post(
        "/api/v1/workspaces", json={"name": "Acme"}
    ).json()["id"]
    client.post(
        f"/api/v1/workspaces/{workspace_id}/onboarding",
        json={
            "business_name": "Acme",
            "website_url": "https://acme.example",
            "target_audience": "founders",
            "offer_description": (
                "AdVanta is the AI growth command center that turns chaotic ad spend into "
                "measurable pipeline by deploying specialized agents across paid, SEO, and "
                "website conversion."
            ),
            "primary_conversion_goal": "Demo bookings",
            "step_completed": 5,
            "mark_completed": True,
        },
    )

    run = client.post(
        f"/api/v1/workspaces/{workspace_id}/agents/run",
        json={"agent_type": "onboarding_insight"},
    ).json()

    listing = client.get(f"/api/v1/workspaces/{workspace_id}/recommendations").json()
    assert len(listing) == len(run["recommendations"]) > 0
    assert all(r["approval"]["status"] == "pending" for r in listing)
