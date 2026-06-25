from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.autoresponder_sync import AutoresponderSyncStatus, SyncDirection
from app.models.connected_account import ConnectionStatus


# ---------------------------------------------------------------------------
# Provider catalog (drives the connect UI)
# ---------------------------------------------------------------------------


class ConfigFieldPublic(BaseModel):
    key: str
    label: str
    type: str
    required: bool
    placeholder: str | None = None
    help_text: str | None = None


class AutoresponderProviderInfo(BaseModel):
    provider: str
    display_name: str
    description: str
    requires_api_key: bool
    api_key_label: str
    api_key_help: str | None = None
    config_fields: list[ConfigFieldPublic]
    supports_audience_listing: bool
    supports_contact_pull: bool
    freeform_audience: bool
    docs_url: str | None = None


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------


class AutoresponderConnectionPublic(BaseModel):
    """Connection state. Never includes the encrypted API key."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: str
    display_name: str | None
    provider_account_id: str | None
    status: ConnectionStatus
    config: dict | None
    connected_at: datetime | None
    last_sync_at: datetime | None
    last_error: str | None


class ConnectAutoresponderRequest(BaseModel):
    api_key: str | None = None
    config: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Audiences
# ---------------------------------------------------------------------------


class AudiencePublic(BaseModel):
    external_id: str
    name: str
    member_count: int | None = None


class AudienceListResponse(BaseModel):
    provider: str
    supports_audience_listing: bool
    freeform_audience: bool
    audiences: list[AudiencePublic]


# ---------------------------------------------------------------------------
# Contact sync
# ---------------------------------------------------------------------------


class ContactInput(BaseModel):
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    tags: list[str] = Field(default_factory=list)
    custom_fields: dict = Field(default_factory=dict)


class PushContactsRequest(BaseModel):
    audience_id: str | None = None
    audience_name: str | None = None
    source: str = "manual"
    contacts: list[ContactInput] = Field(min_length=1, max_length=1000)


class PullContactsRequest(BaseModel):
    audience_id: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class ContactPublic(BaseModel):
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    tags: list[str] = Field(default_factory=list)


class ContactSyncPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    direction: SyncDirection
    status: AutoresponderSyncStatus
    audience_external_id: str | None
    audience_name: str | None
    source: str | None
    requested_count: int
    succeeded_count: int
    failed_count: int
    summary: dict | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class PullContactsResponse(BaseModel):
    sync: ContactSyncPublic
    contacts: list[ContactPublic]
