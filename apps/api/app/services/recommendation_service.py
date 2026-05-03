from datetime import datetime, timezone
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.core.logging import get_logger
from app.models.approval import Approval, ApprovalStatus
from app.models.audit_log import AuditActorType
from app.models.recommendation import (
    Recommendation,
    RecommendationStatus,
    RiskLevel,
)
from app.models.recommendation_execution import RecommendationExecution
from app.security.permissions import (
    PermissionDeniedError,
    Role,
    require_role_at_least,
)
from app.services import audit_service

log = get_logger(__name__)


class RecommendationNotFoundError(AdVantaError):
    status_code = 404
    code = "recommendation_not_found"


class InvalidApprovalStateError(AdVantaError):
    status_code = 409
    code = "invalid_approval_state"


# Map risk level → minimum role required to act on the recommendation.
RISK_TO_MIN_ROLE: dict[RiskLevel, Role] = {
    RiskLevel.LOW: Role.MARKETER,
    RiskLevel.MEDIUM: Role.ADMIN,
    RiskLevel.HIGH: Role.OWNER,
}


def _require_role_for_risk(role: Role, risk: RiskLevel) -> None:
    minimum = RISK_TO_MIN_ROLE[risk]
    try:
        require_role_at_least(role, minimum)
    except PermissionDeniedError as exc:
        raise PermissionDeniedError(
            f"This {risk.value}-risk recommendation requires {minimum.value} or higher.",
        ) from exc


def get_recommendation(
    db: Session, *, workspace_id: UUID, recommendation_id: UUID
) -> Recommendation:
    rec = (
        db.query(Recommendation)
        .filter(
            Recommendation.id == recommendation_id,
            Recommendation.workspace_id == workspace_id,
        )
        .first()
    )
    if rec is None:
        raise RecommendationNotFoundError("Recommendation not found in this workspace.")
    return rec


def _ensure_approval(db: Session, rec: Recommendation) -> Approval:
    if rec.approval is not None:
        return rec.approval
    # Defensive — shouldn't happen post-M5 because runtime auto-creates it.
    approval = Approval(
        workspace_id=rec.workspace_id,
        recommendation_id=rec.id,
        action_type=rec.recommendation_type,
        risk_level=rec.risk_level,
        status=ApprovalStatus.PENDING,
    )
    db.add(approval)
    db.flush()
    return approval


def _has_executable_action(rec: Recommendation) -> bool:
    meta = rec.metadata_json or {}
    return bool(meta.get("action") and (meta.get("provider") or rec.platform))


def approve_recommendation(
    db: Session,
    *,
    workspace_id: UUID,
    recommendation_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    request: Request | None = None,
    auto_execute: bool = True,
    actor_type: AuditActorType = AuditActorType.USER,
    audit_action: str = "recommendation.approved",
    audit_metadata_extra: dict | None = None,
) -> tuple[Recommendation, RecommendationExecution | None]:
    """Approve a recommendation.

    If `auto_execute` is True (default) and the recommendation carries an
    actionable plan (metadata.action + provider), the change is applied to the
    external provider as part of the same transaction. Returns the updated
    recommendation plus the execution row (None if no execution was attempted).

    `actor_type` + `audit_action` let callers (e.g. autopilot) emit a single
    accurate audit row instead of layering a second one on top. Defaults
    preserve the legacy USER attribution + `recommendation.approved` action.

    Execution failures are recorded as a FAILED execution row but do *not*
    invalidate the approval — the user can retry once the underlying problem
    is fixed (e.g. provider creds, account permissions)."""

    rec = get_recommendation(
        db, workspace_id=workspace_id, recommendation_id=recommendation_id
    )
    _require_role_for_risk(actor_role, rec.risk_level)

    approval = _ensure_approval(db, rec)
    if approval.status not in (ApprovalStatus.PENDING, ApprovalStatus.REJECTED):
        raise InvalidApprovalStateError(
            f"Recommendation is already in '{approval.status.value}' state."
        )

    now = datetime.now(timezone.utc)
    approval.status = ApprovalStatus.APPROVED
    approval.approved_by = actor_user_id
    approval.approved_at = now
    approval.rejected_by = None
    approval.rejected_at = None

    rec.status = RecommendationStatus.APPROVED

    audit_metadata: dict = {
        "risk_level": rec.risk_level.value,
        "recommendation_type": rec.recommendation_type,
        "auto_execute": auto_execute and _has_executable_action(rec),
    }
    if audit_metadata_extra:
        audit_metadata.update(audit_metadata_extra)

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=actor_type,
        actor_id=actor_user_id,
        action=audit_action,
        resource_type="recommendation",
        resource_id=rec.id,
        metadata=audit_metadata,
        request=request,
    )

    db.commit()
    db.refresh(rec)

    execution: RecommendationExecution | None = None
    if auto_execute and _has_executable_action(rec):
        # Imported lazily to avoid a circular import (execution_service depends
        # on the recommendation/approval models, not on this module).
        from app.services import execution_service

        # Deterministic idempotency key derived from the approval id. Every
        # auto-execute attempt for the same approval shares this key, so a
        # retried POST /approve never doubles a provider write.
        auto_key = (
            f"approval:{approval.id}" if approval is not None else None
        )

        try:
            execution = execution_service.execute_recommendation(
                db,
                rec=rec,
                actor_user_id=actor_user_id,
                request=request,
                idempotency_key=auto_key,
            )
        except execution_service.ExecutionError as exc:
            log.warning(
                "recommendation.execute.failed",
                recommendation_id=str(rec.id),
                error=str(exc),
            )
            # Re-fetch so we return the latest committed state, including the
            # FAILED execution row that the service already persisted.
            db.refresh(rec)
            execution = (
                db.query(RecommendationExecution)
                .filter(
                    RecommendationExecution.recommendation_id == rec.id,
                    RecommendationExecution.is_revert.is_(False),
                )
                .order_by(RecommendationExecution.created_at.desc())
                .first()
            )

    return rec, execution


def reject_recommendation(
    db: Session,
    *,
    workspace_id: UUID,
    recommendation_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    request: Request | None = None,
    reason: str | None = None,
) -> Recommendation:
    rec = get_recommendation(
        db, workspace_id=workspace_id, recommendation_id=recommendation_id
    )
    _require_role_for_risk(actor_role, rec.risk_level)

    approval = _ensure_approval(db, rec)
    if approval.status not in (ApprovalStatus.PENDING, ApprovalStatus.APPROVED):
        raise InvalidApprovalStateError(
            f"Recommendation is already in '{approval.status.value}' state."
        )

    now = datetime.now(timezone.utc)
    approval.status = ApprovalStatus.REJECTED
    approval.rejected_by = actor_user_id
    approval.rejected_at = now
    approval.approved_by = None
    approval.approved_at = None

    rec.status = RecommendationStatus.REJECTED

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="recommendation.rejected",
        resource_type="recommendation",
        resource_id=rec.id,
        metadata={
            "risk_level": rec.risk_level.value,
            "recommendation_type": rec.recommendation_type,
            "reason": reason,
        },
        request=request,
    )

    db.commit()
    db.refresh(rec)
    return rec


# Editable fields are user-facing copy only — risk/type/agent_run_id/status are
# considered immutable agent outputs.
EDITABLE_FIELDS = {"title", "summary", "expected_impact", "suggested_action"}


def edit_recommendation(
    db: Session,
    *,
    workspace_id: UUID,
    recommendation_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    updates: dict,
    request: Request | None = None,
) -> Recommendation:
    rec = get_recommendation(
        db, workspace_id=workspace_id, recommendation_id=recommendation_id
    )
    require_role_at_least(actor_role, Role.ADMIN)

    changes: dict[str, dict[str, str]] = {}
    for field, new_value in updates.items():
        if field not in EDITABLE_FIELDS or new_value is None:
            continue
        current = getattr(rec, field)
        if current != new_value:
            changes[field] = {"from": current, "to": new_value}
            setattr(rec, field, new_value)

    if not changes:
        return rec

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="recommendation.edited",
        resource_type="recommendation",
        resource_id=rec.id,
        metadata={"changes": changes},
        request=request,
    )

    db.commit()
    db.refresh(rec)
    return rec
