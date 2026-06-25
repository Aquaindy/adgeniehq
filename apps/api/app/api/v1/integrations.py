from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import get_db
from app.integrations.registry import get_provider
from app.models.connected_account import ConnectionStatus
from app.models.workspace_member import WorkspaceMember
from app.schemas.integrations import ConnectUrlResponse, IntegrationStatus, SyncLogPublic
from app.security.dependencies import get_current_member, require_role
from app.security.permissions import Role
from app.services.integration_service import (
    build_connect_url,
    disconnect,
    handle_oauth_callback,
    list_integrations_for_workspace,
    trigger_sync,
)

log = get_logger(__name__)

# Workspace-scoped router (mounted at /workspaces). All routes require auth.
workspace_router = APIRouter()

# Public router (mounted at /integrations) for the OAuth provider callback.
public_router = APIRouter()


@workspace_router.get("/{workspace_id}/integrations", response_model=list[IntegrationStatus])
def list_integrations(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[IntegrationStatus]:
    return list_integrations_for_workspace(db, workspace_id=workspace_id)


@workspace_router.get(
    "/{workspace_id}/integrations/{provider_id}/connect-url",
    response_model=ConnectUrlResponse,
)
def get_connect_url(
    workspace_id: UUID,
    provider_id: str,
    scope_mode: str = Query(default="write", pattern="^(read|write)$"),
    member: WorkspaceMember = Depends(require_role(Role.ADMIN)),
) -> ConnectUrlResponse:
    # Surface unknown providers with a real 404
    get_provider(provider_id)
    return build_connect_url(
        workspace_id=workspace_id,
        user_id=member.user_id,
        provider_id=provider_id,
        scope_mode=scope_mode,
    )


@workspace_router.post(
    "/{workspace_id}/integrations/{provider_id}/disconnect",
    response_model=IntegrationStatus,
)
def disconnect_provider(
    workspace_id: UUID,
    provider_id: str,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> IntegrationStatus:
    get_provider(provider_id)
    disconnect(
        db,
        workspace_id=workspace_id,
        provider_id=provider_id,
        user_id=member.user_id,
        request=request,
    )
    statuses = list_integrations_for_workspace(db, workspace_id=workspace_id)
    found = next((s for s in statuses if s.provider == provider_id), None)
    assert found is not None
    return found


@workspace_router.post(
    "/{workspace_id}/integrations/{provider_id}/sync",
    response_model=SyncLogPublic,
    status_code=status.HTTP_201_CREATED,
)
def sync_provider(
    workspace_id: UUID,
    provider_id: str,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> SyncLogPublic:
    get_provider(provider_id)
    sync_log = trigger_sync(
        db,
        workspace_id=workspace_id,
        provider_id=provider_id,
        user_id=member.user_id,
        request=request,
    )
    return SyncLogPublic.model_validate(sync_log)


# ---------------------------------------------------------------------------
# Public OAuth callback (no JWT — state token is the auth)
# ---------------------------------------------------------------------------


@public_router.get("/{provider_id}/callback")
def oauth_callback(
    provider_id: str,
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    # Resolve provider early so we 404 cleanly on bad provider IDs.
    get_provider(provider_id)

    error_message = error_description or error
    workspace_id, _, conn_status, message = handle_oauth_callback(
        db,
        provider_id=provider_id,
        code=code,
        state_token=state,
        error=error_message,
        request=request,
    )

    redirect_to = f"{settings.frontend_url.rstrip('/')}/integrations"
    params = {
        "provider": provider_id,
        "status": "success" if conn_status == ConnectionStatus.CONNECTED else "error",
        "workspace_id": str(workspace_id),
    }
    if message:
        params["message"] = message
    return RedirectResponse(url=f"{redirect_to}?{urlencode(params)}")
