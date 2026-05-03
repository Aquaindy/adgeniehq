from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class ProspectStatus(StrEnum):
    NEW = "new"
    QUEUED = "queued"
    CONTACTED = "contacted"
    REPLIED = "replied"
    WON = "won"
    DECLINED = "declined"
    BOUNCED = "bounced"
    ARCHIVED = "archived"


class BacklinkProspect(Base, TimestampMixin):
    """A potential link partner — a domain we'd like a backlink from."""

    __tablename__ = "backlink_prospects"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "domain", name="uq_backlink_prospects_workspace_domain"
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    page_url: Mapped[str | None] = mapped_column(String(1024))
    contact_name: Mapped[str | None] = mapped_column(String(255))
    contact_email: Mapped[str | None] = mapped_column(String(320), index=True)
    contact_role: Mapped[str | None] = mapped_column(String(120))
    relevance_score: Mapped[int | None] = mapped_column(Integer)
    domain_authority: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[ProspectStatus] = mapped_column(
        Enum(ProspectStatus, name="backlink_prospect_status"),
        nullable=False,
        default=ProspectStatus.NEW,
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB)

    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    won_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    backlink_url: Mapped[str | None] = mapped_column(String(1024))

    created_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    emails = relationship(
        "OutreachEmail",
        back_populates="prospect",
        cascade="all, delete-orphan",
        order_by="OutreachEmail.created_at",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BacklinkProspect id={self.id} domain={self.domain} status={self.status}>"
