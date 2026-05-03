from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.db.session import get_db
from app.models.workspace_member import WorkspaceMember
from app.schemas.agents import (
    AgentCatalogEntry,
    AgentRunDetail,
    AgentRunRequest,
    AgentRunSummary,
    AgentTaskPublic,
    RecommendationPublic,
)
from app.security.dependencies import get_current_member, require_role
from app.security.permissions import Role
from app.services.agent_service import (
    get_run_detail,
    list_agents_with_last_run,
    list_recent_tasks,
    list_recommendations,
    list_runs,
)
from app.workers.dispatch import run_or_dispatch
from app.workers.tasks import run_agent_task

router = APIRouter()


class RunNotFoundError(AdVantaError):
    status_code = 404
    code = "agent_run_not_found"


@router.get("/{workspace_id}/agents", response_model=list[AgentCatalogEntry])
def list_agents(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[AgentCatalogEntry]:
    return list_agents_with_last_run(db, workspace_id=workspace_id)


@router.post(
    "/{workspace_id}/agents/run",
    response_model=AgentRunDetail,
    status_code=status.HTTP_201_CREATED,
)
def trigger_agent_run(
    workspace_id: UUID,
    payload: AgentRunRequest,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> AgentRunDetail:
    # Route through run_or_dispatch so that with WORKERS_ENABLED=1 the actual
    # agent work runs on the celery pool (its own process, its own DB session,
    # its own provider HTTP timeouts) instead of pinning a FastAPI worker. In
    # sync mode the task runs inline — same behaviour as before this change.
    result = run_or_dispatch(
        run_agent_task,
        workspace_id=str(workspace_id),
        agent_type=payload.agent_type,
        triggered_by_user_id=str(member.user_id),
        input_payload=payload.input_payload or {},
    )
    data = result.get(timeout=300)
    run_id = UUID(data["run_id"])
    detail = get_run_detail(db, workspace_id=workspace_id, run_id=run_id)
    assert detail is not None  # task just created it
    return detail


@router.get("/{workspace_id}/agents/runs", response_model=list[AgentRunSummary])
def list_agent_runs(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[AgentRunSummary]:
    return list_runs(db, workspace_id=workspace_id)


@router.get(
    "/{workspace_id}/agents/runs/{run_id}",
    response_model=AgentRunDetail,
)
def get_agent_run(
    workspace_id: UUID,
    run_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> AgentRunDetail:
    detail = get_run_detail(db, workspace_id=workspace_id, run_id=run_id)
    if detail is None:
        raise RunNotFoundError("Agent run not found in this workspace.")
    return detail


@router.get("/{workspace_id}/agents/tasks", response_model=list[AgentTaskPublic])
def list_agent_tasks(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[AgentTaskPublic]:
    return list_recent_tasks(db, workspace_id=workspace_id)


@router.get(
    "/{workspace_id}/recommendations",
    response_model=list[RecommendationPublic],
)
def list_workspace_recommendations(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[RecommendationPublic]:
    return list_recommendations(db, workspace_id=workspace_id)
