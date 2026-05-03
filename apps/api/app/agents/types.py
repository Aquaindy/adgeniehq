from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.agent_task import AgentTaskStatus
from app.models.recommendation import RiskLevel


@dataclass
class AgentContext:
    db: Session
    workspace_id: UUID
    input_payload: dict[str, Any]
    # The user that triggered the run. Plumbed through so agents that delegate
    # (e.g. MasterOrchestrator) can attribute sub-runs without race-prone
    # "most-recent run" lookups.
    triggered_by_user_id: UUID | None = None


@dataclass
class TaskRecord:
    skill_name: str
    status: AgentTaskStatus
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class SkillOutputRecord:
    skill_name: str
    output_type: str
    payload: dict[str, Any]
    task_index: int | None = None  # which task this output belongs to


@dataclass
class RecommendationRecord:
    title: str
    summary: str
    recommendation_type: str
    risk_level: RiskLevel
    expected_impact: str
    suggested_action: str
    platform: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class AgentResult:
    output_payload: dict[str, Any] = field(default_factory=dict)
    tasks: list[TaskRecord] = field(default_factory=list)
    skill_outputs: list[SkillOutputRecord] = field(default_factory=list)
    recommendations: list[RecommendationRecord] = field(default_factory=list)
