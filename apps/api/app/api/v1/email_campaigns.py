"""Email-campaign endpoints.

List the workspace's email campaigns (synced from Omnisend with engagement +
deliverability metrics), trigger a sync, and link a campaign to a paid-ads
campaign. The email-marketing audit itself runs through the agent system
(`POST /agents/run` with agent_type=email_marketing)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.workspace_member import WorkspaceMember
from app.schemas.email_campaigns import (
    AssociateAdCampaignRequest,
    EmailCampaignPublic,
)
from app.security.dependencies import get_current_member, require_role
from app.security.permissions import Role
from app.services import email_campaign_service

router = APIRouter()


@router.get(
    "/{workspace_id}/email-campaigns",
    response_model=list[EmailCampaignPublic],
)
def list_email_campaigns(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[EmailCampaignPublic]:
    rows = email_campaign_service.list_email_campaigns(db, workspace_id=workspace_id)
    return [EmailCampaignPublic.model_validate(r) for r in rows]


@router.post(
    "/{workspace_id}/email-campaigns/sync",
    response_model=list[EmailCampaignPublic],
)
def sync_email_campaigns(
    workspace_id: UUID,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> list[EmailCampaignPublic]:
    rows = email_campaign_service.sync_email_campaigns(
        db,
        workspace_id=workspace_id,
        user_id=member.user_id,
        request=request,
    )
    return [EmailCampaignPublic.model_validate(r) for r in rows]


@router.post(
    "/{workspace_id}/email-campaigns/{email_campaign_id}/associate",
    response_model=EmailCampaignPublic,
)
def associate_email_campaign(
    workspace_id: UUID,
    email_campaign_id: UUID,
    payload: AssociateAdCampaignRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> EmailCampaignPublic:
    ec = email_campaign_service.associate_with_ad_campaign(
        db,
        workspace_id=workspace_id,
        user_id=member.user_id,
        email_campaign_id=email_campaign_id,
        ad_campaign_id=payload.ad_campaign_id,
        request=request,
    )
    return EmailCampaignPublic.model_validate(ec)
