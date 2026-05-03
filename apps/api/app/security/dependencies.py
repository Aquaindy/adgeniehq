from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.db.session import get_db
from app.models.user import User
from app.models.workspace_member import WorkspaceMember
from app.security.permissions import (
    MemberStatus,
    PermissionDeniedError,
    Role,
    require_role_at_least,
)
from app.security.tokens import InvalidTokenError, decode_token


class NotAuthenticatedError(AdVantaError):
    status_code = 401
    code = "not_authenticated"


class WorkspaceNotFoundError(AdVantaError):
    status_code = 404
    code = "workspace_not_found"


async def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization:
        raise NotAuthenticatedError("Missing bearer token.")

    parts = authorization.split(None, 1)
    if len(parts) != 2:
        raise NotAuthenticatedError("Malformed Authorization header.")
    scheme, value = parts[0].lower(), parts[1].strip()

    if scheme == "apikey":
        # Programmatic access via API key. Stamps the request so `get_current_member`
        # can short-circuit the workspace + role lookup.
        from app.services import api_key_service

        key = api_key_service.verify_plaintext(db, plaintext=value)
        if key is None:
            raise NotAuthenticatedError("Invalid or revoked API key.")
        creator = db.get(User, key.created_by) if key.created_by else None
        if creator is None or not creator.is_active:
            raise NotAuthenticatedError("API-key creator is missing or inactive.")
        request.state.api_key_id = key.id
        request.state.api_key_workspace_id = key.workspace_id
        request.state.api_key_role = key.role
        return creator

    if scheme != "bearer":
        raise NotAuthenticatedError("Unsupported authorization scheme.")

    payload = decode_token(value, expected_type="access")
    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError("Invalid subject.") from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise NotAuthenticatedError("User not found or inactive.")

    # Superuser bypass for plan-limit checks. Only set for interactive
    # (bearer) sessions — API-key requests stay limited so a scoped key
    # the user issued for scripting can't accidentally bypass tenant caps.
    if user.is_superuser:
        from app.core.superuser_context import set_superuser_request

        set_superuser_request(True)

    return user


def get_current_member(
    request: Request,
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceMember:
    api_key_workspace_id = getattr(request.state, "api_key_workspace_id", None)
    if api_key_workspace_id is not None and api_key_workspace_id != workspace_id:
        # API key is workspace-scoped — refuse to act in a different workspace
        # even if the creating user happens to be a member there.
        raise WorkspaceNotFoundError(
            "API key is not authorized for this workspace."
        )

    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.status == MemberStatus.ACTIVE,
        )
        .first()
    )
    if member is None:
        raise WorkspaceNotFoundError("Workspace not found or you don't have access.")

    # When authenticating via API key, the effective role is whichever is more
    # restrictive of (member.role, key.role). This way an Owner who issues a
    # MARKETER-scoped key can't accidentally use it to perform owner-only ops.
    #
    # SAFETY: we MUST NOT mutate `member.role` while the row is still attached
    # to the SQLAlchemy session — `db.commit()` later in the request would
    # flush that change and permanently demote the workspace member. Instead,
    # we expunge the row first, then mutate the now-detached copy. The session
    # forgets about the row, so subsequent commits leave workspace_members.role
    # untouched. Consumers only read scalar attributes (role, user_id,
    # workspace_id), so detachment doesn't break them.
    api_key_role = getattr(request.state, "api_key_role", None)
    if api_key_role is not None:
        effective = _least_privileged(member.role, api_key_role)
        if effective != member.role:
            db.expunge(member)
            member.role = effective

    request.state.workspace_id = workspace_id
    request.state.role = member.role
    return member


def _least_privileged(*roles: Role) -> Role:
    from app.security.permissions import ROLE_RANK
    return min(roles, key=lambda r: ROLE_RANK[r])


def require_role(minimum: Role):
    """FastAPI dependency factory enforcing minimum role within the resolved workspace."""

    def _dep(member: WorkspaceMember = Depends(get_current_member)) -> WorkspaceMember:
        require_role_at_least(member.role, minimum)
        return member

    return _dep


def require_owner(member: WorkspaceMember = Depends(get_current_member)) -> WorkspaceMember:
    if member.role != Role.OWNER:
        raise PermissionDeniedError("Only the workspace owner can perform this action.")
    return member


def require_superuser(user: User = Depends(get_current_user)) -> User:
    """Gate for /admin endpoints — requires User.is_superuser."""
    if not user.is_superuser:
        raise PermissionDeniedError("Superuser access required.")
    return user
