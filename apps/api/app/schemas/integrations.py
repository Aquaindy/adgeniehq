from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.connected_account import ConnectionStatus
from app.models.sync_log import SyncLogStatus


class SyncLogPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: SyncLogStatus
    started_at: datetime
    completed_at: datetime | None
    summary: dict | None
    error_message: str | None
    created_at: datetime


class IntegrationStatus(BaseModel):
    """Per-provider status block for the Integrations Center."""

    provider: str
    display_name: str
    description: str
    configured: bool  # whether the OAuth app credentials are set in env
    status: ConnectionStatus
    provider_account_id: str | None
    display_account_name: str | None
    scopes: list[str] | None
    connected_at: datetime | None
    last_sync_at: datetime | None
    last_error: str | None
    recent_syncs: list[SyncLogPublic] = []


class ConnectUrlResponse(BaseModel):
    authorization_url: str
    state: str
    redirect_uri: str
