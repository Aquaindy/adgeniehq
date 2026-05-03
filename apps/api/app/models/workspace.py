from uuid import UUID, uuid4

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Workspace(Base, TimestampMixin):
    __tablename__ = "workspaces"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    # CMS publish hook — when set, approved content drafts can be POSTed to
    # this URL on `Publish`. The receiver implements the contract documented
    # at /api/v1/workspaces/{id}/content-drafts/{id}/publish (see schema).
    # The secret travels in the Authorization: Bearer header so it never
    # appears in URL logs. Stored encrypted at rest with the same Fernet key
    # we use for OAuth tokens.
    publish_webhook_url: Mapped[str | None] = mapped_column(String(1024))
    encrypted_publish_webhook_secret: Mapped[str | None] = mapped_column(Text)

    members = relationship(
        "WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Workspace id={self.id} slug={self.slug}>"
