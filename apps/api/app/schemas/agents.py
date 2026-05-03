from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.agent_run import AgentRunStatus
from app.models.agent_task import AgentTaskStatus
from app.models.approval import ApprovalStatus
from app.models.recommendation import RecommendationStatus, RiskLevel
from app.models.recommendation_execution import ExecutionStatus


class AgentCatalogEntry(BaseModel):
    type: str
    title: str
    description: str
    last_run: "AgentRunSummary | None" = None


class AgentRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_type: str
    status: AgentRunStatus
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None


class AgentRunRequest(BaseModel):
    agent_type: str
    input_payload: dict[str, Any] | None = None


class AgentTaskPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_index: int
    skill_name: str
    status: AgentTaskStatus
    input_payload: dict | None
    output_payload: dict | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None


class SkillOutputPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    skill_name: str
    output_type: str
    payload: dict
    created_at: datetime


class ApprovalSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: ApprovalStatus
    approved_by: UUID | None
    approved_at: datetime | None
    rejected_by: UUID | None
    rejected_at: datetime | None


class ExecutionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    recommendation_id: UUID
    provider: str
    action_type: str
    status: ExecutionStatus
    target_external_id: str | None
    target_external_account_id: str | None
    payload: dict | None
    prior_state: dict | None
    result: dict | None
    error_message: str | None
    is_revert: bool
    reverts_execution_id: UUID | None
    idempotency_key: str | None
    executed_by: UUID | None
    executed_at: datetime | None
    created_at: datetime


class RecommendationPublic(BaseModel):
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
    approval: ApprovalSnapshot | None = None
    executions: list[ExecutionPublic] = []
    has_executable_action: bool = False


class AgentRunDetail(AgentRunSummary):
    triggered_by_user_id: UUID | None
    input_payload: dict | None
    output_payload: dict | None
    model_used: str | None
    tasks: list[AgentTaskPublic]
    skill_outputs: list[SkillOutputPublic]
    recommendations: list[RecommendationPublic]


AgentCatalogEntry.model_rebuild()
