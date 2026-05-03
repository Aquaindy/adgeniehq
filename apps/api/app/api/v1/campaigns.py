from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.db.session import get_db
from app.models.campaign import CampaignStatus
from app.models.workspace_member import WorkspaceMember
from app.schemas.campaigns import (
    CampaignDetail,
    CampaignPublic,
    CampaignSummary,
    CampaignSyncResponse,
    ProviderSyncResultPublic,
)
from app.security.dependencies import get_current_member, require_role
from app.security.permissions import Role
from app.services import campaign_service
from app.services.campaign_sync_service import sync_workspace_campaigns

router = APIRouter()


class CampaignNotFoundError(AdVantaError):
    status_code = 404
    code = "campaign_not_found"


@router.get("/{workspace_id}/campaigns", response_model=list[CampaignPublic])
def list_campaigns_endpoint(
    workspace_id: UUID,
    provider: str | None = Query(default=None),
    status_filter: CampaignStatus | None = Query(default=None, alias="status"),
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[CampaignPublic]:
    return campaign_service.list_campaigns(
        db,
        workspace_id=workspace_id,
        provider=provider,
        status=status_filter,
    )


@router.get(
    "/{workspace_id}/campaigns/summary",
    response_model=CampaignSummary,
)
def campaigns_summary(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> CampaignSummary:
    return campaign_service.summary(db, workspace_id=workspace_id)


@router.post(
    "/{workspace_id}/campaigns/sync",
    response_model=CampaignSyncResponse,
    status_code=status.HTTP_201_CREATED,
)
def sync_campaigns(
    workspace_id: UUID,
    provider: str | None = Query(default=None),
    _member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> CampaignSyncResponse:
    summary = sync_workspace_campaigns(
        db, workspace_id=workspace_id, only_provider=provider
    )
    return CampaignSyncResponse(
        started_at=summary.started_at,
        completed_at=summary.completed_at,
        providers=[
            ProviderSyncResultPublic(
                provider=r.provider,
                sync_log_id=r.sync_log_id,
                status=r.status.value,
                fetched=r.fetched,
                upserted=r.upserted,
                error=r.error,
            )
            for r in summary.providers
        ],
    )


@router.get(
    "/{workspace_id}/campaigns/{campaign_id}",
    response_model=CampaignDetail,
)
def get_campaign(
    workspace_id: UUID,
    campaign_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> CampaignDetail:
    detail = campaign_service.get_campaign(
        db, workspace_id=workspace_id, campaign_id=campaign_id
    )
    if detail is None:
        raise CampaignNotFoundError("Campaign not found in this workspace.")
    return detail
