from uuid import UUID

from sqlalchemy.orm import Session

from app.agents.catalog import list_catalog
from app.models.agent_run import AgentRun
from app.models.agent_task import AgentTask
from app.models.recommendation import Recommendation
from app.models.skill_output import SkillOutput
from app.schemas.agents import (
    AgentCatalogEntry,
    AgentRunDetail,
    AgentRunSummary,
    AgentTaskPublic,
    ApprovalSnapshot,
    ExecutionPublic,
    RecommendationPublic,
    SkillOutputPublic,
)


def _has_executable_action(rec: Recommendation) -> bool:
    meta = rec.metadata_json or {}
    return bool(meta.get("action") and (meta.get("provider") or rec.platform))


def serialize_recommendation(rec: Recommendation) -> RecommendationPublic:
    approval = (
        ApprovalSnapshot.model_validate(rec.approval) if rec.approval is not None else None
    )
    executions = [ExecutionPublic.model_validate(e) for e in (rec.executions or [])]
    return RecommendationPublic(
        id=rec.id,
        workspace_id=rec.workspace_id,
        agent_run_id=rec.agent_run_id,
        title=rec.title,
        summary=rec.summary,
        recommendation_type=rec.recommendation_type,
        risk_level=rec.risk_level,
        expected_impact=rec.expected_impact,
        suggested_action=rec.suggested_action,
        status=rec.status,
        platform=rec.platform,
        metadata=rec.metadata_json,
        created_at=rec.created_at,
        approval=approval,
        executions=executions,
        has_executable_action=_has_executable_action(rec),
    )


def list_agents_with_last_run(
    db: Session, *, workspace_id: UUID
) -> list[AgentCatalogEntry]:
    entries = list_catalog()
    catalog: list[AgentCatalogEntry] = []
    for entry in entries:
        last_run = (
            db.query(AgentRun)
            .filter(
                AgentRun.workspace_id == workspace_id,
                AgentRun.agent_type == entry["type"],
            )
            .order_by(AgentRun.created_at.desc())
            .first()
        )
        catalog.append(
            AgentCatalogEntry(
                type=entry["type"],
                title=entry["title"],
                description=entry["description"],
                last_run=AgentRunSummary.model_validate(last_run) if last_run else None,
            )
        )
    return catalog


def list_runs(db: Session, *, workspace_id: UUID, limit: int = 50) -> list[AgentRunSummary]:
    runs = (
        db.query(AgentRun)
        .filter(AgentRun.workspace_id == workspace_id)
        .order_by(AgentRun.created_at.desc())
        .limit(limit)
        .all()
    )
    return [AgentRunSummary.model_validate(r) for r in runs]


def get_run_detail(
    db: Session, *, workspace_id: UUID, run_id: UUID
) -> AgentRunDetail | None:
    run = (
        db.query(AgentRun)
        .filter(AgentRun.id == run_id, AgentRun.workspace_id == workspace_id)
        .first()
    )
    if run is None:
        return None

    tasks = (
        db.query(AgentTask)
        .filter(AgentTask.agent_run_id == run.id)
        .order_by(AgentTask.task_index.asc())
        .all()
    )
    outputs = (
        db.query(SkillOutput)
        .filter(SkillOutput.agent_run_id == run.id)
        .order_by(SkillOutput.created_at.asc())
        .all()
    )
    recs = (
        db.query(Recommendation)
        .filter(Recommendation.agent_run_id == run.id)
        .order_by(Recommendation.created_at.asc())
        .all()
    )

    return AgentRunDetail(
        id=run.id,
        agent_type=run.agent_type,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error_message=run.error_message,
        triggered_by_user_id=run.triggered_by_user_id,
        input_payload=run.input_payload,
        output_payload=run.output_payload,
        model_used=run.model_used,
        tasks=[AgentTaskPublic.model_validate(t) for t in tasks],
        skill_outputs=[SkillOutputPublic.model_validate(o) for o in outputs],
        recommendations=[serialize_recommendation(r) for r in recs],
    )


def list_recent_tasks(
    db: Session, *, workspace_id: UUID, limit: int = 50
) -> list[AgentTaskPublic]:
    tasks = (
        db.query(AgentTask)
        .join(AgentRun, AgentRun.id == AgentTask.agent_run_id)
        .filter(AgentRun.workspace_id == workspace_id)
        .order_by(AgentTask.created_at.desc())
        .limit(limit)
        .all()
    )
    return [AgentTaskPublic.model_validate(t) for t in tasks]


def list_recommendations(
    db: Session, *, workspace_id: UUID, limit: int = 100
) -> list[RecommendationPublic]:
    rows = (
        db.query(Recommendation)
        .filter(Recommendation.workspace_id == workspace_id)
        .order_by(Recommendation.created_at.desc())
        .limit(limit)
        .all()
    )
    return [serialize_recommendation(r) for r in rows]
