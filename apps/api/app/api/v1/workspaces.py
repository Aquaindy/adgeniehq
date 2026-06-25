from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.db.session import get_db
from app.models.user import User
from app.models.workspace_member import WorkspaceMember
from app.schemas.workspaces import (
    MemberPublic,
    MemberUpdateRequest,
    PublishWebhookConfig,
    PublishWebhookUpdate,
    WorkspaceCreateRequest,
    WorkspaceMembership,
    WorkspacePublic,
    WorkspaceUpdateRequest,
)
from app.security.encryption import encrypt
from app.security.dependencies import (
    get_current_member,
    get_current_user,
    require_role,
)
from app.security.permissions import (
    MemberStatus,
    PermissionDeniedError,
    Role,
    require_role_at_least,
    role_at_least,
)
from app.services.workspace_service import (
    create_workspace_for_user,
    list_members,
    list_workspaces_for_user,
    update_member,
)

router = APIRouter()


class MemberNotFoundError(AdVantaError):
    status_code = 404
    code = "member_not_found"


class CannotDemoteSoleOwnerError(AdVantaError):
    status_code = 409
    code = "cannot_demote_sole_owner"


@router.get("", response_model=list[WorkspaceMembership])
def list_my_workspaces(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WorkspaceMembership]:
    rows = list_workspaces_for_user(db, user=user)
    return [
        WorkspaceMembership(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            created_at=workspace.created_at,
            role=member.role,
            status=member.status,
        )
        for workspace, member in rows
    ]


@router.post("", response_model=WorkspaceMembership, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceMembership:
    workspace = create_workspace_for_user(db, owner=user, name=payload.name)
    return WorkspaceMembership(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        created_at=workspace.created_at,
        role=Role.OWNER,
        status=MemberStatus.ACTIVE,
    )


@router.get("/{workspace_id}", response_model=WorkspaceMembership)
def get_workspace_endpoint(
    workspace_id: UUID,  # noqa: ARG001 — used by dependency
    member: WorkspaceMember = Depends(get_current_member),
) -> WorkspaceMembership:
    workspace = member.workspace
    return WorkspaceMembership(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        created_at=workspace.created_at,
        role=member.role,
        status=member.status,
    )


@router.patch("/{workspace_id}", response_model=WorkspacePublic)
def update_workspace(
    workspace_id: UUID,  # noqa: ARG001 — used by dependency
    payload: WorkspaceUpdateRequest,
    member: WorkspaceMember = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> WorkspacePublic:
    workspace = member.workspace
    if payload.name is not None:
        workspace.name = payload.name.strip()
    db.commit()
    db.refresh(workspace)
    return WorkspacePublic.model_validate(workspace)


@router.get("/{workspace_id}/members", response_model=list[MemberPublic])
def list_workspace_members(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[MemberPublic]:
    rows = list_members(db, workspace_id)
    return [
        MemberPublic(
            id=member.id,
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=member.role,
            status=member.status,
            created_at=member.created_at,
        )
        for member, user in rows
    ]


@router.patch("/{workspace_id}/members/{member_id}", response_model=MemberPublic)
def update_workspace_member(
    workspace_id: UUID,
    member_id: UUID,
    payload: MemberUpdateRequest,
    actor: WorkspaceMember = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> MemberPublic:
    target = db.get(WorkspaceMember, member_id)
    if target is None or target.workspace_id != workspace_id:
        raise MemberNotFoundError("Member not found in this workspace.")

    # A non-Owner cannot modify a peer at or above their own rank (only the
    # Owner can act on Admins/Owners). Acting on yourself is still allowed
    # (the sole-Owner demotion guard below covers the dangerous case).
    if (
        actor.role != Role.OWNER
        and target.id != actor.id
        and role_at_least(target.role, actor.role)
    ):
        raise PermissionDeniedError("You cannot modify a member at or above your role.")

    # If demoting an Owner, ensure another Owner exists.
    if (
        payload.role is not None
        and target.role == Role.OWNER
        and payload.role != Role.OWNER
    ):
        other_owner_count = (
            db.query(WorkspaceMember)
            .filter(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.id != target.id,
                WorkspaceMember.role == Role.OWNER,
                WorkspaceMember.status == MemberStatus.ACTIVE,
            )
            .count()
        )
        if other_owner_count == 0:
            raise CannotDemoteSoleOwnerError(
                "Promote another member to Owner before demoting the sole Owner."
            )

    # You can never grant a role higher than your own (generalizes the
    # Owner-promotion guard to any future intermediate role).
    if payload.role is not None:
        require_role_at_least(actor.role, payload.role)

    updated = update_member(db, member=target, role=payload.role, status=payload.status)
    target_user = updated.user
    return MemberPublic(
        id=updated.id,
        user_id=target_user.id,
        email=target_user.email,
        full_name=target_user.full_name,
        role=updated.role,
        status=updated.status,
        created_at=updated.created_at,
    )


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: Role = Role.MARKETER


class InvitationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    email: str
    role: Role
    status: str
    expires_at: datetime
    invited_by: UUID | None
    accepted_by: UUID | None
    accepted_at: datetime | None
    created_at: datetime


class AcceptInvitationRequest(BaseModel):
    token: str


@router.post(
    "/{workspace_id}/members/invite",
    response_model=InvitationPublic,
)
def invite_member(
    workspace_id: UUID,  # noqa: ARG001 — used for routing
    payload: InviteMemberRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> InvitationPublic:
    from app.services import invitation_service

    inviter = db.get(User, member.user_id)
    invitation, _plaintext = invitation_service.create_invitation(
        db,
        workspace=member.workspace,
        inviter=inviter,
        actor_role=member.role,
        email=payload.email,
        role=payload.role,
        request=request,
    )
    return InvitationPublic.model_validate(invitation)


@router.get(
    "/{workspace_id}/members/invitations",
    response_model=list[InvitationPublic],
)
def list_invitations(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> list[InvitationPublic]:
    from app.services import invitation_service

    rows = invitation_service.list_pending(db, workspace_id=workspace_id)
    return [InvitationPublic.model_validate(r) for r in rows]


@router.post(
    "/{workspace_id}/members/invitations/{invitation_id}/revoke",
    response_model=InvitationPublic,
)
def revoke_invitation(
    workspace_id: UUID,
    invitation_id: UUID,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> InvitationPublic:
    from app.services import invitation_service

    row = invitation_service.revoke_invitation(
        db,
        workspace_id=workspace_id,
        invitation_id=invitation_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        request=request,
    )
    return InvitationPublic.model_validate(row)


# ---------------------------------------------------------------------------
# Publish-webhook settings
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/publish-webhook",
    response_model=PublishWebhookConfig,
)
def get_publish_webhook(
    workspace_id: UUID,  # noqa: ARG001 — workspace resolved through membership
    member: WorkspaceMember = Depends(require_role(Role.ADMIN)),
) -> PublishWebhookConfig:
    workspace = member.workspace
    return PublishWebhookConfig(
        publish_webhook_url=workspace.publish_webhook_url,
        has_secret=bool(workspace.encrypted_publish_webhook_secret),
    )


@router.patch(
    "/{workspace_id}/publish-webhook",
    response_model=PublishWebhookConfig,
)
def update_publish_webhook(
    workspace_id: UUID,  # noqa: ARG001
    payload: PublishWebhookUpdate,
    member: WorkspaceMember = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> PublishWebhookConfig:
    """Configure the CMS publish hook.

    Empty-string clears either field. The secret is encrypted at rest with
    the same Fernet key as OAuth tokens. The plaintext secret is never
    returned on a subsequent GET — the response only reports whether one
    is set."""

    workspace = member.workspace
    if payload.publish_webhook_url is not None:
        url = payload.publish_webhook_url.strip() or None
        if url and not url.lower().startswith(("http://", "https://")):
            from app.core.exceptions import AdVantaError

            class InvalidWebhookUrlError(AdVantaError):
                status_code = 400
                code = "invalid_webhook_url"

            raise InvalidWebhookUrlError(
                "publish_webhook_url must start with http:// or https://."
            )
        workspace.publish_webhook_url = url

    if payload.publish_webhook_secret is not None:
        plain = payload.publish_webhook_secret.strip()
        workspace.encrypted_publish_webhook_secret = (
            encrypt(plain) if plain else None
        )

    db.commit()
    db.refresh(workspace)
    return PublishWebhookConfig(
        publish_webhook_url=workspace.publish_webhook_url,
        has_secret=bool(workspace.encrypted_publish_webhook_secret),
    )


# ---------------------------------------------------------------------------
# Accept-invitation — workspace-id-less because the user joining might not yet
# have any workspace selected. Mounted under the same prefix as /workspaces;
# the caller just needs to be authenticated.
# ---------------------------------------------------------------------------


@router.post("/invitations/accept", response_model=WorkspaceMembership)
def accept_invitation(
    payload: "AcceptInvitationRequest",  # forward ref — defined above
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceMembership:
    from app.services import invitation_service

    member = invitation_service.accept_invitation(
        db, token=payload.token, accepting_user=user, request=request
    )
    workspace = member.workspace
    return WorkspaceMembership(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        created_at=workspace.created_at,
        role=member.role,
        status=member.status,
    )
