"""Ad hierarchy routes: ad_groups, ads, creatives.

Read paths cover what the operator needs to inspect. The only writable
surface is `PATCH /creatives/{id}` so a human can polish AI-generated copy
before it ships. Provider-synced ad_groups + ads are read-only here —
mutations go through the existing recommendation/approval pipeline so they
remain audit-logged."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.db.session import get_db
from app.models.ad import Ad
from app.models.ad_group import AdGroup
from app.models.audit_log import AuditActorType
from app.models.creative import Creative
from app.models.workspace_member import WorkspaceMember
from app.schemas.ad_hierarchy import (
    AdCreateRequest,
    AdGroupCreateRequest,
    AdGroupPublic,
    AdGroupUpdateRequest,
    AdPublic,
    AdPublishResponse,
    AdUpdateRequest,
    CreativeCreateRequest,
    CreativePublic,
    CreativeUpdateRequest,
)
from app.security.dependencies import get_current_member, require_role
from app.security.permissions import Role, require_role_at_least
from app.services import ad_builder_service, ad_publish_service, audit_service

router = APIRouter()


class AdGroupNotFoundError(AdVantaError):
    status_code = 404
    code = "ad_group_not_found"


class AdNotFoundError(AdVantaError):
    status_code = 404
    code = "ad_not_found"


class CreativeNotFoundError(AdVantaError):
    status_code = 404
    code = "creative_not_found"


# ---------------------------------------------------------------------------
# Ad groups
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/ad-groups", response_model=list[AdGroupPublic]
)
def list_ad_groups(
    workspace_id: UUID,
    campaign_id: UUID | None = Query(default=None),
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[AdGroupPublic]:
    q = db.query(AdGroup).filter(AdGroup.workspace_id == workspace_id)
    if campaign_id is not None:
        q = q.filter(AdGroup.campaign_id == campaign_id)
    rows = q.order_by(AdGroup.created_at.desc()).all()
    return [AdGroupPublic.model_validate(r) for r in rows]


@router.get(
    "/{workspace_id}/ad-groups/{ad_group_id}", response_model=AdGroupPublic
)
def get_ad_group(
    workspace_id: UUID,
    ad_group_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> AdGroupPublic:
    row = (
        db.query(AdGroup)
        .filter(
            AdGroup.workspace_id == workspace_id,
            AdGroup.id == ad_group_id,
        )
        .first()
    )
    if row is None:
        raise AdGroupNotFoundError("Ad group not found in this workspace.")
    return AdGroupPublic.model_validate(row)


# ---------------------------------------------------------------------------
# Ads
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/ads", response_model=list[AdPublic])
def list_ads(
    workspace_id: UUID,
    campaign_id: UUID | None = Query(default=None),
    ad_group_id: UUID | None = Query(default=None),
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[AdPublic]:
    q = db.query(Ad).filter(Ad.workspace_id == workspace_id)
    if campaign_id is not None:
        q = q.filter(Ad.campaign_id == campaign_id)
    if ad_group_id is not None:
        q = q.filter(Ad.ad_group_id == ad_group_id)
    rows = q.order_by(Ad.created_at.desc()).all()
    return [AdPublic.model_validate(r) for r in rows]


@router.get("/{workspace_id}/ads/{ad_id}", response_model=AdPublic)
def get_ad(
    workspace_id: UUID,
    ad_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> AdPublic:
    row = (
        db.query(Ad)
        .filter(Ad.workspace_id == workspace_id, Ad.id == ad_id)
        .first()
    )
    if row is None:
        raise AdNotFoundError("Ad not found in this workspace.")
    return AdPublic.model_validate(row)


# ---------------------------------------------------------------------------
# Creatives
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/creatives", response_model=list[CreativePublic])
def list_creatives(
    workspace_id: UUID,
    type: str | None = Query(default=None),
    source: str | None = Query(default=None),
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[CreativePublic]:
    q = db.query(Creative).filter(Creative.workspace_id == workspace_id)
    if type is not None:
        q = q.filter(Creative.type == type)
    if source is not None:
        q = q.filter(Creative.source == source)
    rows = q.order_by(Creative.created_at.desc()).all()
    return [CreativePublic.model_validate(r) for r in rows]


@router.get(
    "/{workspace_id}/creatives/{creative_id}", response_model=CreativePublic
)
def get_creative(
    workspace_id: UUID,
    creative_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> CreativePublic:
    row = (
        db.query(Creative)
        .filter(
            Creative.workspace_id == workspace_id,
            Creative.id == creative_id,
        )
        .first()
    )
    if row is None:
        raise CreativeNotFoundError("Creative not found in this workspace.")
    return CreativePublic.model_validate(row)


@router.patch(
    "/{workspace_id}/creatives/{creative_id}", response_model=CreativePublic
)
def update_creative(
    workspace_id: UUID,
    creative_id: UUID,
    payload: CreativeUpdateRequest,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> CreativePublic:
    """Refine copy on a creative. Marketers and above can edit; viewers and
    analysts can read only. Audit-logged so we have a paper trail of the
    diff between the AI's first draft and what shipped."""

    require_role_at_least(member.role, Role.MARKETER)

    row = (
        db.query(Creative)
        .filter(
            Creative.workspace_id == workspace_id,
            Creative.id == creative_id,
        )
        .first()
    )
    if row is None:
        raise CreativeNotFoundError("Creative not found in this workspace.")

    diff: dict[str, dict[str, str | None]] = {}
    updates = payload.model_dump(exclude_unset=True)
    for field, new_value in updates.items():
        current = getattr(row, field)
        if current != new_value:
            diff[field] = {"from": current, "to": new_value}
            setattr(row, field, new_value)

    if not diff:
        return CreativePublic.model_validate(row)

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=member.user_id,
        action="creative.updated",
        resource_type="creative",
        resource_id=row.id,
        metadata={"changes": diff},
    )
    db.commit()
    db.refresh(row)
    return CreativePublic.model_validate(row)


# ---------------------------------------------------------------------------
# Ad-structure builder (user-built drafts) — require MARKETER+
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/campaigns/{campaign_id}/ad-groups",
    response_model=AdGroupPublic,
    status_code=status.HTTP_201_CREATED,
)
def create_ad_group_endpoint(
    workspace_id: UUID,
    campaign_id: UUID,
    payload: AdGroupCreateRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> AdGroupPublic:
    ag = ad_builder_service.create_ad_group(
        db,
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        name=payload.name,
        daily_budget_cents=payload.daily_budget_cents,
        targeting=payload.targeting.model_dump(),
        actor_user_id=member.user_id,
        request=request,
    )
    return AdGroupPublic.model_validate(ag)


@router.patch("/{workspace_id}/ad-groups/{ad_group_id}", response_model=AdGroupPublic)
def update_ad_group_endpoint(
    workspace_id: UUID,
    ad_group_id: UUID,
    payload: AdGroupUpdateRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> AdGroupPublic:
    updates = payload.model_dump(exclude_unset=True)
    if "targeting" in updates and payload.targeting is not None:
        updates["targeting"] = payload.targeting.model_dump()
    ag = ad_builder_service.update_ad_group(
        db,
        workspace_id=workspace_id,
        ad_group_id=ad_group_id,
        updates=updates,
        actor_user_id=member.user_id,
        request=request,
    )
    return AdGroupPublic.model_validate(ag)


def _publish_response(result: ad_publish_service.PublishResult) -> AdPublishResponse:
    return AdPublishResponse(
        status=result.status,
        object_type=result.object_type,
        risk_level=result.risk_level.value,
        required_role=result.required_role.value,
        message=result.message,
        recommendation_id=result.recommendation.id,
        approval_id=result.approval.id if result.approval else None,
        approval_status=result.approval.status.value if result.approval else None,
        execution_id=result.execution.id if result.execution else None,
        execution_status=result.execution.status.value if result.execution else None,
        external_id=result.external_id,
        error_message=result.execution.error_message if result.execution else None,
    )


@router.post(
    "/{workspace_id}/ad-groups/{ad_group_id}/publish",
    response_model=AdPublishResponse,
)
def publish_ad_group_endpoint(
    workspace_id: UUID,
    ad_group_id: UUID,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> AdPublishResponse:
    result = ad_publish_service.publish_ad_group(
        db,
        workspace_id=workspace_id,
        ad_group_id=ad_group_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        request=request,
    )
    return _publish_response(result)


@router.post(
    "/{workspace_id}/ads/{ad_id}/publish",
    response_model=AdPublishResponse,
)
def publish_ad_endpoint(
    workspace_id: UUID,
    ad_id: UUID,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> AdPublishResponse:
    result = ad_publish_service.publish_ad(
        db,
        workspace_id=workspace_id,
        ad_id=ad_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        request=request,
    )
    return _publish_response(result)


@router.delete(
    "/{workspace_id}/ad-groups/{ad_group_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_ad_group_endpoint(
    workspace_id: UUID,
    ad_group_id: UUID,
    _member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> None:
    ad_builder_service.delete_ad_group(
        db, workspace_id=workspace_id, ad_group_id=ad_group_id
    )


@router.post(
    "/{workspace_id}/ad-groups/{ad_group_id}/ads",
    response_model=AdPublic,
    status_code=status.HTTP_201_CREATED,
)
def create_ad_endpoint(
    workspace_id: UUID,
    ad_group_id: UUID,
    payload: AdCreateRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> AdPublic:
    ad = ad_builder_service.create_ad(
        db,
        workspace_id=workspace_id,
        ad_group_id=ad_group_id,
        name=payload.name,
        landing_page_url=payload.landing_page_url,
        creative_id=payload.creative_id,
        actor_user_id=member.user_id,
        request=request,
    )
    return AdPublic.model_validate(ad)


@router.patch("/{workspace_id}/ads/{ad_id}", response_model=AdPublic)
def update_ad_endpoint(
    workspace_id: UUID,
    ad_id: UUID,
    payload: AdUpdateRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> AdPublic:
    ad = ad_builder_service.update_ad(
        db,
        workspace_id=workspace_id,
        ad_id=ad_id,
        updates=payload.model_dump(exclude_unset=True),
        actor_user_id=member.user_id,
        request=request,
    )
    return AdPublic.model_validate(ad)


@router.delete("/{workspace_id}/ads/{ad_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ad_endpoint(
    workspace_id: UUID,
    ad_id: UUID,
    _member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> None:
    ad_builder_service.delete_ad(db, workspace_id=workspace_id, ad_id=ad_id)


@router.post(
    "/{workspace_id}/creatives",
    response_model=CreativePublic,
    status_code=status.HTTP_201_CREATED,
)
def create_creative_endpoint(
    workspace_id: UUID,
    payload: CreativeCreateRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> CreativePublic:
    creative = ad_builder_service.create_creative(
        db,
        workspace_id=workspace_id,
        type=payload.type,
        title=payload.title,
        headline=payload.headline,
        primary_text=payload.primary_text,
        description=payload.description,
        cta=payload.cta,
        image_url=payload.image_url,
        video_url=payload.video_url,
        actor_user_id=member.user_id,
        request=request,
    )
    return CreativePublic.model_validate(creative)
