from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.db.session import get_db
from app.models.workspace_member import WorkspaceMember
from app.schemas.growth_dna import (
    GrowthDnaLabelUpdate,
    GrowthDnaPublic,
    GrowthDnaSummary,
)
from app.schemas.onboarding import OnboardingProfilePublic, OnboardingProfileUpdate
from app.security.dependencies import get_current_member, require_role
from app.security.permissions import Role
from app.services.growth_dna_service import (
    delete_profile,
    enrich_growth_dna_background,
    generate_growth_dna,
    get_by_id,
    get_latest_for_workspace,
    list_for_workspace,
    restore_onboarding_from_profile,
    set_label,
)
from app.services.onboarding_service import (
    get_or_create_profile,
    update_profile,
)

router = APIRouter()


class GrowthDnaNotFoundError(AdVantaError):
    status_code = 404
    code = "growth_dna_not_found"


@router.get("/{workspace_id}/onboarding", response_model=OnboardingProfilePublic)
def get_onboarding(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> OnboardingProfilePublic:
    profile = get_or_create_profile(db, workspace_id=workspace_id)
    return OnboardingProfilePublic.model_validate(profile)


@router.post(
    "/{workspace_id}/onboarding",
    response_model=OnboardingProfilePublic,
)
def update_onboarding(
    workspace_id: UUID,
    payload: OnboardingProfileUpdate,
    _member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> OnboardingProfilePublic:
    profile = get_or_create_profile(db, workspace_id=workspace_id)
    profile = update_profile(db, profile=profile, payload=payload)
    return OnboardingProfilePublic.model_validate(profile)


@router.post(
    "/{workspace_id}/growth-dna/generate",
    response_model=GrowthDnaPublic,
    status_code=status.HTTP_201_CREATED,
)
def generate_growth_dna_endpoint(
    workspace_id: UUID,
    background_tasks: BackgroundTasks,
    _member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> GrowthDnaPublic:
    profile = get_or_create_profile(db, workspace_id=workspace_id)
    # Returns the deterministic profile immediately; the AI tailoring runs in
    # the background so the request never blocks on a slow LLM call.
    dna = generate_growth_dna(db, profile=profile)
    if (dna.marketing_strategy or {}).get("enrichment") == "pending":
        background_tasks.add_task(enrich_growth_dna_background, workspace_id, dna.id)
    return GrowthDnaPublic.model_validate(dna)


@router.get("/{workspace_id}/growth-dna", response_model=GrowthDnaPublic)
def get_growth_dna(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> GrowthDnaPublic:
    dna = get_latest_for_workspace(db, workspace_id=workspace_id)
    if dna is None:
        raise GrowthDnaNotFoundError("No Growth DNA Profile generated for this workspace yet.")
    return GrowthDnaPublic.model_validate(dna)


# Static path declared before "/{dna_id}" so "history" never hits the UUID route.
@router.get(
    "/{workspace_id}/growth-dna/history",
    response_model=list[GrowthDnaSummary],
)
def list_growth_dna_history(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[GrowthDnaSummary]:
    rows = list_for_workspace(db, workspace_id=workspace_id)
    return [GrowthDnaSummary.model_validate(r) for r in rows]


@router.get("/{workspace_id}/growth-dna/{dna_id}", response_model=GrowthDnaPublic)
def get_growth_dna_by_id(
    workspace_id: UUID,
    dna_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> GrowthDnaPublic:
    dna = get_by_id(db, workspace_id=workspace_id, dna_id=dna_id)
    if dna is None:
        raise GrowthDnaNotFoundError("Growth DNA Profile not found in this workspace.")
    return GrowthDnaPublic.model_validate(dna)


@router.patch("/{workspace_id}/growth-dna/{dna_id}", response_model=GrowthDnaPublic)
def rename_growth_dna(
    workspace_id: UUID,
    dna_id: UUID,
    payload: GrowthDnaLabelUpdate,
    _member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> GrowthDnaPublic:
    dna = get_by_id(db, workspace_id=workspace_id, dna_id=dna_id)
    if dna is None:
        raise GrowthDnaNotFoundError("Growth DNA Profile not found in this workspace.")
    dna = set_label(db, dna=dna, label=payload.label)
    return GrowthDnaPublic.model_validate(dna)


@router.delete(
    "/{workspace_id}/growth-dna/{dna_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_growth_dna(
    workspace_id: UUID,
    dna_id: UUID,
    _member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> Response:
    deleted = delete_profile(db, workspace_id=workspace_id, dna_id=dna_id)
    if not deleted:
        raise GrowthDnaNotFoundError("Growth DNA Profile not found in this workspace.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{workspace_id}/growth-dna/{dna_id}/use-onboarding",
    response_model=OnboardingProfilePublic,
)
def use_growth_dna_onboarding(
    workspace_id: UUID,
    dna_id: UUID,
    _member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> OnboardingProfilePublic:
    """Load this profile's frozen onboarding answers back into the workspace's
    onboarding profile, so the wizard opens pre-filled with that product."""
    dna = get_by_id(db, workspace_id=workspace_id, dna_id=dna_id)
    if dna is None:
        raise GrowthDnaNotFoundError("Growth DNA Profile not found in this workspace.")
    profile = restore_onboarding_from_profile(db, dna=dna)
    return OnboardingProfilePublic.model_validate(profile)
