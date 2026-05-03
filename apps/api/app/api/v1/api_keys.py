from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.workspace_member import WorkspaceMember
from app.security.dependencies import get_current_member
from app.security.permissions import Role
from app.services import api_key_service

router = APIRouter()


class ApiKeyPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label: str
    prefix: str
    role: Role
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiKeyCreatePublic(ApiKeyPublic):
    """Returned exactly once at creation — `plaintext_key` is the cleartext
    value. Store it now; we can't recover it."""

    plaintext_key: str


class ApiKeyCreateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    role: Role = Role.MARKETER
    expires_at: datetime | None = None


@router.get("/{workspace_id}/api-keys", response_model=list[ApiKeyPublic])
def list_keys(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[ApiKeyPublic]:
    rows = api_key_service.list_keys(db, workspace_id=workspace_id)
    return [ApiKeyPublic.model_validate(r) for r in rows]


@router.post(
    "/{workspace_id}/api-keys",
    response_model=ApiKeyCreatePublic,
    status_code=status.HTTP_201_CREATED,
)
def create_key(
    workspace_id: UUID,
    payload: ApiKeyCreateRequest,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> ApiKeyCreatePublic:
    key, plaintext = api_key_service.create_key(
        db,
        workspace_id=workspace_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        label=payload.label,
        role=payload.role,
        expires_at=payload.expires_at,
    )
    public = ApiKeyPublic.model_validate(key)
    return ApiKeyCreatePublic(**public.model_dump(), plaintext_key=plaintext)


@router.post(
    "/{workspace_id}/api-keys/{key_id}/revoke", response_model=ApiKeyPublic
)
def revoke_key(
    workspace_id: UUID,
    key_id: UUID,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> ApiKeyPublic:
    key = api_key_service.revoke_key(
        db,
        workspace_id=workspace_id,
        key_id=key_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
    )
    return ApiKeyPublic.model_validate(key)
