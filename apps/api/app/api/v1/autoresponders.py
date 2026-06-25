"""Autoresponder integration endpoints.

Connect/disconnect autoresponder providers (API-key based), list audiences,
and sync contacts in both directions (push AdVanta contacts → provider lists,
pull provider contacts → AdVanta)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.integrations.autoresponders.registry import get_adapter
from app.models.workspace_member import WorkspaceMember
from app.schemas.autoresponders import (
    AudienceListResponse,
    AudiencePublic,
    AutoresponderConnectionPublic,
    AutoresponderProviderInfo,
    ConnectAutoresponderRequest,
    ContactPublic,
    ContactSyncPublic,
    PullContactsRequest,
    PullContactsResponse,
    PushContactsRequest,
)
from app.security.dependencies import get_current_member, require_role
from app.security.permissions import Role
from app.services import autoresponder_service

router = APIRouter()


@router.get(
    "/{workspace_id}/autoresponders/catalog",
    response_model=list[AutoresponderProviderInfo],
)
def autoresponder_catalog(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
) -> list[AutoresponderProviderInfo]:
    return [AutoresponderProviderInfo(**c) for c in autoresponder_service.provider_catalog()]


@router.get(
    "/{workspace_id}/autoresponders",
    response_model=list[AutoresponderConnectionPublic],
)
def list_autoresponders(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[AutoresponderConnectionPublic]:
    conns = autoresponder_service.list_connections(db, workspace_id=workspace_id)
    return [AutoresponderConnectionPublic.model_validate(c) for c in conns]


@router.post(
    "/{workspace_id}/autoresponders/{provider_id}/connect",
    response_model=AutoresponderConnectionPublic,
)
def connect_autoresponder(
    workspace_id: UUID,
    provider_id: str,
    payload: ConnectAutoresponderRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> AutoresponderConnectionPublic:
    get_adapter(provider_id)  # 404 on unknown provider
    conn = autoresponder_service.connect(
        db,
        workspace_id=workspace_id,
        user_id=member.user_id,
        provider_id=provider_id,
        api_key=payload.api_key,
        config=payload.config,
        request=request,
    )
    return AutoresponderConnectionPublic.model_validate(conn)


@router.post(
    "/{workspace_id}/autoresponders/{provider_id}/disconnect",
    response_model=AutoresponderConnectionPublic,
)
def disconnect_autoresponder(
    workspace_id: UUID,
    provider_id: str,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> AutoresponderConnectionPublic:
    get_adapter(provider_id)
    conn = autoresponder_service.disconnect(
        db,
        workspace_id=workspace_id,
        user_id=member.user_id,
        provider_id=provider_id,
        request=request,
    )
    return AutoresponderConnectionPublic.model_validate(conn)


@router.get(
    "/{workspace_id}/autoresponders/{provider_id}/audiences",
    response_model=AudienceListResponse,
)
def list_audiences(
    workspace_id: UUID,
    provider_id: str,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> AudienceListResponse:
    adapter = get_adapter(provider_id)
    audiences = autoresponder_service.list_audiences(
        db, workspace_id=workspace_id, provider_id=provider_id
    )
    return AudienceListResponse(
        provider=provider_id,
        supports_audience_listing=adapter.supports_audience_listing,
        freeform_audience=adapter.freeform_audience,
        audiences=[
            AudiencePublic(
                external_id=a.external_id, name=a.name, member_count=a.member_count
            )
            for a in audiences
        ],
    )


@router.post(
    "/{workspace_id}/autoresponders/{provider_id}/push",
    response_model=ContactSyncPublic,
)
def push_contacts(
    workspace_id: UUID,
    provider_id: str,
    payload: PushContactsRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> ContactSyncPublic:
    get_adapter(provider_id)
    sync = autoresponder_service.push_contacts(
        db,
        workspace_id=workspace_id,
        user_id=member.user_id,
        provider_id=provider_id,
        audience_id=payload.audience_id,
        audience_name=payload.audience_name,
        contacts=[c.model_dump() for c in payload.contacts],
        source=payload.source,
        request=request,
    )
    return ContactSyncPublic.model_validate(sync)


@router.post(
    "/{workspace_id}/autoresponders/{provider_id}/pull",
    response_model=PullContactsResponse,
)
def pull_contacts(
    workspace_id: UUID,
    provider_id: str,
    payload: PullContactsRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> PullContactsResponse:
    get_adapter(provider_id)
    contacts, sync = autoresponder_service.pull_contacts(
        db,
        workspace_id=workspace_id,
        user_id=member.user_id,
        provider_id=provider_id,
        audience_id=payload.audience_id,
        limit=payload.limit,
        request=request,
    )
    return PullContactsResponse(
        sync=ContactSyncPublic.model_validate(sync),
        contacts=[
            ContactPublic(
                email=c.email,
                first_name=c.first_name,
                last_name=c.last_name,
                phone=c.phone,
                tags=c.tags,
            )
            for c in contacts
        ],
    )


@router.get(
    "/{workspace_id}/autoresponders/activity",
    response_model=list[ContactSyncPublic],
)
def autoresponder_activity(
    workspace_id: UUID,
    provider: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[ContactSyncPublic]:
    syncs = autoresponder_service.list_syncs(
        db, workspace_id=workspace_id, provider_id=provider, limit=limit
    )
    return [ContactSyncPublic.model_validate(s) for s in syncs]
