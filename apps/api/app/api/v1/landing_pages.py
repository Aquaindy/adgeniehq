from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.agents.runtime import run_agent
from app.db.session import get_db
from app.models.workspace_member import WorkspaceMember
from app.schemas.agents import AgentRunDetail
from app.schemas.landing_pages import (
    ImportFromOnboardingResponse,
    LandingPageCreate,
    LandingPagePublic,
)
from app.security.dependencies import get_current_member, require_role
from app.security.permissions import Role
from app.services import landing_page_service
from app.services.agent_service import get_run_detail

router = APIRouter()


@router.get(
    "/{workspace_id}/landing-pages",
    response_model=list[LandingPagePublic],
)
def list_pages(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[LandingPagePublic]:
    rows = landing_page_service.list_landing_pages(db, workspace_id=workspace_id)
    return [LandingPagePublic.model_validate(r) for r in rows]


@router.post(
    "/{workspace_id}/landing-pages",
    response_model=LandingPagePublic,
    status_code=status.HTTP_201_CREATED,
)
def create_page(
    workspace_id: UUID,
    payload: LandingPageCreate,
    _member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> LandingPagePublic:
    lp = landing_page_service.create_landing_page(
        db,
        workspace_id=workspace_id,
        url=str(payload.url),
        label=payload.label,
        is_primary=payload.is_primary,
    )
    return LandingPagePublic.model_validate(lp)


@router.post(
    "/{workspace_id}/landing-pages/import",
    response_model=ImportFromOnboardingResponse,
    status_code=status.HTTP_201_CREATED,
)
def import_from_onboarding_endpoint(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> ImportFromOnboardingResponse:
    created = landing_page_service.import_from_onboarding(
        db, workspace_id=workspace_id
    )
    return ImportFromOnboardingResponse(created=created)


@router.get(
    "/{workspace_id}/landing-pages/{landing_page_id}",
    response_model=LandingPagePublic,
)
def get_page(
    workspace_id: UUID,
    landing_page_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> LandingPagePublic:
    lp = landing_page_service.get_landing_page(
        db, workspace_id=workspace_id, landing_page_id=landing_page_id
    )
    return LandingPagePublic.model_validate(lp)


@router.delete(
    "/{workspace_id}/landing-pages/{landing_page_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_page(
    workspace_id: UUID,
    landing_page_id: UUID,
    _member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> None:
    landing_page_service.delete_landing_page(
        db, workspace_id=workspace_id, landing_page_id=landing_page_id
    )


@router.post(
    "/{workspace_id}/landing-pages/{landing_page_id}/audit",
    response_model=AgentRunDetail,
    status_code=status.HTTP_201_CREATED,
)
def trigger_audit(
    workspace_id: UUID,
    landing_page_id: UUID,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> AgentRunDetail:
    # Verify the landing page belongs to this workspace before kicking off the agent.
    landing_page_service.get_landing_page(
        db, workspace_id=workspace_id, landing_page_id=landing_page_id
    )
    run = run_agent(
        db,
        workspace_id=workspace_id,
        agent_type="landing_page_audit",
        triggered_by_user_id=member.user_id,
        input_payload={"landing_page_id": str(landing_page_id)},
    )
    detail = get_run_detail(db, workspace_id=workspace_id, run_id=run.id)
    assert detail is not None
    return detail
