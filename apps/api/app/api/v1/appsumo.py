from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.schemas.appsumo import (
    AdminGenerateRequest,
    AdminGenerateResponse,
    AppSumoStatus,
    CodeStats,
    DeactivateRequest,
    RedeemRequest,
)
from app.security.dependencies import (
    get_current_member,
    require_owner,
    require_superuser,
)
from app.services import appsumo_service

# Workspace-scoped (auth required)
workspace_router = APIRouter()

# Superuser-only code administration
admin_router = APIRouter()


@workspace_router.get(
    "/{workspace_id}/appsumo/status", response_model=AppSumoStatus
)
def appsumo_status(
    workspace_id: UUID,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> AppSumoStatus:
    return AppSumoStatus(**appsumo_service.get_status(db, workspace_id=workspace_id))


@workspace_router.post(
    "/{workspace_id}/appsumo/redeem",
    response_model=AppSumoStatus,
    status_code=status.HTTP_200_OK,
)
def redeem(
    workspace_id: UUID,
    payload: RedeemRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_owner),
    db: Session = Depends(get_db),
) -> AppSumoStatus:
    workspace = db.get(Workspace, workspace_id)
    assert workspace is not None  # require_owner guarantees membership
    result = appsumo_service.redeem_code(
        db,
        workspace=workspace,
        user=member.user,
        code=payload.code,
        request=request,
    )
    return AppSumoStatus(**result)


# ---------------------------------------------------------------------------
# Admin (superuser) — code minting + lifecycle
# ---------------------------------------------------------------------------


@admin_router.post(
    "/admin/codes",
    response_model=AdminGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_codes(
    payload: AdminGenerateRequest,
    _user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> AdminGenerateResponse:
    rows = appsumo_service.generate_codes(
        db, count=payload.count, batch=payload.batch, prefix=payload.prefix
    )
    return AdminGenerateResponse(
        generated=len(rows),
        batch=payload.batch,
        codes=[r.code for r in rows],
    )


@admin_router.get("/admin/codes/stats", response_model=CodeStats)
def codes_stats(
    _user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> CodeStats:
    return CodeStats(**appsumo_service.code_stats(db))


@admin_router.post("/admin/codes/deactivate", status_code=status.HTTP_200_OK)
def deactivate_code(
    payload: DeactivateRequest,
    _user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> dict:
    result = appsumo_service.deactivate_code(db, code=payload.code)
    return {"deactivated": True, "workspace_status": result}
