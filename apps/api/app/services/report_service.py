"""Report aggregation service.

Rolls real workspace data — agent runs, recommendations, campaigns, SEO/GEO,
landing-page audits, Growth DNA — into a structured payload. Nothing is
fabricated: empty inputs produce empty sections, and the renderer / dashboard
surface that honestly."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.campaign import Campaign, CampaignStatus
from app.models.growth_dna_profile import GrowthDnaProfile
from app.models.keyword import Keyword
from app.models.landing_page import LandingPage
from app.models.recommendation import (
    Recommendation,
    RecommendationStatus,
    RiskLevel,
)
from app.models.report import Report, ReportPeriod, ReportStatus
from app.models.seo_project import SeoProject
from app.models.workspace import Workspace

log = get_logger(__name__)


PERIOD_LABELS = {
    ReportPeriod.DAILY: "Daily",
    ReportPeriod.WEEKLY: "Weekly",
    ReportPeriod.MONTHLY: "Monthly",
}


# ---------------------------------------------------------------------------
# Period windows
# ---------------------------------------------------------------------------


def period_window(
    period: ReportPeriod, *, anchor: datetime | None = None
) -> tuple[datetime, datetime]:
    end = anchor or datetime.now(timezone.utc)
    if period == ReportPeriod.DAILY:
        start = end - timedelta(days=1)
    elif period == ReportPeriod.WEEKLY:
        start = end - timedelta(days=7)
    elif period == ReportPeriod.MONTHLY:
        start = end - timedelta(days=30)
    else:  # pragma: no cover — exhaustive match
        raise ValueError(f"Unknown report period: {period}")
    return start, end


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


def generate_report(
    db: Session,
    *,
    workspace_id: UUID,
    period: ReportPeriod,
    actor_user_id: UUID | None,
) -> Report:
    start, end = period_window(period)
    workspace = db.get(Workspace, workspace_id)
    title = _build_title(period=period, end=end, workspace_name=workspace.name if workspace else "")

    report = Report(
        workspace_id=workspace_id,
        generated_by_user_id=actor_user_id,
        period=period,
        period_start=start,
        period_end=end,
        status=ReportStatus.GENERATING,
        title=title,
        payload={},
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    try:
        payload = build_payload(
            db,
            workspace=workspace,
            workspace_id=workspace_id,
            period=period,
            start=start,
            end=end,
        )
    except Exception as exc:  # pragma: no cover — defensive
        log.exception("report.generate.failed", workspace=str(workspace_id), period=period.value)
        report.status = ReportStatus.FAILED
        report.error_message = str(exc)
        db.commit()
        db.refresh(report)
        return report

    report.payload = payload
    report.status = ReportStatus.READY
    db.commit()
    db.refresh(report)
    return report


def _build_title(*, period: ReportPeriod, end: datetime, workspace_name: str) -> str:
    label = PERIOD_LABELS.get(period, period.value.title())
    end_label = end.date().isoformat()
    name = f" — {workspace_name}" if workspace_name else ""
    return f"{label} report{name} · {end_label}"


# ---------------------------------------------------------------------------
# Payload sections
# ---------------------------------------------------------------------------


def build_payload(
    db: Session,
    *,
    workspace: Workspace | None,
    workspace_id: UUID,
    period: ReportPeriod,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    return {
        "workspace": _workspace_block(workspace),
        "period": {
            "type": period.value,
            "label": PERIOD_LABELS.get(period, period.value.title()),
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        "summary": _summary_block(db, workspace_id, start, end),
        "agent_runs": _agent_runs_block(db, workspace_id, start, end),
        "top_recommendations": _top_recommendations(db, workspace_id, start, end),
        "campaigns": _campaigns_block(db, workspace_id),
        "seo": _seo_block(db, workspace_id),
        "landing_pages": _landing_pages_block(db, workspace_id),
        "growth_dna": _growth_dna_block(db, workspace_id),
        "executions": _executions_block(db, workspace_id, start, end),
        "content_drafts": _content_drafts_block(db, workspace_id, start, end),
        "outreach": _outreach_block(db, workspace_id, start, end),
        "ab_tests": _ab_tests_block(db, workspace_id, start, end),
    }


def _executions_block(
    db: Session, workspace_id: UUID, start: datetime, end: datetime
) -> dict[str, Any]:
    """Phase A — outbound provider writes during the period."""

    from app.models.recommendation_execution import (
        ExecutionStatus,
        RecommendationExecution,
    )

    base_q = db.query(RecommendationExecution).filter(
        RecommendationExecution.workspace_id == workspace_id,
        RecommendationExecution.created_at >= start,
        RecommendationExecution.created_at <= end,
    )
    total = base_q.count()
    by_status: dict[str, int] = {}
    for status in ExecutionStatus:
        by_status[status.value] = (
            base_q.filter(RecommendationExecution.status == status).count()
        )
    by_provider_rows = (
        db.query(
            RecommendationExecution.provider,
            func.count(RecommendationExecution.id),
        )
        .filter(
            RecommendationExecution.workspace_id == workspace_id,
            RecommendationExecution.created_at >= start,
            RecommendationExecution.created_at <= end,
        )
        .group_by(RecommendationExecution.provider)
        .all()
    )
    return {
        "total": total,
        "by_status": by_status,
        "by_provider": {p: c for p, c in by_provider_rows if p},
    }


def _content_drafts_block(
    db: Session, workspace_id: UUID, start: datetime, end: datetime
) -> dict[str, Any]:
    from app.models.content_draft import ContentDraft, ContentDraftStatus

    base_q = db.query(ContentDraft).filter(
        ContentDraft.workspace_id == workspace_id,
        ContentDraft.created_at >= start,
        ContentDraft.created_at <= end,
    )
    total = base_q.count()
    by_status = {
        s.value: base_q.filter(ContentDraft.status == s).count()
        for s in ContentDraftStatus
    }
    by_type_rows = (
        db.query(ContentDraft.type, func.count(ContentDraft.id))
        .filter(
            ContentDraft.workspace_id == workspace_id,
            ContentDraft.created_at >= start,
            ContentDraft.created_at <= end,
        )
        .group_by(ContentDraft.type)
        .all()
    )
    return {
        "total": total,
        "by_status": by_status,
        "by_type": {t.value: c for t, c in by_type_rows},
    }


def _outreach_block(
    db: Session, workspace_id: UUID, start: datetime, end: datetime
) -> dict[str, Any]:
    from app.models.backlink_prospect import BacklinkProspect, ProspectStatus
    from app.models.outreach_email import OutreachEmail, OutreachEmailStatus

    emails_q = db.query(OutreachEmail).filter(
        OutreachEmail.workspace_id == workspace_id,
        OutreachEmail.created_at >= start,
        OutreachEmail.created_at <= end,
    )
    sent = emails_q.filter(OutreachEmail.status == OutreachEmailStatus.SENT).count()
    replied = emails_q.filter(
        OutreachEmail.status == OutreachEmailStatus.REPLIED
    ).count()
    bounced = emails_q.filter(
        OutreachEmail.status == OutreachEmailStatus.BOUNCED
    ).count()
    total = emails_q.count()

    prospects_q = db.query(BacklinkProspect).filter(
        BacklinkProspect.workspace_id == workspace_id,
    )
    prospects_total = prospects_q.count()
    won = prospects_q.filter(BacklinkProspect.status == ProspectStatus.WON).count()

    return {
        "emails_total": total,
        "emails_sent": sent,
        "emails_replied": replied,
        "emails_bounced": bounced,
        "reply_rate": (replied / sent) if sent > 0 else 0.0,
        "prospects_total": prospects_total,
        "prospects_won": won,
    }


def _ab_tests_block(
    db: Session, workspace_id: UUID, start: datetime, end: datetime
) -> dict[str, Any]:
    from app.models.ab_test import AbTest, AbTestStatus

    base_q = db.query(AbTest).filter(
        AbTest.workspace_id == workspace_id,
        AbTest.created_at >= start,
        AbTest.created_at <= end,
    )
    total = base_q.count()
    by_status = {
        s.value: base_q.filter(AbTest.status == s).count() for s in AbTestStatus
    }
    completed_with_winner = base_q.filter(
        AbTest.status == AbTestStatus.COMPLETED,
        AbTest.winner_variant_id.is_not(None),
    ).count()
    return {
        "total": total,
        "by_status": by_status,
        "completed_with_winner": completed_with_winner,
    }


def _workspace_block(workspace: Workspace | None) -> dict[str, Any]:
    if workspace is None:
        return {}
    return {
        "id": str(workspace.id),
        "name": workspace.name,
        "slug": workspace.slug,
    }


def _summary_block(
    db: Session, workspace_id: UUID, start: datetime, end: datetime
) -> dict[str, Any]:
    agent_runs_total = (
        db.query(func.count(AgentRun.id))
        .filter(
            AgentRun.workspace_id == workspace_id,
            AgentRun.created_at >= start,
            AgentRun.created_at <= end,
        )
        .scalar()
        or 0
    )

    rec_status_counts: dict[str, int] = {s.value: 0 for s in RecommendationStatus}
    rows = (
        db.query(Recommendation.status, func.count(Recommendation.id))
        .filter(
            Recommendation.workspace_id == workspace_id,
            Recommendation.created_at >= start,
            Recommendation.created_at <= end,
        )
        .group_by(Recommendation.status)
        .all()
    )
    for status_value, count in rows:
        rec_status_counts[status_value.value] = count

    rec_risk_counts: dict[str, int] = {r.value: 0 for r in RiskLevel}
    risk_rows = (
        db.query(Recommendation.risk_level, func.count(Recommendation.id))
        .filter(
            Recommendation.workspace_id == workspace_id,
            Recommendation.created_at >= start,
            Recommendation.created_at <= end,
        )
        .group_by(Recommendation.risk_level)
        .all()
    )
    for risk, count in risk_rows:
        rec_risk_counts[risk.value] = count

    campaigns_total = (
        db.query(func.count(Campaign.id))
        .filter(Campaign.workspace_id == workspace_id)
        .scalar()
        or 0
    )
    campaigns_active = (
        db.query(func.count(Campaign.id))
        .filter(
            Campaign.workspace_id == workspace_id,
            Campaign.status == CampaignStatus.ACTIVE,
        )
        .scalar()
        or 0
    )

    keywords_tracked = (
        db.query(func.count(Keyword.id))
        .join(SeoProject, SeoProject.id == Keyword.seo_project_id)
        .filter(SeoProject.workspace_id == workspace_id)
        .scalar()
        or 0
    )
    landing_pages_total = (
        db.query(func.count(LandingPage.id))
        .filter(LandingPage.workspace_id == workspace_id)
        .scalar()
        or 0
    )
    landing_pages_audited = (
        db.query(func.count(LandingPage.id))
        .filter(
            LandingPage.workspace_id == workspace_id,
            LandingPage.last_audited_at.isnot(None),
        )
        .scalar()
        or 0
    )

    return {
        "agent_runs_total": agent_runs_total,
        "recommendations_by_status": rec_status_counts,
        "recommendations_by_risk": rec_risk_counts,
        "campaigns_total": campaigns_total,
        "campaigns_active": campaigns_active,
        "keywords_tracked": keywords_tracked,
        "landing_pages_total": landing_pages_total,
        "landing_pages_audited": landing_pages_audited,
    }


def _agent_runs_block(
    db: Session, workspace_id: UUID, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    runs = (
        db.query(AgentRun)
        .filter(
            AgentRun.workspace_id == workspace_id,
            AgentRun.created_at >= start,
            AgentRun.created_at <= end,
        )
        .order_by(AgentRun.created_at.desc())
        .limit(25)
        .all()
    )

    rec_counts: dict[UUID, int] = dict(
        db.query(Recommendation.agent_run_id, func.count(Recommendation.id))
        .filter(Recommendation.workspace_id == workspace_id)
        .group_by(Recommendation.agent_run_id)
        .all()
    )

    return [
        {
            "id": str(run.id),
            "agent_type": run.agent_type,
            "status": run.status.value,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "recommendation_count": rec_counts.get(run.id, 0),
        }
        for run in runs
    ]


_RISK_PRIORITY = {RiskLevel.HIGH: 0, RiskLevel.MEDIUM: 1, RiskLevel.LOW: 2}


def _top_recommendations(
    db: Session, workspace_id: UUID, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    rows = (
        db.query(Recommendation)
        .filter(
            Recommendation.workspace_id == workspace_id,
            Recommendation.created_at >= start,
            Recommendation.created_at <= end,
            Recommendation.status == RecommendationStatus.OPEN,
        )
        .all()
    )
    rows.sort(
        key=lambda r: (_RISK_PRIORITY.get(r.risk_level, 99), r.created_at),
    )
    top = rows[:10]
    return [
        {
            "id": str(r.id),
            "title": r.title,
            "summary": r.summary,
            "risk_level": r.risk_level.value,
            "recommendation_type": r.recommendation_type,
            "platform": r.platform,
            "expected_impact": r.expected_impact,
            "suggested_action": r.suggested_action,
            "agent_run_id": str(r.agent_run_id),
            "created_at": r.created_at.isoformat(),
        }
        for r in top
    ]


def _campaigns_block(db: Session, workspace_id: UUID) -> dict[str, Any]:
    rows = (
        db.query(Campaign)
        .filter(Campaign.workspace_id == workspace_id)
        .all()
    )
    if not rows:
        return {"total": 0, "per_provider": {}, "active_without_budget": 0, "stale_active": 0}

    from datetime import date

    today = date.today()
    per_provider: dict[str, int] = {}
    active_without_budget = 0
    stale_active = 0
    for c in rows:
        per_provider[c.provider] = per_provider.get(c.provider, 0) + 1
        if c.status == CampaignStatus.ACTIVE:
            if not c.daily_budget_cents and not c.lifetime_budget_cents:
                active_without_budget += 1
            if c.end_date is not None and c.end_date < today:
                stale_active += 1

    return {
        "total": len(rows),
        "per_provider": per_provider,
        "active_without_budget": active_without_budget,
        "stale_active": stale_active,
    }


def _seo_block(db: Session, workspace_id: UUID) -> dict[str, Any]:
    project = (
        db.query(SeoProject)
        .filter(SeoProject.workspace_id == workspace_id)
        .first()
    )
    if project is None:
        return {"present": False}

    top_keywords = (
        db.query(Keyword)
        .filter(Keyword.seo_project_id == project.id)
        .order_by(Keyword.opportunity_score.desc(), Keyword.impressions.desc())
        .limit(10)
        .all()
    )

    return {
        "present": True,
        "site_url": project.site_url,
        "search_console_site_url": project.search_console_site_url,
        "last_crawled_at": project.last_crawled_at.isoformat() if project.last_crawled_at else None,
        "last_search_console_synced_at": project.last_search_console_synced_at.isoformat()
        if project.last_search_console_synced_at
        else None,
        "crawl_summary": project.crawl_summary,
        "top_keywords": [
            {
                "query": kw.query,
                "impressions": kw.impressions,
                "clicks": kw.clicks,
                "ctr": kw.ctr,
                "position": kw.position,
                "opportunity_score": kw.opportunity_score,
                "top_page": kw.top_page,
            }
            for kw in top_keywords
        ],
    }


def _landing_pages_block(db: Session, workspace_id: UUID) -> list[dict[str, Any]]:
    rows = (
        db.query(LandingPage)
        .filter(LandingPage.workspace_id == workspace_id)
        .order_by(LandingPage.is_primary.desc(), LandingPage.last_audited_at.desc().nullslast())
        .limit(10)
        .all()
    )
    out: list[dict[str, Any]] = []
    for lp in rows:
        scores = None
        if lp.last_audit_summary and isinstance(lp.last_audit_summary, dict):
            scores = lp.last_audit_summary.get("scores")
        out.append(
            {
                "id": str(lp.id),
                "url": lp.url,
                "label": lp.label,
                "is_primary": lp.is_primary,
                "last_audited_at": lp.last_audited_at.isoformat()
                if lp.last_audited_at
                else None,
                "scores": scores,
            }
        )
    return out


def _growth_dna_block(db: Session, workspace_id: UUID) -> dict[str, Any] | None:
    dna = (
        db.query(GrowthDnaProfile)
        .filter(GrowthDnaProfile.workspace_id == workspace_id)
        .order_by(GrowthDnaProfile.created_at.desc())
        .first()
    )
    if dna is None:
        return None
    return {
        "engine_version": dna.engine_version,
        "funnel_readiness_score": dna.funnel_readiness_score,
        "paid_ads_readiness_score": dna.paid_ads_readiness_score,
        "generated_at": dna.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def list_reports(
    db: Session, *, workspace_id: UUID, limit: int = 50
) -> list[Report]:
    return (
        db.query(Report)
        .filter(Report.workspace_id == workspace_id)
        .order_by(Report.created_at.desc())
        .limit(limit)
        .all()
    )


def get_report(db: Session, *, workspace_id: UUID, report_id: UUID) -> Report | None:
    return (
        db.query(Report)
        .filter(Report.id == report_id, Report.workspace_id == workspace_id)
        .first()
    )
