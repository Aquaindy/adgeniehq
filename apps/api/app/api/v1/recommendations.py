from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.workspace_member import WorkspaceMember
from app.schemas.agents import ExecutionPublic, RecommendationPublic
from app.schemas.recommendations import (
    AuditLogPublic,
    ApproveRecommendationRequest,
    ApproveRecommendationResponse,
    RecommendationUpdate,
    RejectRecommendationRequest,
)
from app.security.dependencies import get_current_member
from app.security.permissions import Role, require_role_at_least
from app.services import audit_service, execution_service
from app.services.agent_service import serialize_recommendation
from app.services.recommendation_service import (
    approve_recommendation,
    edit_recommendation,
    get_recommendation,
    reject_recommendation,
)

router = APIRouter()


@router.get(
    "/{workspace_id}/recommendations/{recommendation_id}",
    response_model=RecommendationPublic,
)
def get_one(
    workspace_id: UUID,
    recommendation_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> RecommendationPublic:
    rec = get_recommendation(
        db, workspace_id=workspace_id, recommendation_id=recommendation_id
    )
    return serialize_recommendation(rec)


@router.post(
    "/{workspace_id}/recommendations/{recommendation_id}/approve",
    response_model=ApproveRecommendationResponse,
)
def approve(
    workspace_id: UUID,
    recommendation_id: UUID,
    request: Request,
    payload: ApproveRecommendationRequest | None = None,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> ApproveRecommendationResponse:
    auto_execute = payload.auto_execute if payload is not None else True
    rec, execution = approve_recommendation(
        db,
        workspace_id=workspace_id,
        recommendation_id=recommendation_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        request=request,
        auto_execute=auto_execute,
    )
    return ApproveRecommendationResponse(
        recommendation=serialize_recommendation(rec),
        execution=ExecutionPublic.model_validate(execution) if execution else None,
    )


@router.post(
    "/{workspace_id}/recommendations/{recommendation_id}/reject",
    response_model=RecommendationPublic,
)
def reject(
    workspace_id: UUID,
    recommendation_id: UUID,
    request: Request,
    payload: RejectRecommendationRequest | None = None,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> RecommendationPublic:
    rec = reject_recommendation(
        db,
        workspace_id=workspace_id,
        recommendation_id=recommendation_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        request=request,
        reason=payload.reason if payload else None,
    )
    return serialize_recommendation(rec)


@router.patch(
    "/{workspace_id}/recommendations/{recommendation_id}",
    response_model=RecommendationPublic,
)
def edit(
    workspace_id: UUID,
    recommendation_id: UUID,
    payload: RecommendationUpdate,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> RecommendationPublic:
    rec = edit_recommendation(
        db,
        workspace_id=workspace_id,
        recommendation_id=recommendation_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        updates=payload.model_dump(exclude_unset=True),
        request=request,
    )
    return serialize_recommendation(rec)


@router.post(
    "/{workspace_id}/recommendations/{recommendation_id}/execute",
    response_model=ExecutionPublic,
)
def execute(
    workspace_id: UUID,
    recommendation_id: UUID,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ExecutionPublic:
    """Run the change described by a recommendation against its provider.

    Used when the user approved without auto-execute, or when a previous
    execution failed and the user wants to retry. Risk-gated to the same
    minimum role as approval.

    Send an `Idempotency-Key` header to make a retry safe: a second call with
    the same key returns the original execution row instead of re-dispatching.
    Without a key, the service falls back to a server-side guard that refuses
    to re-execute when a non-reverted prior execution is RUNNING or SUCCEEDED."""

    rec = get_recommendation(
        db, workspace_id=workspace_id, recommendation_id=recommendation_id
    )
    # Reuse the same risk → role mapping as approve/reject.
    from app.services.recommendation_service import RISK_TO_MIN_ROLE

    require_role_at_least(member.role, RISK_TO_MIN_ROLE[rec.risk_level])

    execution = execution_service.execute_recommendation(
        db,
        rec=rec,
        actor_user_id=member.user_id,
        request=request,
        idempotency_key=idempotency_key,
    )
    return ExecutionPublic.model_validate(execution)


@router.post(
    "/{workspace_id}/recommendations/executions/{execution_id}/revert",
    response_model=ExecutionPublic,
)
def revert(
    workspace_id: UUID,
    execution_id: UUID,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> ExecutionPublic:
    """Apply the inverse of a previously-succeeded execution. Admin-only."""

    require_role_at_least(member.role, Role.ADMIN)
    execution = execution_service.get_execution(
        db, workspace_id=workspace_id, execution_id=execution_id
    )
    revert_row = execution_service.revert_execution(
        db, execution=execution, actor_user_id=member.user_id, request=request
    )
    return ExecutionPublic.model_validate(revert_row)


@router.get(
    "/{workspace_id}/recommendations/{recommendation_id}/executions",
    response_model=list[ExecutionPublic],
)
def list_executions(
    workspace_id: UUID,
    recommendation_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[ExecutionPublic]:
    rows = execution_service.list_executions_for_recommendation(
        db, workspace_id=workspace_id, recommendation_id=recommendation_id
    )
    return [ExecutionPublic.model_validate(r) for r in rows]


@router.get(
    "/{workspace_id}/recommendations/{recommendation_id}/audit-logs",
    response_model=list[AuditLogPublic],
)
def list_audit_logs(
    workspace_id: UUID,
    recommendation_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[AuditLogPublic]:
    rec = get_recommendation(
        db, workspace_id=workspace_id, recommendation_id=recommendation_id
    )
    rows = audit_service.list_for_resource(
        db,
        workspace_id=workspace_id,
        resource_type="recommendation",
        resource_id=rec.id,
    )
    return [
        AuditLogPublic(
            id=row.id,
            workspace_id=row.workspace_id,
            actor_type=row.actor_type,
            actor_id=row.actor_id,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            metadata=row.metadata_json,
            ip_address=row.ip_address,
            user_agent=row.user_agent,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/{workspace_id}/recommendations/executions.csv")
def export_executions_csv(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
):
    from fastapi import Response

    from app.services.csv_export import export_executions

    body = export_executions(db, workspace_id=workspace_id)
    return Response(
        content=body,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="executions.csv"'
        },
    )
