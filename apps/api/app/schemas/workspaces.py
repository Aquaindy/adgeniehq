from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.security.permissions import MemberStatus, Role


class WorkspacePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    created_at: datetime


class WorkspaceMembership(WorkspacePublic):
    role: Role
    status: MemberStatus


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)


class WorkspaceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)


class MemberPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    email: EmailStr
    full_name: str | None
    role: Role
    status: MemberStatus
    created_at: datetime


class MemberUpdateRequest(BaseModel):
    role: Role | None = None
    status: MemberStatus | None = None


# ---------------------------------------------------------------------------
# Publish-webhook settings
# ---------------------------------------------------------------------------


class PublishWebhookConfig(BaseModel):
    publish_webhook_url: str | None = None
    has_secret: bool = False


class PublishWebhookUpdate(BaseModel):
    # `None` clears the existing value; an empty string is treated as None.
    publish_webhook_url: str | None = Field(default=None, max_length=1024)
    publish_webhook_secret: str | None = Field(default=None, max_length=512)
