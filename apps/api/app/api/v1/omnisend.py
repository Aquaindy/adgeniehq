"""Omnisend journey-connection endpoints (Phase 5).

The AI Omnisend Journey Builder, traffic-campaign → segment/tag/flow mapping,
and real lead-source contact tagging. Workspace-scoped; reads need membership,
writes need Marketer+.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.workspace_member import WorkspaceMember
from app.schemas.omnisend_journeys import (
    CampaignMappingRequest,
    GenerateJourneyRequest,
    JourneyTypePublic,
    SyncLeadSourceRequest,
)
from app.security.dependencies import get_current_member, require_role
from app.security.permissions import Role
from app.services import omnisend_journey_service

router = APIRouter()


@router.get("/{workspace_id}/omnisend/journey-types", response_model=list[JourneyTypePublic])
def list_journey_types(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
) -> list[JourneyTypePublic]:
    return [JourneyTypePublic(**j) for j in omnisend_journey_service.list_journey_types()]


@router.post("/{workspace_id}/omnisend/journeys/generate", response_model=dict)
def generate_journey(
    workspace_id: UUID,
    payload: GenerateJourneyRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> dict:
    return omnisend_journey_service.generate_journey(
        db, workspace_id=workspace_id, actor_user_id=member.user_id,
        context=payload.model_dump(exclude_none=True), request=request,
    )


@router.post("/{workspace_id}/omnisend/campaign-mapping", response_model=dict)
def map_campaign(
    workspace_id: UUID,
    payload: CampaignMappingRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> dict:
    return omnisend_journey_service.map_campaign(
        db, workspace_id=workspace_id, actor_user_id=member.user_id,
        traffic_campaign_id=payload.traffic_campaign_id,
        vendor_name=payload.vendor_name, journey_type=payload.journey_type,
        request=request,
    )


@router.post("/{workspace_id}/omnisend/sync-lead-source", response_model=dict)
def sync_lead_source(
    workspace_id: UUID,
    payload: SyncLeadSourceRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> dict:
    return omnisend_journey_service.sync_lead_source(
        db, workspace_id=workspace_id, actor_user_id=member.user_id,
        tag=payload.tag, source=payload.source,
        contacts=[c.model_dump(exclude_none=True) for c in payload.contacts],
        request=request,
    )
