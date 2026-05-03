from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.agent_run import AgentRun
from app.models.billing_subscription import BillingSubscription, SubscriptionStatus
from app.models.connected_account import ConnectedAccount, ConnectionStatus
from app.models.landing_page import LandingPage
from app.models.recommendation import Recommendation, RecommendationStatus
from app.models.report import Report
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.schemas.admin import AdminOverview, AdminUserRow, AdminWorkspaceRow
from app.security.dependencies import require_superuser

router = APIRouter()


@router.get("/overview", response_model=AdminOverview)
def overview(
    _: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> AdminOverview:
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

    users_total = db.query(func.count(User.id)).scalar() or 0
    superusers_total = (
        db.query(func.count(User.id)).filter(User.is_superuser.is_(True)).scalar() or 0
    )
    workspaces_total = db.query(func.count(Workspace.id)).scalar() or 0
    paid_workspaces_total = (
        db.query(func.count(BillingSubscription.id))
        .filter(
            BillingSubscription.status.in_(
                [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]
            )
        )
        .scalar()
        or 0
    )

    agent_runs_total = db.query(func.count(AgentRun.id)).scalar() or 0
    agent_runs_last_7d = (
        db.query(func.count(AgentRun.id))
        .filter(AgentRun.created_at >= seven_days_ago)
        .scalar()
        or 0
    )

    recommendations_open = (
        db.query(func.count(Recommendation.id))
        .filter(Recommendation.status == RecommendationStatus.OPEN)
        .scalar()
        or 0
    )
    integrations_connected = (
        db.query(func.count(ConnectedAccount.id))
        .filter(ConnectedAccount.status == ConnectionStatus.CONNECTED)
        .scalar()
        or 0
    )
    landing_pages_total = db.query(func.count(LandingPage.id)).scalar() or 0
    reports_generated_last_7d = (
        db.query(func.count(Report.id))
        .filter(Report.created_at >= seven_days_ago)
        .scalar()
        or 0
    )

    # Post-M12 resource counts
    from app.models.ab_test import AbTest, AbTestStatus
    from app.models.backlink_prospect import BacklinkProspect
    from app.models.content_draft import ContentDraft, ContentDraftStatus
    from app.models.outreach_email import OutreachEmail, OutreachEmailStatus
    from app.models.recommendation_execution import (
        ExecutionStatus,
        RecommendationExecution,
    )

    executions_total = db.query(func.count(RecommendationExecution.id)).scalar() or 0
    executions_succeeded_last_7d = (
        db.query(func.count(RecommendationExecution.id))
        .filter(
            RecommendationExecution.status == ExecutionStatus.SUCCEEDED,
            RecommendationExecution.created_at >= seven_days_ago,
        )
        .scalar()
        or 0
    )
    content_drafts_total = db.query(func.count(ContentDraft.id)).scalar() or 0
    content_drafts_published_last_7d = (
        db.query(func.count(ContentDraft.id))
        .filter(
            ContentDraft.status == ContentDraftStatus.PUBLISHED,
            ContentDraft.published_at >= seven_days_ago,
        )
        .scalar()
        or 0
    )
    outreach_emails_sent_last_7d = (
        db.query(func.count(OutreachEmail.id))
        .filter(
            OutreachEmail.status == OutreachEmailStatus.SENT,
            OutreachEmail.sent_at >= seven_days_ago,
        )
        .scalar()
        or 0
    )
    outreach_prospects_total = db.query(func.count(BacklinkProspect.id)).scalar() or 0
    ab_tests_active = (
        db.query(func.count(AbTest.id))
        .filter(AbTest.status == AbTestStatus.LAUNCHED)
        .scalar()
        or 0
    )
    ab_tests_completed_last_7d = (
        db.query(func.count(AbTest.id))
        .filter(
            AbTest.status == AbTestStatus.COMPLETED,
            AbTest.ended_at >= seven_days_ago,
        )
        .scalar()
        or 0
    )

    return AdminOverview(
        users_total=users_total,
        superusers_total=superusers_total,
        workspaces_total=workspaces_total,
        paid_workspaces_total=paid_workspaces_total,
        agent_runs_total=agent_runs_total,
        agent_runs_last_7d=agent_runs_last_7d,
        recommendations_open=recommendations_open,
        integrations_connected=integrations_connected,
        landing_pages_total=landing_pages_total,
        reports_generated_last_7d=reports_generated_last_7d,
        executions_total=executions_total,
        executions_succeeded_last_7d=executions_succeeded_last_7d,
        content_drafts_total=content_drafts_total,
        content_drafts_published_last_7d=content_drafts_published_last_7d,
        outreach_emails_sent_last_7d=outreach_emails_sent_last_7d,
        outreach_prospects_total=outreach_prospects_total,
        ab_tests_active=ab_tests_active,
        ab_tests_completed_last_7d=ab_tests_completed_last_7d,
    )


@router.get("/workspaces", response_model=list[AdminWorkspaceRow])
def list_workspaces(
    limit: int = Query(default=200, le=1000),
    _: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> list[AdminWorkspaceRow]:
    rows = (
        db.query(
            Workspace,
            func.count(WorkspaceMember.id).label("member_count"),
        )
        .outerjoin(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .group_by(Workspace.id)
        .order_by(Workspace.created_at.desc())
        .limit(limit)
        .all()
    )

    sub_map: dict = {}
    subs = db.query(BillingSubscription).all()
    for s in subs:
        sub_map[s.workspace_id] = (s.plan_code or "free", s.status.value)

    out: list[AdminWorkspaceRow] = []
    for workspace, member_count in rows:
        plan_code, status_value = sub_map.get(workspace.id, ("free", "none"))
        out.append(
            AdminWorkspaceRow(
                id=workspace.id,
                name=workspace.name,
                slug=workspace.slug,
                created_at=workspace.created_at,
                member_count=member_count or 0,
                plan_code=plan_code,
                subscription_status=status_value,
            )
        )
    return out


@router.get("/users", response_model=list[AdminUserRow])
def list_users(
    limit: int = Query(default=200, le=1000),
    _: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> list[AdminUserRow]:
    rows = (
        db.query(User, func.count(WorkspaceMember.id).label("workspace_count"))
        .outerjoin(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .group_by(User.id)
        .order_by(User.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        AdminUserRow(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
            workspace_count=workspace_count or 0,
            created_at=user.created_at,
        )
        for user, workspace_count in rows
    ]
