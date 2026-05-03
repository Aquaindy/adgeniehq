from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class AdminWorkspaceRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    created_at: datetime
    member_count: int
    plan_code: str
    subscription_status: str


class AdminUserRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_superuser: bool
    workspace_count: int
    created_at: datetime


class AdminOverview(BaseModel):
    users_total: int
    superusers_total: int
    workspaces_total: int
    paid_workspaces_total: int
    agent_runs_total: int
    agent_runs_last_7d: int
    recommendations_open: int
    integrations_connected: int
    landing_pages_total: int
    reports_generated_last_7d: int
    # Phase A-D + ops surface
    executions_total: int = 0
    executions_succeeded_last_7d: int = 0
    content_drafts_total: int = 0
    content_drafts_published_last_7d: int = 0
    outreach_emails_sent_last_7d: int = 0
    outreach_prospects_total: int = 0
    ab_tests_active: int = 0
    ab_tests_completed_last_7d: int = 0
