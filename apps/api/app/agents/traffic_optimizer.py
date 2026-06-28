"""Traffic Optimizer agent — AI next best action (Phase 6).

Reads the workspace's REAL traffic rollup (from traffic_analytics_service), then:
  * surfaces prioritized next-best-actions (scale / fix-or-pause / improve),
  * writes an executive narrative (LLM, deterministic fallback),
  * emits the high/medium actions as Recommendations so they flow into the
    Recommendations Center with the rest of the approval workflow.

All inputs are real numbers the operator logged or imported — the agent never
invents performance data; with no data it returns a clean empty state.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

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

_PRIORITY_RISK = {"high": RiskLevel.HIGH, "medium": RiskLevel.MEDIUM, "low": RiskLevel.LOW}


class TrafficOptimizerAgent(BaseAgent):
    type = "traffic_optimizer"
    title = "Traffic optimizer"
    description = (
        "Analyzes your real traffic performance across sources — profitability, "
        "ROAS and quality — and recommends the next best actions (scale, fix, "
        "pause, improve)."
    )

    def run(self, ctx: AgentContext) -> AgentResult:
        from app.services import traffic_analytics_service as analytics  # deferred (import cycle)

        result = AgentResult()
        started = datetime.now(timezone.utc)

        overview = analytics.compute_overview(ctx.db, workspace_id=ctx.workspace_id)
        if not overview.get("has_data"):
            return self._no_data(result, started)

        actions = analytics.next_best_actions(overview)
        report = {
            "generated_at": started.isoformat(),
            "totals": overview["totals"],
            "by_type": overview["by_type"],
            "top_sources": overview["sources"][:8],
            "top_campaigns": overview["campaigns"][:8],
            "next_best_actions": actions,
        }
        report["executive_summary"] = self._llm_summary(ctx, overview, actions) or self._fallback_summary(overview)

        self._emit_recommendations(result, actions)

        result.tasks.append(
            TaskRecord(
                skill_name="traffic.optimize",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={"sources": len(overview["sources"])},
                output_payload={"actions": len(actions)},
                started_at=started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="traffic.optimize",
                output_type="traffic_optimization",
                payload=report,
                task_index=1,
            )
        )
        result.output_payload = report
        return result

    # ------------------------------------------------------------------

    def _emit_recommendations(self, result: AgentResult, actions: list[dict]) -> None:
        for a in actions:
            if a["priority"] == "low":
                continue
            result.recommendations.append(
                RecommendationRecord(
                    title=a["title"],
                    summary=a["detail"],
                    recommendation_type=f"traffic.{a['type']}",
                    risk_level=_PRIORITY_RISK.get(a["priority"], RiskLevel.LOW),
                    expected_impact="Improve traffic profitability by reallocating toward what works.",
                    suggested_action=a["detail"],
                    platform="traffic",
                    metadata={"source": a["source"], "priority": a["priority"]},
                )
            )

    def _llm_summary(self, ctx: AgentContext, overview: dict, actions: list[dict]) -> str | None:
        from app.llm.client import LlmMessage, get_llm_client_for_workspace

        compact = {
            "totals": {k: overview["totals"].get(k) for k in ("cost_cents", "revenue_cents", "profit_cents", "roas", "leads", "sales")},
            "sources": [
                {"name": s["source_name"], "roas": s.get("roas"), "profit_cents": s.get("profit_cents"), "quality": s.get("quality_score")}
                for s in overview["sources"][:6]
            ],
            "actions": [a["title"] for a in actions[:5]],
        }
        system = (
            "You are a growth analyst. Given REAL aggregate traffic performance, write a 3-5 sentence "
            "executive summary: which sources make money, which lose money, and what to do next. "
            "Return PLAIN TEXT only (no JSON, no markdown headers). Ground every claim in the numbers; "
            "do not invent metrics."
        )
        user = "Performance JSON:\n" + json.dumps(compact)
        try:
            client = get_llm_client_for_workspace(ctx.db, ctx.workspace_id)
            completion = client.complete_metered(
                db=ctx.db, workspace_id=ctx.workspace_id,
                messages=[LlmMessage(role="system", content=system), LlmMessage(role="user", content=user)],
                max_tokens=500, temperature=0.4, purpose="traffic_optimizer",
            )
            text = (completion.text or "").strip()
            return text or None
        except Exception as exc:  # noqa: BLE001 — any LLM/budget failure → deterministic summary
            from app.core.logging import get_logger

            get_logger(__name__).info("traffic_optimizer.llm_fallback", error=str(exc))
            return None

    def _fallback_summary(self, overview: dict) -> str:
        t = overview["totals"]
        roas = t.get("roas")
        profit = t.get("profit_cents") or 0
        best = overview["sources"][0] if overview["sources"] else None
        parts = [
            f"Across your tracked sources you've spent {_usd(t.get('cost_cents') or 0)} and made "
            f"{_usd(t.get('revenue_cents') or 0)} ({'+' if profit >= 0 else ''}{_usd(profit)} profit"
            f"{f', {roas:.1f}x ROAS' if roas is not None else ''})."
        ]
        if best:
            parts.append(f"{best['source_name']} is your top source by profit.")
        parts.append("See the next best actions below for where to scale, fix or pause.")
        return " ".join(parts)

    def _no_data(self, result: AgentResult, started: datetime) -> AgentResult:
        result.tasks.append(
            TaskRecord(
                skill_name="traffic.optimize",
                status=AgentTaskStatus.SKIPPED,
                input_payload={},
                error_message="No traffic results logged yet.",
                started_at=started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.recommendations.append(
            RecommendationRecord(
                title="Log traffic results to unlock optimization",
                summary="The optimizer compares your real source performance. Log results (or run solo-ad orders) so there's data to analyze.",
                recommendation_type="traffic.no_data",
                risk_level=RiskLevel.LOW,
                expected_impact="Unlocks source comparison, quality scoring and next-best-actions.",
                suggested_action="Traffic Genie → Dashboard → Log results, or record a Solo Ads order.",
                platform="traffic",
            )
        )
        result.output_payload = {"has_data": False, "reason": "no_traffic_results"}
        return result


def _usd(cents: int) -> str:
    return f"${cents/100:,.0f}"
