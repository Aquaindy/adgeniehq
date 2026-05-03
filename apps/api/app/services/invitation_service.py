"""Workspace invitation flow.

Admin clicks "invite" → we mint a single-use token, hash it for storage,
email the plaintext to the invitee. The user clicks the link, lands on
/accept-invite?token=…; the frontend POSTs the token to /accept which
creates their WorkspaceMember row (and registers them first if they
aren't yet logged in)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AdVantaError
from app.core.logging import get_logger
from app.models.audit_log import AuditActorType
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_invitation import (
    InvitationStatus,
    WorkspaceInvitation,
)
from app.models.workspace_member import WorkspaceMember
from app.security.permissions import (
    MemberStatus,
    Role,
    require_role_at_least,
)
from app.services import audit_service, billing_service
from app.services.email_service import EmailMessageDraft, send_email

log = get_logger(__name__)

INVITE_TTL_DAYS = 7


class InvitationError(AdVantaError):
    status_code = 400
    code = "invalid_invitation"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _build_accept_url(token: str) -> str:
    base = (settings.frontend_url or "").rstrip("/")
    return f"{base}/accept-invite?token={token}"


def create_invitation(
    db: Session,
    *,
    workspace: Workspace,
    inviter: User,
    actor_role: Role,
    email: str,
    role: Role,
    request: Request | None = None,
) -> tuple[WorkspaceInvitation, str]:
    """Mint an invitation. Returns (row, plaintext_token). The plaintext is
    emailed to the invitee and never persisted."""

    require_role_at_least(actor_role, Role.ADMIN)
    if role == Role.OWNER and actor_role != Role.OWNER:
        raise InvitationError("Only the Owner can invite another Owner.")

    normalized_email = email.strip().lower()
    if not normalized_email or "@" not in normalized_email:
        raise InvitationError("Provide a valid email address.")

    # Plan seat-cap check. Counts active members + pending invitations
    # against plan.limits.members. Raises 402 PlanLimitExceededError.
    billing_service.assert_within_member_limit(db, workspace_id=workspace.id)

    # If they're already a member, refuse.
    existing_user = (
        db.query(User).filter(User.email == normalized_email).first()
    )
    if existing_user is not None:
        already_member = (
            db.query(WorkspaceMember)
            .filter(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == existing_user.id,
            )
            .first()
        )
        if already_member is not None:
            raise InvitationError(
                f"{normalized_email} is already a member of this workspace."
            )

    # Cancel any prior PENDING invitation for the same email+workspace; one at
    # a time keeps the inbox clean.
    prior = (
        db.query(WorkspaceInvitation)
        .filter(
            WorkspaceInvitation.workspace_id == workspace.id,
            WorkspaceInvitation.email == normalized_email,
            WorkspaceInvitation.status == InvitationStatus.PENDING,
        )
        .first()
    )
    if prior is not None:
        prior.status = InvitationStatus.REVOKED

    plaintext = secrets.token_urlsafe(32)
    invitation = WorkspaceInvitation(
        workspace_id=workspace.id,
        email=normalized_email,
        role=role,
        status=InvitationStatus.PENDING,
        token_hash=_hash_token(plaintext),
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS),
        invited_by=inviter.id,
    )
    db.add(invitation)
    db.flush()

    # Email the link. SMTP-not-configured = drop+log via send_email's fallback;
    # we still persist the invitation so a manually-shared link works.
    accept_url = _build_accept_url(plaintext)
    draft = EmailMessageDraft(
        subject=f"You're invited to {workspace.name} on AdVanta AI",
        text_body=(
            f"{inviter.full_name or inviter.email} invited you to join "
            f"{workspace.name} as {role.value}.\n\n"
            f"Accept: {accept_url}\n\n"
            f"This link expires in {INVITE_TTL_DAYS} days."
        ),
        html_body=(
            f"<p><strong>{inviter.full_name or inviter.email}</strong> invited "
            f"you to join <strong>{workspace.name}</strong> as "
            f"<strong>{role.value}</strong>.</p>"
            f"<p><a href=\"{accept_url}\">Accept invitation</a></p>"
            f"<p style=\"color:#94A3B8;font-size:12px;\">"
            f"This link expires in {INVITE_TTL_DAYS} days.</p>"
        ),
    )
    send_email(to=normalized_email, draft=draft)

    audit_service.log_event(
        db,
        workspace_id=workspace.id,
        actor_type=AuditActorType.USER,
        actor_id=inviter.id,
        action="workspace_invitation.created",
        resource_type="workspace_invitation",
        resource_id=invitation.id,
        metadata={"invitee_email": normalized_email, "role": role.value},
        request=request,
    )

    db.commit()
    db.refresh(invitation)
    return invitation, plaintext


def list_pending(db: Session, *, workspace_id: UUID) -> list[WorkspaceInvitation]:
    now = datetime.now(timezone.utc)
    rows = (
        db.query(WorkspaceInvitation)
        .filter(
            WorkspaceInvitation.workspace_id == workspace_id,
            WorkspaceInvitation.status == InvitationStatus.PENDING,
        )
        .all()
    )
    # Auto-expire stale rows.
    out: list[WorkspaceInvitation] = []
    for row in rows:
        if row.expires_at < now:
            row.status = InvitationStatus.EXPIRED
        else:
            out.append(row)
    if rows:
        db.commit()
    return out


def revoke_invitation(
    db: Session,
    *,
    workspace_id: UUID,
    invitation_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    request: Request | None = None,
) -> WorkspaceInvitation:
    require_role_at_least(actor_role, Role.ADMIN)
    row = (
        db.query(WorkspaceInvitation)
        .filter(
            WorkspaceInvitation.id == invitation_id,
            WorkspaceInvitation.workspace_id == workspace_id,
        )
        .first()
    )
    if row is None:
        raise InvitationError("Invitation not found.")
    if row.status != InvitationStatus.PENDING:
        raise InvitationError(
            f"Invitation is in `{row.status.value}` state."
        )
    row.status = InvitationStatus.REVOKED
    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="workspace_invitation.revoked",
        resource_type="workspace_invitation",
        resource_id=row.id,
        metadata={"email": row.email},
        request=request,
    )
    db.commit()
    db.refresh(row)
    return row


def accept_invitation(
    db: Session,
    *,
    token: str,
    accepting_user: User,
    request: Request | None = None,
) -> WorkspaceMember:
    """Look up by hashed token, verify status + expiry, and create the
    WorkspaceMember row. The caller is whoever currently holds an auth
    session; we don't tie acceptance to the email field on the invitation
    so that users with multiple email addresses can still join."""

    if not token or not token.strip():
        raise InvitationError("Provide an invitation token.")
    row = (
        db.query(WorkspaceInvitation)
        .filter(WorkspaceInvitation.token_hash == _hash_token(token.strip()))
        .first()
    )
    if row is None:
        raise InvitationError("Invitation not found or already used.")
    now = datetime.now(timezone.utc)
    if row.status == InvitationStatus.ACCEPTED:
        raise InvitationError("This invitation was already accepted.")
    if row.status in (InvitationStatus.REVOKED, InvitationStatus.EXPIRED):
        raise InvitationError("This invitation is no longer valid.")
    if row.expires_at < now:
        row.status = InvitationStatus.EXPIRED
        db.commit()
        raise InvitationError("This invitation has expired.")

    # If the user already happens to be a member, just bump their role to
    # whatever the invitation specified (highest-of) and mark accepted.
    existing_member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == row.workspace_id,
            WorkspaceMember.user_id == accepting_user.id,
        )
        .first()
    )
    if existing_member is None:
        member = WorkspaceMember(
            workspace_id=row.workspace_id,
            user_id=accepting_user.id,
            role=row.role,
            status=MemberStatus.ACTIVE,
        )
        db.add(member)
    else:
        existing_member.status = MemberStatus.ACTIVE
        existing_member.role = row.role
        member = existing_member

    row.status = InvitationStatus.ACCEPTED
    row.accepted_by = accepting_user.id
    row.accepted_at = now

    audit_service.log_event(
        db,
        workspace_id=row.workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=accepting_user.id,
        action="workspace_invitation.accepted",
        resource_type="workspace_invitation",
        resource_id=row.id,
        metadata={"role": row.role.value},
        request=request,
    )

    db.commit()
    db.refresh(member)
    return member
