from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ContentDraftType(StrEnum):
    BLOG_POST = "blog_post"
    LANDING_PAGE = "landing_page"
    AD_COPY = "ad_copy"
    META_DESCRIPTION = "meta_description"
    EMAIL = "email"
    SOCIAL_POST = "social_post"


class ContentDraftStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ContentDraft(Base, TimestampMixin):
    """An LLM- or human-authored piece of content awaiting review.

    Production rule: drafts are never auto-published. They land in `draft`
    status; an Admin must approve, after which a publisher hook (manual or
    integration-backed) flips them to `published`."""

    __tablename__ = "content_drafts"
    __table_args__ = (
        # Slug must be unique per workspace, but only when set — most
        # non-blog drafts (ad copy, landing pages, etc.) won't have one.
        # Mirrored in alembic migration e5f6a7b8c9d0 so production matches.
        Index(
            "uq_content_drafts_workspace_slug",
            "workspace_id",
            "slug",
            unique=True,
            postgresql_where=text("slug IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_run_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        index=True,
    )

    type: Mapped[ContentDraftType] = mapped_column(
        Enum(ContentDraftType, name="content_draft_type"),
        nullable=False,
        index=True,
    )
    status: Mapped[ContentDraftStatus] = mapped_column(
        Enum(ContentDraftStatus, name="content_draft_status"),
        nullable=False,
        default=ContentDraftStatus.DRAFT,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    target_url: Mapped[str | None] = mapped_column(String(1024))
    # URL slug for public-blog publishing. Unique per workspace via a partial
    # index (only enforced when slug IS NOT NULL); set on publish if blank.
    slug: Mapped[str | None] = mapped_column(String(255))
    # Short summary for cards / OG / RSS. Auto-derived from body on publish
    # when blank.
    excerpt: Mapped[str | None] = mapped_column(Text)
    # Optional hero image URL (DALL-E or hand-uploaded). Populated by the
    # ContentWriter agent when image generation is enabled.
    image_url: Mapped[str | None] = mapped_column(String(2048))

    keywords: Mapped[list | None] = mapped_column(JSONB)  # ["pricing", "launch"]
    seo_metadata: Mapped[dict | None] = mapped_column(JSONB)  # {meta_title, meta_description, ...}
    notes: Mapped[str | None] = mapped_column(Text)

    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="agent"
    )  # "agent" | "manual"
    model_used: Mapped[str | None] = mapped_column(String(64))

    created_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ContentDraft id={self.id} type={self.type} status={self.status}>"
