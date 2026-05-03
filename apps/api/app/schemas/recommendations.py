from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.approval import ApprovalStatus
from app.models.audit_log import AuditActorType
from app.models.recommendation import RecommendationStatus, RiskLevel
from app.schemas.agents import ExecutionPublic, RecommendationPublic


class ApprovalPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: ApprovalStatus
    approved_by: UUID | None
    approved_at: datetime | None
    rejected_by: UUID | None
    rejected_at: datetime | None
    execution_result: dict | None


class RecommendationDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    agent_run_id: UUID
    title: str
    summary: str
    recommendation_type: str
    risk_level: RiskLevel
    expected_impact: str
    suggested_action: str
    status: RecommendationStatus
    platform: str | None
    metadata: dict | None
    created_at: datetime
    approval: ApprovalPublic | None


class RecommendationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    summary: str | None = Field(default=None, min_length=1, max_length=4000)
    expected_impact: str | None = Field(default=None, min_length=1, max_length=4000)
    suggested_action: str | None = Field(default=None, min_length=1, max_length=4000)


class RejectRecommendationRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class ApproveRecommendationRequest(BaseModel):
    auto_execute: bool = True


class ApproveRecommendationResponse(BaseModel):
    recommendation: RecommendationPublic
    execution: ExecutionPublic | None = None


class AuditLogPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    actor_type: AuditActorType
    actor_id: UUID | None
    action: str
    resource_type: str
    resource_id: UUID | None
    metadata: dict | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
