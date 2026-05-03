from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.campaign import Campaign, CampaignStatus
from app.models.recommendation import (
    Recommendation,
    RecommendationStatus,
    RiskLevel,
)
from app.models.report import ReportPeriod
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role
from app.services.report_renderer import render_csv, render_pdf
from app.services.report_service import period_window


# ---------------------------------------------------------------------------
# Period windows
# ---------------------------------------------------------------------------


def test_period_window_daily() -> None:
    anchor = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
    start, end = period_window(ReportPeriod.DAILY, anchor=anchor)
    assert (end - start).days == 1
    assert end == anchor


def test_period_window_weekly() -> None:
    anchor = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
    start, end = period_window(ReportPeriod.WEEKLY, anchor=anchor)
    assert (end - start).days == 7


def test_period_window_monthly() -> None:
    anchor = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
    start, end = period_window(ReportPeriod.MONTHLY, anchor=anchor)
    assert (end - start).days == 30


# ---------------------------------------------------------------------------
# Renderer unit tests
# ---------------------------------------------------------------------------


def test_render_pdf_returns_real_bytes_with_minimal_payload() -> None:
    payload = {
        "workspace": {"name": "Acme"},
        "period": {
            "type": "weekly",
            "label": "Weekly",
            "start": "2026-04-18T00:00:00+00:00",
            "end": "2026-04-25T00:00:00+00:00",
        },
        "summary": {"agent_runs_total": 0, "recommendations_by_status": {}, "recommendations_by_risk": {}},
        "agent_runs": [],
        "top_recommendations": [],
    }
    body = render_pdf(payload, title="Weekly report — Acme")
    assert body[:5] == b"%PDF-"
    assert len(body) > 1000


def test_render_csv_includes_recommendation_rows() -> None:
    payload = {
        "top_recommendations": [
            {
                "risk_level": "high",
                "title": "Stale active campaign",
                "recommendation_type": "paid_ads.stale_active",
                "platform": "google_ads",
                "expected_impact": "Stops wasteful spend",
                "suggested_action": "Pause the campaign in Google Ads.",
                "agent_run_id": "00000000-0000-0000-0000-000000000000",
                "created_at": "2026-04-25T00:00:00+00:00",
            }
        ]
    }
    body = render_csv(payload)
    text = body.decode("utf-8")
    assert "# top_recommendations" in text  # section marker
    assert "risk_level" in text  # header
    assert "Stale active campaign" in text
    assert "paid_ads.stale_active" in text


def test_render_csv_includes_post_m12_sections() -> None:
    """Post-M12 payload sections (executions, content_drafts, outreach,
    ab_tests) must surface in the CSV download. Each is gated by `total > 0`
    so empty workspaces render as the recommendations section only."""

    payload = {
        "top_recommendations": [],
        "executions": {
            "total": 3,
            "by_status": {"succeeded": 2, "failed": 1},
            "by_provider": {"google_ads": 2, "meta_ads": 1},
        },
        "content_drafts": {
            "total": 4,
            "by_status": {"draft": 2, "published": 2},
            "by_type": {"blog_post": 3, "landing_page": 1},
        },
        "outreach": {
            "emails_total": 10,
            "emails_sent": 8,
            "emails_replied": 2,
            "emails_bounced": 1,
            "reply_rate": 0.25,
            "prospects_total": 12,
            "prospects_won": 1,
        },
        "ab_tests": {
            "total": 2,
            "by_status": {"launched": 1, "completed": 1},
            "completed_with_winner": 1,
        },
    }
    body = render_csv(payload)
    text = body.decode("utf-8")

    assert "# executions" in text
    assert "by_status.succeeded,2" in text
    assert "by_provider.google_ads,2" in text
    assert "# content_drafts" in text
    assert "by_type.blog_post,3" in text
    assert "# outreach" in text
    assert "emails_sent,8" in text
    assert "reply_rate,0.2500" in text
    assert "# ab_tests" in text
    assert "completed_with_winner,1" in text


def test_render_pdf_with_post_m12_sections_returns_pdf_bytes() -> None:
    """End-to-end PDF render with all post-M12 sections populated. We don't
    parse the PDF — we just confirm reportlab successfully produced bytes
    (i.e. the new section helpers don't crash on real-shaped input)."""

    payload = {
        "workspace": {"name": "Acme"},
        "period": {
            "type": "weekly",
            "label": "Weekly",
            "start": "2026-04-18T00:00:00+00:00",
            "end": "2026-04-25T00:00:00+00:00",
        },
        "summary": {
            "agent_runs_total": 1,
            "recommendations_by_status": {"open": 1},
            "recommendations_by_risk": {"high": 1},
        },
        "executions": {
            "total": 5,
            "by_status": {"succeeded": 4, "failed": 1},
            "by_provider": {"google_ads": 5},
        },
        "content_drafts": {
            "total": 3,
            "by_status": {"draft": 2, "published": 1},
            "by_type": {"blog_post": 3},
        },
        "outreach": {
            "emails_total": 12,
            "emails_sent": 10,
            "emails_replied": 3,
            "emails_bounced": 0,
            "reply_rate": 0.3,
            "prospects_total": 14,
            "prospects_won": 2,
        },
        "ab_tests": {
            "total": 2,
            "by_status": {"launched": 1, "completed": 1},
            "completed_with_winner": 1,
        },
    }
    body = render_pdf(payload, title="Weekly — Acme")
    assert body[:5] == b"%PDF-"
    assert len(body) > 1500


# ---------------------------------------------------------------------------
# Helpers
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


def _login(client: TestClient, email: str) -> None:
    token = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct-horse-9"},
    ).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})


# ---------------------------------------------------------------------------
# Generation pulls real data
# ---------------------------------------------------------------------------


def test_generate_report_aggregates_real_workspace_data(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)

    # Seed some history within the weekly window
    run = AgentRun(
        workspace_id=workspace.id,
        agent_type="onboarding_insight",
        status=AgentRunStatus.SUCCEEDED,
    )
    db_session.add(run)
    db_session.flush()
    db_session.add_all(
        [
            Recommendation(
                workspace_id=workspace.id,
                agent_run_id=run.id,
                title="Tighten offer description",
                summary="Expand to 2-3 sentences.",
                recommendation_type="onboarding.gap.offer",
                risk_level=RiskLevel.HIGH,
                expected_impact="Sharpens copy.",
                suggested_action="Edit offer.",
                status=RecommendationStatus.OPEN,
            ),
            Recommendation(
                workspace_id=workspace.id,
                agent_run_id=run.id,
                title="Add brand voice",
                summary="Brand voice is undefined.",
                recommendation_type="onboarding.gap.brand_voice",
                risk_level=RiskLevel.LOW,
                expected_impact="Better generated copy.",
                suggested_action="Add a paragraph.",
                status=RecommendationStatus.APPROVED,
            ),
        ]
    )
    db_session.add(
        Campaign(
            workspace_id=workspace.id,
            provider="meta_ads",
            external_id="100",
            name="Brand Awareness",
            status=CampaignStatus.ACTIVE,
            daily_budget_cents=5000,
            currency="USD",
            last_synced_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/reports/generate",
        json={"period": "weekly"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "ready"

    summary = body["payload"]["summary"]
    assert summary["agent_runs_total"] == 1
    assert summary["recommendations_by_status"]["open"] == 1
    assert summary["recommendations_by_status"]["approved"] == 1
    assert summary["recommendations_by_risk"]["high"] == 1
    assert summary["campaigns_total"] == 1
    assert summary["campaigns_active"] == 1

    # Top recs only contain open, ordered by risk
    types = [r["recommendation_type"] for r in body["payload"]["top_recommendations"]]
    assert types == ["onboarding.gap.offer"]


def test_generate_report_excludes_data_outside_window(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    old = AgentRun(
        workspace_id=workspace.id,
        agent_type="paid_ads",
        status=AgentRunStatus.SUCCEEDED,
        created_at=datetime.now(timezone.utc) - timedelta(days=120),
    )
    db_session.add(old)
    db_session.commit()

    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/reports/generate",
        json={"period": "daily"},
    )
    assert response.status_code == 201
    summary = response.json()["payload"]["summary"]
    # The 120-day-old run must not appear in a daily report
    assert summary["agent_runs_total"] == 0


# ---------------------------------------------------------------------------
# Endpoints: list / detail / download / role gates
# ---------------------------------------------------------------------------


def test_list_then_detail(client: TestClient, db_session: Session) -> None:
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")

    created = client.post(
        f"/api/v1/workspaces/{workspace.id}/reports/generate",
        json={"period": "daily"},
    ).json()

    listing = client.get(f"/api/v1/workspaces/{workspace.id}/reports").json()
    assert len(listing) == 1
    assert listing[0]["id"] == created["id"]

    detail = client.get(
        f"/api/v1/workspaces/{workspace.id}/reports/{created['id']}"
    ).json()
    assert detail["payload"]["workspace"]["name"] == "Acme"


def test_download_pdf_and_csv(client: TestClient, db_session: Session) -> None:
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    created = client.post(
        f"/api/v1/workspaces/{workspace.id}/reports/generate",
        json={"period": "weekly"},
    ).json()

    pdf = client.get(
        f"/api/v1/workspaces/{workspace.id}/reports/{created['id']}/download?format=pdf"
    )
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content[:5] == b"%PDF-"

    csv_resp = client.get(
        f"/api/v1/workspaces/{workspace.id}/reports/{created['id']}/download?format=csv"
    )
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    assert b"risk_level" in csv_resp.content


def test_download_invalid_format_returns_400(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    created = client.post(
        f"/api/v1/workspaces/{workspace.id}/reports/generate",
        json={"period": "daily"},
    ).json()

    response = client.get(
        f"/api/v1/workspaces/{workspace.id}/reports/{created['id']}/download?format=docx"
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_format"


def test_generate_requires_marketer_role(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(
        db_session, role=Role.VIEWER, email="viewer@example.com"
    )
    _login(client, "viewer@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/reports/generate",
        json={"period": "daily"},
    )
    assert response.status_code == 403


def test_email_send_silently_skips_when_smtp_not_configured(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/reports/generate",
        json={"period": "daily", "email_to": "owner@example.com"},
    )
    assert response.status_code == 201
    assert response.json()["email_sent_at"] is None


def test_report_404_for_unknown_id(client: TestClient, db_session: Session) -> None:
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    response = client.get(
        f"/api/v1/workspaces/{workspace.id}/reports/{__import__('uuid').uuid4()}"
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "report_not_found"
