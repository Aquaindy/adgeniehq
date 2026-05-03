from uuid import UUID, uuid4

from slugify import slugify
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.permissions import MemberStatus, Role


class WorkspaceConflictError(AdVantaError):
    status_code = 409
    code = "workspace_conflict"


def _candidate_slug(name: str, *, suffix: str | None = None) -> str:
    base = slugify(name, max_length=48) or "workspace"
    return f"{base}-{suffix}" if suffix else base


def create_workspace_for_user(db: Session, *, owner: User, name: str) -> Workspace:
    """Create a workspace and make `owner` the Owner member, retrying slug on conflict."""
    for attempt in range(5):
        slug = _candidate_slug(name, suffix=uuid4().hex[:6] if attempt else None)
        workspace = Workspace(name=name.strip(), slug=slug)
        db.add(workspace)
        try:
            db.flush()
            break
        except IntegrityError:
            db.rollback()
    else:
        raise WorkspaceConflictError("Could not allocate a unique workspace slug.")

    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=owner.id,
        role=Role.OWNER,
        status=MemberStatus.ACTIVE,
    )
    db.add(member)
    db.commit()
    db.refresh(workspace)
    return workspace


def list_workspaces_for_user(
    db: Session, *, user: User
) -> list[tuple[Workspace, WorkspaceMember]]:
    rows = (
        db.query(Workspace, WorkspaceMember)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .filter(
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.status == MemberStatus.ACTIVE,
        )
        .order_by(Workspace.created_at.asc())
        .all()
    )
    return [(workspace, member) for workspace, member in rows]


def get_workspace(db: Session, workspace_id: UUID) -> Workspace | None:
    return db.get(Workspace, workspace_id)


def list_members(db: Session, workspace_id: UUID) -> list[tuple[WorkspaceMember, User]]:
    return (
        db.query(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .filter(WorkspaceMember.workspace_id == workspace_id)
        .order_by(WorkspaceMember.created_at.asc())
        .all()
    )


def update_member(
    db: Session,
    *,
    member: WorkspaceMember,
    role: Role | None = None,
    status: MemberStatus | None = None,
) -> WorkspaceMember:
    if role is not None:
        member.role = role
    if status is not None:
        member.status = status
    db.commit()
    db.refresh(member)
    return member
