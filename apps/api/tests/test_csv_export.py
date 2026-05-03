"""CSV export tests.

Goal: every column header in the rendered CSV must correspond to an actual
attribute on the underlying model (or be a documented derived field). A
previous bug emitted columns named after fields that did not exist on the
model — they downloaded as empty strings.

These tests build one real row per resource and assert the rendered CSV
contains the seeded value under the expected column.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.approval import Approval, ApprovalStatus
from app.models.backlink_prospect import BacklinkProspect, ProspectStatus
from app.models.content_draft import (
    ContentDraft,
    ContentDraftStatus,
    ContentDraftType,
)
from app.models.recommendation import (
    Recommendation,
    RecommendationStatus,
    RiskLevel,
)
from app.models.recommendation_execution import (
    ExecutionStatus,
    RecommendationExecution,
)
from app.models.user import User
from app.models.workspace import Workspace
from app.security.passwords import hash_password
from app.services.csv_export import (
    export_content_drafts,
    export_executions,
    export_prospects,
)


def _seed_workspace(db: Session) -> tuple[User, Workspace]:
    user = User(
        email=f"alice+{uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("correct-horse-9"),
        is_active=True,
    )
    db.add(user)
    db.flush()
    ws = Workspace(name="Acme", slug=f"acme-{uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    db.commit()
    return user, ws


def _parse(body: bytes) -> tuple[list[str], list[list[str]]]:
    text = body.lstrip(b"\xef\xbb\xbf").decode("utf-8")  # strip BOM
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    return rows[0], rows[1:]


def test_prospects_csv_uses_real_columns(db_session: Session) -> None:
    user, ws = _seed_workspace(db_session)
    db_session.add(
        BacklinkProspect(
            workspace_id=ws.id,
            domain="acme.test",
            page_url="https://acme.test/blog/post",
            contact_name="Pat",
            contact_email="pat@acme.test",
            contact_role="Editor",
            relevance_score=82,
            domain_authority=55,
            status=ProspectStatus.NEW,
            notes="Outreach for backlink to /pricing.",
            source="manual",
            created_by=user.id,
            last_contacted_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        )
    )
    db_session.commit()

    body = export_prospects(db_session, workspace_id=ws.id)
    headers, rows = _parse(body)

    assert "page_url" in headers
    assert "relevance_score" in headers
    assert "domain_authority" in headers
    assert "topic" not in headers  # the misnomer is gone
    assert "url" not in headers
    assert "score" not in headers

    assert len(rows) == 1
    row = dict(zip(headers, rows[0]))
    assert row["domain"] == "acme.test"
    assert row["page_url"] == "https://acme.test/blog/post"
    assert row["relevance_score"] == "82"
    assert row["domain_authority"] == "55"
    assert row["contact_email"] == "pat@acme.test"
    assert row["status"] == "new"


def test_content_drafts_csv_uses_real_columns(db_session: Session) -> None:
    user, ws = _seed_workspace(db_session)
    db_session.add(
        ContentDraft(
            workspace_id=ws.id,
            type=ContentDraftType.BLOG_POST,
            status=ContentDraftStatus.DRAFT,
            title="How to ship faster",
            body="word " * 250,  # 250 words
            target_url="https://acme.test/blog/ship-faster",
            keywords=["shipping", "release process"],
            seo_metadata={"meta_title": "Ship faster"},
            source="ai_generated",
            created_by=user.id,
        )
    )
    db_session.commit()

    body = export_content_drafts(db_session, workspace_id=ws.id)
    headers, rows = _parse(body)

    # Misnomers must be gone.
    assert "target_keyword" not in headers
    # `keywords` is a JSONB list — must be present as a joined string column.
    assert "keywords" in headers
    # `word_count` is a derived column — body word count.
    assert "word_count" in headers

    assert len(rows) == 1
    row = dict(zip(headers, rows[0]))
    assert row["title"] == "How to ship faster"
    assert row["status"] == "draft"
    assert row["type"] == "blog_post"
    assert "shipping" in row["keywords"]
    assert "release process" in row["keywords"]
    # Body had 250 "word " repetitions
    assert row["word_count"] == "250"


def test_executions_csv_uses_real_columns(db_session: Session) -> None:
    user, ws = _seed_workspace(db_session)
    run = AgentRun(
        workspace_id=ws.id,
        triggered_by_user_id=user.id,
        agent_type="paid_ads",
        status=AgentRunStatus.SUCCEEDED,
        input_payload={},
        model_used="deterministic",
    )
    db_session.add(run)
    db_session.flush()
    rec = Recommendation(
        workspace_id=ws.id,
        agent_run_id=run.id,
        title="Test rec",
        summary="—",
        recommendation_type="paid_ads.budget_unset",
        risk_level=RiskLevel.LOW,
        expected_impact="—",
        suggested_action="—",
        status=RecommendationStatus.OPEN,
    )
    db_session.add(rec)
    db_session.flush()
    approval = Approval(
        workspace_id=ws.id,
        recommendation_id=rec.id,
        action_type=rec.recommendation_type,
        risk_level=RiskLevel.LOW,
        status=ApprovalStatus.PENDING,
    )
    db_session.add(approval)
    db_session.flush()
    db_session.add(
        RecommendationExecution(
            workspace_id=ws.id,
            recommendation_id=rec.id,
            approval_id=approval.id,
            provider="google_ads",
            action_type="budget.update",
            status=ExecutionStatus.FAILED,
            error_message="provider rejected the budget update",
            executed_by=user.id,
        )
    )
    db_session.commit()

    body = export_executions(db_session, workspace_id=ws.id)
    headers, rows = _parse(body)

    assert "error_message" in headers
    assert "action_type" in headers
    assert "error_code" not in headers  # misnomer is gone

    assert len(rows) == 1
    row = dict(zip(headers, rows[0]))
    assert row["provider"] == "google_ads"
    assert row["status"] == "failed"
    assert row["action_type"] == "budget.update"
    assert "provider rejected" in row["error_message"]


def test_empty_export_returns_header_only(db_session: Session) -> None:
    _user, ws = _seed_workspace(db_session)
    body = export_prospects(db_session, workspace_id=ws.id)
    headers, rows = _parse(body)
    assert rows == []
    assert "domain" in headers
