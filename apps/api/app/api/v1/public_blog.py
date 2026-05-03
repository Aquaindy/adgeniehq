"""Public blog reader.

Two unauthenticated endpoints powering the marketing site:

  GET /public/blog            → list of published posts (newest first)
  GET /public/blog/{slug}     → single post detail

Source of truth: ContentDraft rows where
  type=blog_post AND status=published AND workspace.slug == settings.marketing_workspace_slug.

When `MARKETING_WORKSPACE_SLUG` is unset, both endpoints return an empty
result — never an error and never fabricated content. That keeps us aligned
with CLAUDE.md §1 ("honest empty states").

Customer workspaces using AdVanta to draft + publish to their own CMS
continue to publish via the workspace.publish_webhook_url flow. The two paths
are independent: this endpoint only serves AdVanta's own marketing blog.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AdVantaError
from app.db.session import get_db
from app.models.content_draft import (
    ContentDraft,
    ContentDraftStatus,
    ContentDraftType,
)
from app.models.workspace import Workspace

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PublicBlogPostSummary(BaseModel):
    """Card-shaped projection used by the archive listing — strips body."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    title: str
    excerpt: str | None
    image_url: str | None
    keywords: list[str] | None
    published_at: datetime | None


class PublicBlogPost(PublicBlogPostSummary):
    """Full post payload for the detail page. Body is the raw markdown the
    editor saved; the frontend handles rendering."""

    body: str
    seo_metadata: dict | None


class BlogPostNotFoundError(AdVantaError):
    status_code = 404
    code = "blog_post_not_found"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _marketing_workspace(db: Session) -> Workspace | None:
    """Resolve the configured marketing workspace by slug. Returns None when
    unset or missing — both endpoints treat this as 'no posts to show'."""
    slug = (settings.marketing_workspace_slug or "").strip().lower()
    if not slug:
        return None
    return db.query(Workspace).filter(Workspace.slug == slug).first()


def _published_blog_posts_query(db: Session, *, workspace_id: UUID):
    """Single source of truth for which rows are publicly visible. Type +
    status + slug-not-null + workspace are all enforced together."""
    return (
        db.query(ContentDraft)
        .filter(
            ContentDraft.workspace_id == workspace_id,
            ContentDraft.type == ContentDraftType.BLOG_POST,
            ContentDraft.status == ContentDraftStatus.PUBLISHED,
            ContentDraft.slug.is_not(None),
        )
        .order_by(ContentDraft.published_at.desc().nulls_last())
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/blog", response_model=list[PublicBlogPostSummary])
def list_blog_posts(
    limit: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[PublicBlogPostSummary]:
    workspace = _marketing_workspace(db)
    if workspace is None:
        return []
    rows = _published_blog_posts_query(db, workspace_id=workspace.id).limit(limit).all()
    return [PublicBlogPostSummary.model_validate(r) for r in rows]


@router.get("/blog/{slug}", response_model=PublicBlogPost)
def get_blog_post(
    slug: str,
    db: Session = Depends(get_db),
) -> PublicBlogPost:
    workspace = _marketing_workspace(db)
    if workspace is None:
        raise BlogPostNotFoundError("Blog post not found.")
    row = (
        _published_blog_posts_query(db, workspace_id=workspace.id)
        .filter(ContentDraft.slug == slug)
        .first()
    )
    if row is None:
        raise BlogPostNotFoundError("Blog post not found.")
    return PublicBlogPost.model_validate(row)
