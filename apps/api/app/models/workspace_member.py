from uuid import UUID, uuid4

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.security.permissions import MemberStatus, Role


class WorkspaceMember(Base, TimestampMixin):
    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_workspace_user"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="workspace_member_role"), nullable=False
    )
    status: Mapped[MemberStatus] = mapped_column(
        Enum(MemberStatus, name="workspace_member_status"),
        nullable=False,
        default=MemberStatus.ACTIVE,
    )

    workspace = relationship("Workspace", back_populates="members")
    user = relationship("User", back_populates="memberships")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<WorkspaceMember workspace={self.workspace_id} user={self.user_id} role={self.role}>"
