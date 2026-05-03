from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit_log import AuditActorType, AuditLog


def extract_request_meta(request: Request | None) -> tuple[str | None, str | None]:
    if request is None:
        return None, None
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else None
    )
    user_agent = request.headers.get("user-agent")
    return ip, user_agent[:512] if user_agent else None


def log_event(
    db: Session,
    *,
    workspace_id: UUID,
    actor_type: AuditActorType,
    actor_id: UUID | None,
    action: str,
    resource_type: str,
    resource_id: UUID | None,
    metadata: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditLog:
    ip_address, user_agent = extract_request_meta(request)
    entry = AuditLog(
        workspace_id=workspace_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_json=metadata,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(entry)
    db.flush()
    return entry


def list_for_resource(
    db: Session,
    *,
    workspace_id: UUID,
    resource_type: str,
    resource_id: UUID,
    limit: int = 50,
) -> list[AuditLog]:
    return (
        db.query(AuditLog)
        .filter(
            AuditLog.workspace_id == workspace_id,
            AuditLog.resource_type == resource_type,
            AuditLog.resource_id == resource_id,
        )
        .order_by(AuditLog.created_at.asc())
        .limit(limit)
        .all()
    )
