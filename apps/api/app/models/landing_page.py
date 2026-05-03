from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class LandingPageSource(StrEnum):
    MANUAL = "manual"
    ONBOARDING = "onboarding"


class LandingPage(Base, TimestampMixin):
    """A specific URL the workspace cares about converting visitors on.

    `last_audit_summary` caches the computed scores + per-skill findings of the
    most recent audit so the dashboard can render without replaying the agent
    run."""

    __tablename__ = "landing_pages"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "url", name="uq_landing_pages_workspace_url"
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[LandingPageSource] = mapped_column(
        Enum(LandingPageSource, name="landing_page_source"),
        nullable=False,
        default=LandingPageSource.MANUAL,
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    last_audited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_audit_summary: Mapped[dict | None] = mapped_column(JSONB)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LandingPage {self.url} workspace={self.workspace_id}>"
