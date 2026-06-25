from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.workspace_member import WorkspaceMember
from app.schemas.analytics import (
    CampaignSeriesResponse,
    MetricsSyncResponse,
    WorkspaceAnalyticsResponse,
)
from app.security.dependencies import get_current_member, require_role
from app.security.permissions import Role
from app.services import metrics_service

router = APIRouter()


@router.get(
    "/{workspace_id}/analytics/summary", response_model=WorkspaceAnalyticsResponse
)
def analytics_summary(
    workspace_id: UUID,
    days: int = Query(default=30, ge=1, le=365),
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> WorkspaceAnalyticsResponse:
    return WorkspaceAnalyticsResponse(
        **metrics_service.workspace_summary(db, workspace_id=workspace_id, days=days)
    )


@router.get(
    "/{workspace_id}/campaigns/{campaign_id}/metrics",
    response_model=CampaignSeriesResponse,
)
def campaign_metrics(
    workspace_id: UUID,
    campaign_id: UUID,
    days: int = Query(default=30, ge=1, le=365),
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> CampaignSeriesResponse:
    return CampaignSeriesResponse(
        **metrics_service.campaign_series(
            db, workspace_id=workspace_id, campaign_id=campaign_id, days=days
        )
    )


@router.post(
    "/{workspace_id}/analytics/sync", response_model=MetricsSyncResponse
)
def sync_analytics(
    workspace_id: UUID,
    days: int = Query(default=30, ge=1, le=365),
    _member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> MetricsSyncResponse:
    return MetricsSyncResponse(
        **metrics_service.sync_workspace_metrics(db, workspace_id=workspace_id, days=days)
    )
