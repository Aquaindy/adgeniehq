"""Synchronous agent runner. Persists run + tasks + skill outputs + recommendations
in a single transaction. M4 runs agents inline; queueing onto Celery is a future
upgrade once the worker stack is wired up (per spec milestone backlog)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.agents.base import BaseAgent
from app.agents.catalog import get_agent
from app.agents.types import AgentContext, AgentResult, TaskRecord
from app.core.exceptions import AdVantaError
from app.core.logging import get_logger
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.agent_task import AgentTask
from app.models.approval import Approval, ApprovalStatus
from app.models.recommendation import Recommendation, RecommendationStatus
from app.models.skill_output import SkillOutput
from app.models.usage_event import UsageEventType
from app.services import billing_service

log = get_logger(__name__)


class UnknownAgentError(AdVantaError):
    status_code = 404
    code = "unknown_agent"


def run_agent(
    db: Session,
    *,
    workspace_id: UUID,
    agent_type: str,
    triggered_by_user_id: UUID,
    input_payload: dict[str, Any] | None = None,
) -> AgentRun:
    agent_cls = get_agent(agent_type)
    if agent_cls is None:
        raise UnknownAgentError(f"Unknown agent type: {agent_type}.")

    # Plan-limit gate. Raises 402 PlanLimitExceededError if the workspace is
    # already at or over its agent-runs/30-day quota.
    billing_service.assert_within_agent_run_limit(db, workspace_id=workspace_id)

    # Persist run as "running" so the dashboard can see it even if execution is slow.
    run = AgentRun(
        workspace_id=workspace_id,
        triggered_by_user_id=triggered_by_user_id,
        agent_type=agent_type,
        status=AgentRunStatus.RUNNING,
        input_payload=input_payload or {},
        started_at=datetime.now(timezone.utc),
        model_used="deterministic",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    ctx = AgentContext(
        db=db,
        workspace_id=workspace_id,
        input_payload=input_payload or {},
        triggered_by_user_id=triggered_by_user_id,
    )
    try:
        agent: BaseAgent = agent_cls()
        result: AgentResult = agent.run(ctx)
    except Exception as exc:
        log.exception("agent.run.failed", agent=agent_type, run_id=str(run.id))
        run.status = AgentRunStatus.FAILED
        run.completed_at = datetime.now(timezone.utc)
        run.error_code = exc.__class__.__name__
        run.error_message = str(exc)
        db.commit()
        db.refresh(run)
        return run

    _persist_result(db, run=run, result=result)
    run.status = AgentRunStatus.SUCCEEDED
    run.completed_at = datetime.now(timezone.utc)
    run.output_payload = result.output_payload

    # Meter the successful run for billing.
    billing_service.record_usage_event(
        db,
        workspace_id=workspace_id,
        event_type=UsageEventType.AGENT_RUN,
        metadata={"agent_type": agent_type, "run_id": str(run.id)},
    )

    db.commit()
    db.refresh(run)
    return run


def _persist_result(db: Session, *, run: AgentRun, result: AgentResult) -> None:
    task_id_by_index: dict[int, UUID] = {}

    for idx, task_record in enumerate(result.tasks, start=1):
        task = AgentTask(
            agent_run_id=run.id,
            task_index=idx,
            skill_name=task_record.skill_name,
            status=task_record.status,
            input_payload=task_record.input_payload,
            output_payload=task_record.output_payload,
            started_at=task_record.started_at,
            completed_at=task_record.completed_at,
            error_message=task_record.error_message,
        )
        db.add(task)
        db.flush()
        task_id_by_index[idx] = task.id

    for output in result.skill_outputs:
        agent_task_id = (
            task_id_by_index.get(output.task_index) if output.task_index is not None else None
        )
        db.add(
            SkillOutput(
                agent_run_id=run.id,
                agent_task_id=agent_task_id,
                skill_name=output.skill_name,
                output_type=output.output_type,
                payload=output.payload,
            )
        )

    for rec in result.recommendations:
        recommendation = Recommendation(
            workspace_id=run.workspace_id,
            agent_run_id=run.id,
            title=rec.title,
            summary=rec.summary,
            recommendation_type=rec.recommendation_type,
            risk_level=rec.risk_level,
            expected_impact=rec.expected_impact,
            suggested_action=rec.suggested_action,
            status=RecommendationStatus.OPEN,
            platform=rec.platform,
            metadata_json=rec.metadata,
        )
        db.add(recommendation)
        db.flush()  # populate recommendation.id

        db.add(
            Approval(
                workspace_id=run.workspace_id,
                recommendation_id=recommendation.id,
                action_type=rec.recommendation_type,
                risk_level=rec.risk_level,
                status=ApprovalStatus.PENDING,
            )
        )


# Re-exported for tests that want to construct minimal records
__all__ = ["run_agent", "UnknownAgentError", "TaskRecord"]
