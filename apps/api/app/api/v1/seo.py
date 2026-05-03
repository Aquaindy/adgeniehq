from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.workspace_member import WorkspaceMember
from app.schemas.seo import KeywordPublic, SearchConsoleSyncResponse, SeoProjectPublic
from app.security.dependencies import get_current_member, require_role
from app.security.permissions import Role
from app.services import seo_service

router = APIRouter()


@router.get("/{workspace_id}/seo/project", response_model=SeoProjectPublic)
def get_project(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> SeoProjectPublic:
    project = seo_service.get_or_create_project(db, workspace_id=workspace_id)
    return SeoProjectPublic.model_validate(project)


@router.get("/{workspace_id}/seo/keywords", response_model=list[KeywordPublic])
def list_keywords_endpoint(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[KeywordPublic]:
    rows = seo_service.list_keywords(db, workspace_id=workspace_id)
    return [KeywordPublic.model_validate(r) for r in rows]


@router.post(
    "/{workspace_id}/seo/sync",
    response_model=SearchConsoleSyncResponse,
    status_code=status.HTTP_201_CREATED,
)
def sync_search_console(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> SearchConsoleSyncResponse:
    project, result = seo_service.sync_search_console(db, workspace_id=workspace_id)
    return SearchConsoleSyncResponse(
        site_url=result.site_url,
        period_start=result.period_start,
        period_end=result.period_end,
        keywords_upserted=len(result.rows),
    )
