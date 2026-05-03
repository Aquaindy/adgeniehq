from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class SeoProject(Base, TimestampMixin):
    """One SEO project per workspace, tied to the site URL the user is optimizing."""

    __tablename__ = "seo_projects"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    site_url: Mapped[str | None] = mapped_column(String(2048))
    # Search Console-specific URL prefix (e.g. "sc-domain:example.com").
    search_console_site_url: Mapped[str | None] = mapped_column(String(2048))

    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_search_console_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    crawl_summary: Mapped[dict | None] = mapped_column(JSONB)

    keywords = relationship(
        "Keyword", back_populates="seo_project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SeoProject workspace={self.workspace_id} site={self.site_url}>"
