from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.content_draft import ContentDraftStatus, ContentDraftType


class ContentDraftPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    agent_run_id: UUID | None
    type: ContentDraftType
    status: ContentDraftStatus
    title: str
    body: str
    target_url: str | None
    slug: str | None = None
    excerpt: str | None = None
    image_url: str | None = None
    platform: str | None = None
    keywords: list[str] | None
    hashtags: list[str] | None = None
    seo_metadata: dict | None
    notes: str | None
    source: str
    model_used: str | None
    created_by: UUID | None
    approved_by: UUID | None
    approved_at: datetime | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class GenerateContentDraftRequest(BaseModel):
    type: ContentDraftType
    topic: str = Field(min_length=2, max_length=512)
    keywords: list[str] = Field(default_factory=list)
    target_url: str | None = Field(default=None, max_length=1024)
    audience: str | None = Field(default=None, max_length=512)
    notes: str | None = Field(default=None, max_length=2000)


class CreateManualContentDraftRequest(BaseModel):
    type: ContentDraftType
    title: str = Field(min_length=1, max_length=512)
    body: str = Field(min_length=1)
    target_url: str | None = Field(default=None, max_length=1024)
    slug: str | None = Field(default=None, max_length=255)
    excerpt: str | None = Field(default=None, max_length=2000)
    image_url: str | None = Field(default=None, max_length=2048)
    keywords: list[str] = Field(default_factory=list)
    seo_metadata: dict | None = None
    notes: str | None = Field(default=None, max_length=2000)


class UpdateContentDraftRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    body: str | None = Field(default=None, min_length=1)
    target_url: str | None = Field(default=None, max_length=1024)
    slug: str | None = Field(default=None, max_length=255)
    excerpt: str | None = Field(default=None, max_length=2000)
    image_url: str | None = Field(default=None, max_length=2048)
    keywords: list[str] | None = None
    hashtags: list[str] | None = None
    seo_metadata: dict | None = None
    notes: str | None = Field(default=None, max_length=2000)


class RejectContentDraftRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class PublishContentDraftRequest(BaseModel):
    publication_url: str | None = Field(default=None, max_length=1024)


class RefreshContentDraftRequest(BaseModel):
    source_draft_id: UUID | None = None
    source_url: str | None = Field(default=None, max_length=1024)
    instructions: str | None = Field(default=None, max_length=2000)
