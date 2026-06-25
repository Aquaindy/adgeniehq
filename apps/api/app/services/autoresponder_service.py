"""Service layer for autoresponder connections + contact sync.

Owns persistence, API-key encryption, the contact-sync ledger, and audit
logging. Provider-specific HTTP lives in the adapters; this module never talks
to the network directly — it resolves an adapter from the registry and calls
its classmethods."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.core.logging import get_logger
from app.integrations.autoresponders.base import (
    Audience,
    AutoresponderAdapter,
    AutoresponderError,
    Contact,
)
from app.integrations.autoresponders.registry import get_adapter, list_adapters
from app.models.audit_log import AuditActorType
from app.models.autoresponder_connection import AutoresponderConnection
from app.models.autoresponder_sync import (
    AutoresponderContactSync,
    AutoresponderSyncStatus,
    SyncDirection,
)
from app.models.connected_account import ConnectionStatus
from app.security.encryption import decrypt, encrypt
from app.services import audit_service

log = get_logger(__name__)


class AutoresponderNotConnectedError(AdVantaError):
    status_code = 409
    code = "autoresponder_not_connected"


class AutoresponderConfigError(AdVantaError):
    status_code = 422
    code = "autoresponder_config_invalid"


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def provider_catalog() -> list[dict]:
    return [adapter.catalog_entry() for adapter in list_adapters()]


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------


def list_connections(db: Session, *, workspace_id: UUID) -> list[AutoresponderConnection]:
    return (
        db.query(AutoresponderConnection)
        .filter(AutoresponderConnection.workspace_id == workspace_id)
        .order_by(AutoresponderConnection.provider)
        .all()
    )


def _get_connection(
    db: Session, *, workspace_id: UUID, provider_id: str
) -> AutoresponderConnection | None:
    return (
        db.query(AutoresponderConnection)
        .filter(
            AutoresponderConnection.workspace_id == workspace_id,
            AutoresponderConnection.provider == provider_id,
        )
        .first()
    )


def _require_connected(
    db: Session, *, workspace_id: UUID, provider_id: str
) -> AutoresponderConnection:
    conn = _get_connection(db, workspace_id=workspace_id, provider_id=provider_id)
    if conn is None or conn.status != ConnectionStatus.CONNECTED:
        raise AutoresponderNotConnectedError(
            f"{provider_id} is not connected for this workspace."
        )
    return conn


def _validate_config(adapter: type[AutoresponderAdapter], config: dict) -> None:
    for field in adapter.config_fields:
        if field.required and not str(config.get(field.key, "")).strip():
            raise AutoresponderConfigError(f"Missing required setting: {field.label}.")


def connect(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    provider_id: str,
    api_key: str | None,
    config: dict | None,
    request: Request | None = None,
) -> AutoresponderConnection:
    adapter = get_adapter(provider_id)
    config = config or {}
    _validate_config(adapter, config)
    if adapter.requires_api_key and not (api_key or "").strip():
        raise AutoresponderConfigError(f"{adapter.display_name} requires an API key.")

    conn = _get_connection(db, workspace_id=workspace_id, provider_id=provider_id)
    if conn is None:
        conn = AutoresponderConnection(workspace_id=workspace_id, provider=provider_id)
        db.add(conn)
        db.flush()

    # Verify credentials before persisting them as a working connection.
    try:
        info = adapter.verify(api_key=api_key, config=config)
    except AdVantaError as exc:
        conn.status = ConnectionStatus.ERROR
        conn.last_error = str(exc)
        conn.config = config
        audit_service.log_event(
            db,
            workspace_id=workspace_id,
            actor_type=AuditActorType.USER,
            actor_id=user_id,
            action="autoresponder.connect_failed",
            resource_type="autoresponder_connection",
            resource_id=conn.id,
            metadata={"provider": provider_id, "error": str(exc)},
            request=request,
        )
        db.commit()
        raise

    now = datetime.now(timezone.utc)
    conn.status = ConnectionStatus.CONNECTED
    conn.encrypted_api_key = encrypt(api_key) if api_key else None
    conn.config = config
    conn.connected_by = user_id
    conn.connected_at = now
    conn.last_error = None
    if info.display_name:
        conn.display_name = info.display_name
    if info.account_id:
        conn.provider_account_id = info.account_id

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        action="autoresponder.connected",
        resource_type="autoresponder_connection",
        resource_id=conn.id,
        metadata={"provider": provider_id},
        request=request,
    )
    db.commit()
    db.refresh(conn)
    return conn


def disconnect(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    provider_id: str,
    request: Request | None = None,
) -> AutoresponderConnection:
    conn = _get_connection(db, workspace_id=workspace_id, provider_id=provider_id)
    if conn is None:
        raise AutoresponderNotConnectedError(
            f"{provider_id} is not connected for this workspace."
        )
    # Drop the secret; keep the row for history.
    conn.encrypted_api_key = None
    conn.status = ConnectionStatus.DISCONNECTED
    conn.last_error = None

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        action="autoresponder.disconnected",
        resource_type="autoresponder_connection",
        resource_id=conn.id,
        metadata={"provider": provider_id},
        request=request,
    )
    db.commit()
    db.refresh(conn)
    return conn


def _api_key_for(conn: AutoresponderConnection) -> str | None:
    if not conn.encrypted_api_key:
        return None
    return decrypt(conn.encrypted_api_key)


# ---------------------------------------------------------------------------
# Audiences
# ---------------------------------------------------------------------------


def list_audiences(
    db: Session, *, workspace_id: UUID, provider_id: str
) -> list[Audience]:
    conn = _require_connected(db, workspace_id=workspace_id, provider_id=provider_id)
    adapter = get_adapter(provider_id)
    return adapter.list_audiences(api_key=_api_key_for(conn), config=conn.config or {})


# ---------------------------------------------------------------------------
# Contact sync (both directions)
# ---------------------------------------------------------------------------


def _to_contacts(rows: list[dict]) -> list[Contact]:
    out: list[Contact] = []
    for r in rows:
        out.append(
            Contact(
                email=(r.get("email") or None),
                first_name=(r.get("first_name") or None),
                last_name=(r.get("last_name") or None),
                phone=(r.get("phone") or None),
                tags=list(r.get("tags") or []),
                custom_fields=dict(r.get("custom_fields") or {}),
            )
        )
    return out


def push_contacts(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    provider_id: str,
    audience_id: str | None,
    audience_name: str | None,
    contacts: list[dict],
    source: str = "manual",
    request: Request | None = None,
) -> AutoresponderContactSync:
    conn = _require_connected(db, workspace_id=workspace_id, provider_id=provider_id)
    adapter = get_adapter(provider_id)
    contact_objs = _to_contacts(contacts)

    sync = AutoresponderContactSync(
        connection_id=conn.id,
        workspace_id=workspace_id,
        direction=SyncDirection.PUSH,
        status=AutoresponderSyncStatus.RUNNING,
        audience_external_id=audience_id,
        audience_name=audience_name,
        source=source,
        requested_count=len(contact_objs),
        started_at=datetime.now(timezone.utc),
    )
    db.add(sync)
    db.flush()

    try:
        result = adapter.push_contacts(
            api_key=_api_key_for(conn),
            config=conn.config or {},
            audience_id=audience_id,
            contacts=contact_objs,
        )
    except AdVantaError as exc:
        sync.status = AutoresponderSyncStatus.FAILED
        sync.completed_at = datetime.now(timezone.utc)
        sync.error_message = str(exc)
        conn.last_error = str(exc)
        db.commit()
        _audit_sync(db, conn=conn, user_id=user_id, sync=sync, request=request)
        raise

    sync.succeeded_count = result.succeeded
    sync.failed_count = result.failed
    sync.summary = {"errors": result.errors} if result.errors else None
    sync.status = _outcome(result.succeeded, result.failed)
    sync.completed_at = datetime.now(timezone.utc)
    conn.last_sync_at = sync.completed_at
    conn.last_error = None

    db.commit()
    _audit_sync(db, conn=conn, user_id=user_id, sync=sync, request=request)
    db.refresh(sync)
    return sync


def pull_contacts(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    provider_id: str,
    audience_id: str | None,
    limit: int = 100,
    request: Request | None = None,
) -> tuple[list[Contact], AutoresponderContactSync]:
    conn = _require_connected(db, workspace_id=workspace_id, provider_id=provider_id)
    adapter = get_adapter(provider_id)

    sync = AutoresponderContactSync(
        connection_id=conn.id,
        workspace_id=workspace_id,
        direction=SyncDirection.PULL,
        status=AutoresponderSyncStatus.RUNNING,
        audience_external_id=audience_id,
        source="audience_pull",
        started_at=datetime.now(timezone.utc),
    )
    db.add(sync)
    db.flush()

    try:
        contacts = adapter.pull_contacts(
            api_key=_api_key_for(conn),
            config=conn.config or {},
            audience_id=audience_id,
            limit=limit,
        )
    except AdVantaError as exc:
        sync.status = AutoresponderSyncStatus.FAILED
        sync.completed_at = datetime.now(timezone.utc)
        sync.error_message = str(exc)
        conn.last_error = str(exc)
        db.commit()
        _audit_sync(db, conn=conn, user_id=user_id, sync=sync, request=request)
        raise

    # Persist counts only — not the contact PII itself.
    sync.requested_count = len(contacts)
    sync.succeeded_count = len(contacts)
    sync.status = AutoresponderSyncStatus.SUCCEEDED
    sync.completed_at = datetime.now(timezone.utc)
    conn.last_sync_at = sync.completed_at
    conn.last_error = None

    db.commit()
    _audit_sync(db, conn=conn, user_id=user_id, sync=sync, request=request)
    db.refresh(sync)
    return contacts, sync


def list_syncs(
    db: Session, *, workspace_id: UUID, provider_id: str | None = None, limit: int = 25
) -> list[AutoresponderContactSync]:
    q = db.query(AutoresponderContactSync).filter(
        AutoresponderContactSync.workspace_id == workspace_id
    )
    if provider_id:
        conn = _get_connection(db, workspace_id=workspace_id, provider_id=provider_id)
        if conn is None:
            return []
        q = q.filter(AutoresponderContactSync.connection_id == conn.id)
    return q.order_by(AutoresponderContactSync.created_at.desc()).limit(limit).all()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _outcome(succeeded: int, failed: int) -> AutoresponderSyncStatus:
    if succeeded == 0 and failed > 0:
        return AutoresponderSyncStatus.FAILED
    if failed > 0:
        return AutoresponderSyncStatus.PARTIAL
    return AutoresponderSyncStatus.SUCCEEDED


def _audit_sync(
    db: Session,
    *,
    conn: AutoresponderConnection,
    user_id: UUID,
    sync: AutoresponderContactSync,
    request: Request | None,
) -> None:
    audit_service.log_event(
        db,
        workspace_id=conn.workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        action=f"autoresponder.contacts_{sync.direction.value}",
        resource_type="autoresponder_contact_sync",
        resource_id=sync.id,
        metadata={
            "provider": conn.provider,
            "status": sync.status.value,
            "requested": sync.requested_count,
            "succeeded": sync.succeeded_count,
            "failed": sync.failed_count,
            "audience": sync.audience_external_id,
        },
        request=request,
    )
    db.commit()
