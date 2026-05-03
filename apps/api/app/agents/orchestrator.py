"""Master Growth Orchestrator.

Accepts a high-level goal (string + optional structured inputs) and chains
specialized agents. Records each delegated agent's run id in skill_outputs so
the dashboard can drill in. The orchestrator never triggers external mutations
directly — it only coordinates and surfaces a unified plan.

Goal vocabulary (free-form, but recognized hints for routing):
- "audit"           → onboarding_insight + paid_ads + seo_audit + landing_page_audit
- "research"        → market_intelligence + icp_persona
- "improve_seo"     → seo_audit
- "improve_paid"    → paid_ads
- "improve_landing" → landing_page_audit
- "icp"             → icp_persona
- "competitors"     → market_intelligence

If the goal is unrecognized, runs the safe research subset
(market_intelligence + icp_persona + onboarding_insight).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.agents.base import BaseAgent
from app.agents.types import (
    AgentContext,
    AgentResult,
    RecommendationRecord,
    SkillOutputRecord,
    TaskRecord,
)
from app.models.agent_task import AgentTaskStatus
from app.models.recommendation import RiskLevel


_GOAL_PLAYBOOKS: dict[str, list[str]] = {
    "audit": [
        "onboarding_insight",
        "paid_ads",
        "seo_audit",
        "landing_page_audit",
    ],
    "research": ["market_intelligence", "icp_persona"],
    "improve_seo": ["seo_audit"],
    "improve_paid": ["paid_ads"],
    "improve_landing": ["landing_page_audit"],
    "icp": ["icp_persona"],
    "competitors": ["market_intelligence"],
}

# Default plan when the caller doesn't specify a recognized goal.
_DEFAULT_PLAN = ["market_intelligence", "icp_persona", "onboarding_insight"]


class MasterOrchestratorAgent(BaseAgent):
    type = "master_orchestrator"
    title = "Master Growth Orchestrator"
    description = (
        "Accepts a high-level goal, picks specialized agents, runs them in "
        "sequence, and produces a unified summary."
    )

    def run(self, ctx: AgentContext) -> AgentResult:
        result = AgentResult()
        started = datetime.now(timezone.utc)

        goal = str(ctx.input_payload.get("goal") or "").strip().lower()
        explicit_plan = ctx.input_payload.get("agents")

        if isinstance(explicit_plan, list) and explicit_plan:
            plan = [str(a) for a in explicit_plan if isinstance(a, str)]
            plan_source = "explicit"
        elif goal in _GOAL_PLAYBOOKS:
            plan = list(_GOAL_PLAYBOOKS[goal])
            plan_source = f"goal:{goal}"
        else:
            plan = list(_DEFAULT_PLAN)
            plan_source = "default"

        # Drop self-references so the orchestrator can't recurse.
        plan = [a for a in plan if a != self.type]

        plan_payload = {"goal": goal or None, "plan": plan, "plan_source": plan_source}
        result.tasks.append(
            TaskRecord(
                skill_name="orchestrator.plan",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={"goal": goal, "explicit_plan": explicit_plan},
                output_payload=plan_payload,
                started_at=started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="orchestrator.plan",
                output_type="execution_plan",
                payload=plan_payload,
                task_index=1,
            )
        )

        # Run each agent in the plan. We do these inline (not via the runner)
        # because the runner persists a *new* AgentRun per call, and we want
        # every sub-run linked back to the orchestrator's run_id via the
        # skill_outputs table — done below. To keep token + plan-limit
        # accounting honest, we still call run_agent from the runtime so
        # billing meters tick correctly.
        sub_runs: list[dict[str, Any]] = []
        unique_recs: list[RecommendationRecord] = []
        seen_rec_titles: set[str] = set()

        # Local import to avoid circular import at module load (runtime imports
        # the catalog which now imports this orchestrator).
        from app.agents.runtime import run_agent

        # Plumbed straight through from AgentContext — no more "most-recent
        # AgentRun" stand-in (which had a race window with concurrent
        # background runs).
        delegate_user_id = ctx.triggered_by_user_id
        if delegate_user_id is None:
            raise RuntimeError(
                "Orchestrator requires triggered_by_user_id on AgentContext."
            )

        for idx, agent_type in enumerate(plan, start=2):
            sub_started = datetime.now(timezone.utc)
            try:
                sub_run = run_agent(
                    ctx.db,
                    workspace_id=ctx.workspace_id,
                    agent_type=agent_type,
                    triggered_by_user_id=delegate_user_id,
                    input_payload=ctx.input_payload,
                )
            except Exception as exc:  # noqa: BLE001 — record + continue
                result.tasks.append(
                    TaskRecord(
                        skill_name=f"orchestrator.delegate.{agent_type}",
                        status=AgentTaskStatus.FAILED,
                        input_payload={"agent_type": agent_type},
                        output_payload=None,
                        error_message=str(exc),
                        started_at=sub_started,
                        completed_at=datetime.now(timezone.utc),
                    )
                )
                continue

            sub_completed = datetime.now(timezone.utc)
            sub_runs.append(
                {
                    "agent_type": agent_type,
                    "run_id": str(sub_run.id),
                    "status": sub_run.status.value
                    if hasattr(sub_run.status, "value")
                    else str(sub_run.status),
                }
            )
            result.tasks.append(
                TaskRecord(
                    skill_name=f"orchestrator.delegate.{agent_type}",
                    status=AgentTaskStatus.SUCCEEDED,
                    input_payload={"agent_type": agent_type},
                    output_payload={"sub_run_id": str(sub_run.id)},
                    started_at=sub_started,
                    completed_at=sub_completed,
                )
            )
            result.skill_outputs.append(
                SkillOutputRecord(
                    skill_name=f"orchestrator.delegate.{agent_type}",
                    output_type="sub_run_reference",
                    payload={
                        "agent_type": agent_type,
                        "sub_run_id": str(sub_run.id),
                        "sub_run_status": sub_run.status.value
                        if hasattr(sub_run.status, "value")
                        else str(sub_run.status),
                    },
                    task_index=idx,
                )
            )

        # Emit one summary recommendation pointing the user at the new sub-runs.
        if sub_runs:
            unique_recs.append(
                RecommendationRecord(
                    title=f"Review the orchestrator plan ({len(sub_runs)} sub-runs)",
                    summary=(
                        f"Goal `{goal or '—'}` produced {len(sub_runs)} sub-runs "
                        "across the agent system. Open each sub-run to review its "
                        "recommendations."
                    ),
                    recommendation_type="orchestrator.review_plan",
                    risk_level=RiskLevel.LOW,
                    expected_impact=(
                        "Coordinated review across paid, SEO, content, and ICP "
                        "decisions — fewer blind spots than a single-agent run."
                    ),
                    suggested_action="Open Agent Runs and review each sub-run.",
                    metadata={"sub_runs": sub_runs, "plan_source": plan_source},
                )
            )

        for rec in unique_recs:
            if rec.title in seen_rec_titles:
                continue
            seen_rec_titles.add(rec.title)
            result.recommendations.append(rec)

        result.output_payload = {
            "goal": goal or None,
            "plan_source": plan_source,
            "plan": plan,
            "sub_runs": sub_runs,
        }
        return result


