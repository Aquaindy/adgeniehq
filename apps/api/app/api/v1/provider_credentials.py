"""BYOK provider credentials.

Workspace admins can save third-party API keys (OpenAI, Anthropic, Google AI)
that AdVanta uses *on the workspace's behalf* for LLM-backed work. The
plaintext is encrypted at rest with Fernet and never returned in responses
once stored.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.provider_credential import (
    ProviderCredentialProvider,
    ProviderCredentialTestStatus,
)
from app.models.workspace_member import WorkspaceMember
from app.security.dependencies import get_current_member
from app.services import provider_credentials_service

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ProviderSpecPublic(BaseModel):
    provider_id: ProviderCredentialProvider
    display_name: str
    docs_url: str
    secret_hint: str


class ProviderCredentialPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: ProviderCredentialProvider
    label: str | None
    last_four: str
    last_tested_at: datetime | None
    last_test_status: ProviderCredentialTestStatus | None
    last_test_error: str | None
    revoked_at: datetime | None
    created_at: datetime


class ProviderCredentialAddRequest(BaseModel):
    provider: ProviderCredentialProvider
    secret: str = Field(min_length=12, max_length=400)
    label: str | None = Field(default=None, max_length=120)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/provider-credentials/specs",
    response_model=list[ProviderSpecPublic],
)
def list_specs(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
) -> list[ProviderSpecPublic]:
    """Static catalog of supported providers — used by the UI to render the
    'Add credential' form. Workspace-scoped only because we want it gated
    behind auth + membership."""
    return [
        ProviderSpecPublic(
            provider_id=spec.provider_id,
            display_name=spec.display_name,
            docs_url=spec.docs_url,
            secret_hint=spec.secret_hint,
        )
        for spec in provider_credentials_service.list_provider_specs()
    ]


@router.get(
    "/{workspace_id}/provider-credentials",
    response_model=list[ProviderCredentialPublic],
)
def list_credentials(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[ProviderCredentialPublic]:
    rows = provider_credentials_service.list_credentials(
        db, workspace_id=workspace_id
    )
    return [ProviderCredentialPublic.model_validate(r) for r in rows]


@router.post(
    "/{workspace_id}/provider-credentials",
    response_model=ProviderCredentialPublic,
    status_code=status.HTTP_201_CREATED,
)
def add_credential(
    workspace_id: UUID,
    payload: ProviderCredentialAddRequest,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> ProviderCredentialPublic:
    cred = provider_credentials_service.add_credential(
        db,
        workspace_id=workspace_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        provider=payload.provider,
        secret=payload.secret,
        label=payload.label,
    )
    return ProviderCredentialPublic.model_validate(cred)


@router.post(
    "/{workspace_id}/provider-credentials/{credential_id}/test",
    response_model=ProviderCredentialPublic,
)
def test_credential(
    workspace_id: UUID,
    credential_id: UUID,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> ProviderCredentialPublic:
    cred = provider_credentials_service.test_credential(
        db,
        workspace_id=workspace_id,
        credential_id=credential_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
    )
    return ProviderCredentialPublic.model_validate(cred)


@router.delete(
    "/{workspace_id}/provider-credentials/{credential_id}",
    response_model=ProviderCredentialPublic,
)
def revoke_credential(
    workspace_id: UUID,
    credential_id: UUID,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> ProviderCredentialPublic:
    cred = provider_credentials_service.revoke_credential(
        db,
        workspace_id=workspace_id,
        credential_id=credential_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
    )
    return ProviderCredentialPublic.model_validate(cred)
