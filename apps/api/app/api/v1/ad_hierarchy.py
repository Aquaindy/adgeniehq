"""Ad hierarchy routes: ad_groups, ads, creatives.

Read paths cover what the operator needs to inspect. The only writable
surface is `PATCH /creatives/{id}` so a human can polish AI-generated copy
before it ships. Provider-synced ad_groups + ads are read-only here —
mutations go through the existing recommendation/approval pipeline so they
remain audit-logged."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.db.session import get_db
from app.models.ad import Ad
from app.models.ad_group import AdGroup
from app.models.audit_log import AuditActorType
from app.models.creative import Creative
from app.models.workspace_member import WorkspaceMember
from app.schemas.ad_hierarchy import (
    AdGroupPublic,
    AdPublic,
    CreativePublic,
    CreativeUpdateRequest,
)
from app.security.dependencies import get_current_member
from app.security.permissions import Role, require_role_at_least
from app.services import audit_service

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
