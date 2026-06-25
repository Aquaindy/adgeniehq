from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.db.session import get_db
from app.models.campaign import CampaignStatus
from app.models.workspace_member import WorkspaceMember
from app.schemas.campaigns import (
    CampaignActionResponse,
    CampaignBudgetRequest,
    CampaignDetail,
    CampaignLaunchRequest,
    CampaignLaunchResponse,
    CampaignPublic,
    CampaignSummary,
    CampaignSyncResponse,
    ProviderSyncResultPublic,
)
from app.security.dependencies import get_current_member, require_role
from app.security.permissions import Role
from app.services import (
    campaign_action_service,
    campaign_launch_service,
    campaign_service,
)
from app.services.campaign_sync_service import sync_workspace_campaigns

router = APIRouter()


def _action_response(result: campaign_action_service.CampaignActionResult) -> CampaignActionResponse:
    return CampaignActionResponse(
        status=result.status,
        action=result.action,
        risk_level=result.risk_level.value,
        required_role=result.required_role.value,
        message=result.message,
        recommendation_id=result.recommendation.id,
        approval_id=result.approval.id if result.approval else None,
        approval_status=result.approval.status.value if result.approval else None,
        execution_id=result.execution.id if result.execution else None,
        execution_status=result.execution.status.value if result.execution else None,
        error_message=result.execution.error_message if result.execution else None,
        campaign=CampaignPublic.model_validate(result.campaign),
    )


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


@router.post(
    "/{workspace_id}/campaigns/launch",
    response_model=CampaignLaunchResponse,
    status_code=status.HTTP_201_CREATED,
)
def launch_campaign_endpoint(
    workspace_id: UUID,
    payload: CampaignLaunchRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> CampaignLaunchResponse:
    result = campaign_launch_service.launch_campaign(
        db,
        workspace_id=workspace_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        provider=payload.provider,
        name=payload.name,
        campaign_type=payload.campaign_type,
        daily_budget_cents=payload.daily_budget_cents,
        request=request,
    )
    return CampaignLaunchResponse(
        status=result.status,
        risk_level=result.risk_level.value,
        required_role=result.required_role.value,
        message=result.message,
        recommendation_id=result.recommendation.id,
        approval_id=result.approval.id if result.approval else None,
        approval_status=result.approval.status.value if result.approval else None,
        execution_id=result.execution.id if result.execution else None,
        execution_status=result.execution.status.value if result.execution else None,
        error_message=result.execution.error_message if result.execution else None,
        campaign=CampaignPublic.model_validate(result.campaign) if result.campaign else None,
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


# ---------------------------------------------------------------------------
# Campaign management actions — gated by the approval + execution engine.
# Requires MARKETER to initiate; the action self-gates per risk level
# (one-click if the actor's role can approve it, otherwise queued).
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/campaigns/{campaign_id}/pause",
    response_model=CampaignActionResponse,
)
def pause_campaign_endpoint(
    workspace_id: UUID,
    campaign_id: UUID,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> CampaignActionResponse:
    result = campaign_action_service.create_campaign_action(
        db,
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        action=campaign_action_service.ACTION_PAUSE,
        actor_user_id=member.user_id,
        actor_role=member.role,
        request=request,
    )
    return _action_response(result)


@router.post(
    "/{workspace_id}/campaigns/{campaign_id}/resume",
    response_model=CampaignActionResponse,
)
def resume_campaign_endpoint(
    workspace_id: UUID,
    campaign_id: UUID,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> CampaignActionResponse:
    result = campaign_action_service.create_campaign_action(
        db,
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        action=campaign_action_service.ACTION_RESUME,
        actor_user_id=member.user_id,
        actor_role=member.role,
        request=request,
    )
    return _action_response(result)


@router.post(
    "/{workspace_id}/campaigns/{campaign_id}/budget",
    response_model=CampaignActionResponse,
)
def update_campaign_budget_endpoint(
    workspace_id: UUID,
    campaign_id: UUID,
    payload: CampaignBudgetRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> CampaignActionResponse:
    result = campaign_action_service.create_campaign_action(
        db,
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        action=campaign_action_service.ACTION_UPDATE_BUDGET,
        actor_user_id=member.user_id,
        actor_role=member.role,
        new_daily_budget_cents=payload.daily_budget_cents,
        request=request,
    )
    return _action_response(result)
