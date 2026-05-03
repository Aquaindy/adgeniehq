"""Market Intelligence Agent — competitor + positioning analysis.

Reads the workspace's onboarding profile (offer, target audience, competitor
list) and produces a competitor matrix, positioning gaps, and ad-angle
recommendations. Works deterministically when no LLM is configured; uses LLM
to enrich the matrix when available.
"""

from __future__ import annotations

import json
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
from app.core.exceptions import AdVantaError
from app.llm.client import LlmError, LlmMessage, get_llm_client_for_workspace
from app.models.agent_task import AgentTaskStatus
from app.models.onboarding_profile import OnboardingProfile
from app.models.recommendation import RiskLevel


class MarketIntelligenceAgent(BaseAgent):
    type = "market_intelligence"
    title = "Market Intelligence"
    description = (
        "Builds a competitor matrix, surfaces positioning gaps, and proposes ad "
        "angles drawn from your onboarding profile."
    )

    def run(self, ctx: AgentContext) -> AgentResult:
        result = AgentResult()
        started = datetime.now(timezone.utc)

        profile = (
            ctx.db.query(OnboardingProfile)
            .filter(OnboardingProfile.workspace_id == ctx.workspace_id)
            .first()
        )
        if profile is None or not profile.completed_at:
            result.tasks.append(
                TaskRecord(
                    skill_name="market_intel.review",
                    status=AgentTaskStatus.SKIPPED,
                    input_payload={},
                    error_message="Onboarding has not been completed.",
                    started_at=started,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            result.recommendations.append(
                RecommendationRecord(
                    title="Complete onboarding to unlock market intelligence",
                    summary=(
                        "Market Intelligence needs your offer, audience, and competitor list "
                        "to build a useful matrix."
                    ),
                    recommendation_type="market_intel.onboarding_incomplete",
                    risk_level=RiskLevel.MEDIUM,
                    expected_impact="Unlocks competitor analysis and positioning gap discovery.",
                    suggested_action="Finish the onboarding wizard.",
                )
            )
            result.output_payload = {"skipped": True, "reason": "onboarding_incomplete"}
            return result

        competitors_raw: list[dict[str, Any]] = list(profile.competitors or [])
        competitor_count = len(competitors_raw)

        # ------------------------------------------------------------------
        # Skill 1 — competitor inventory
        # ------------------------------------------------------------------
        inv_payload = {
            "competitor_count": competitor_count,
            "competitors": [
                {"name": c.get("name") or "—", "url": c.get("url") or None}
                for c in competitors_raw[:20]
            ],
        }
        result.tasks.append(
            TaskRecord(
                skill_name="market_intel.inventory",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={},
                output_payload=inv_payload,
                started_at=started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="market_intel.inventory",
                output_type="competitor_inventory",
                payload=inv_payload,
                task_index=1,
            )
        )

        if competitor_count == 0:
            result.recommendations.append(
                RecommendationRecord(
                    title="Add competitors to onboarding",
                    summary=(
                        "No competitors are listed — Market Intelligence has nothing "
                        "to compare against."
                    ),
                    recommendation_type="market_intel.no_competitors",
                    risk_level=RiskLevel.LOW,
                    expected_impact="Enables competitor positioning and ad-angle research.",
                    suggested_action=(
                        "List 1–3 direct competitors with their URLs in onboarding."
                    ),
                )
            )

        # ------------------------------------------------------------------
        # Skill 2 — positioning matrix (LLM-enriched if available)
        # ------------------------------------------------------------------
        matrix_started = datetime.now(timezone.utc)
        matrix, matrix_source = _build_matrix(ctx, profile, competitors_raw)
        matrix_payload = {
            "source": matrix_source,
            "matrix": matrix,
        }
        result.tasks.append(
            TaskRecord(
                skill_name="market_intel.positioning_matrix",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={"competitor_count": competitor_count},
                output_payload={
                    "source": matrix_source,
                    "row_count": len(matrix.get("rows", [])),
                },
                started_at=matrix_started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="market_intel.positioning_matrix",
                output_type="positioning_matrix",
                payload=matrix_payload,
                task_index=2,
            )
        )

        # ------------------------------------------------------------------
        # Skill 3 — ad-angle recommendations
        # ------------------------------------------------------------------
        gaps = matrix.get("gaps") or []
        for gap in gaps[:5]:
            result.recommendations.append(
                RecommendationRecord(
                    title=f"Positioning gap: {gap.get('label', '—')[:80]}",
                    summary=gap.get("summary", ""),
                    recommendation_type="market_intel.positioning_gap",
                    risk_level=RiskLevel.LOW,
                    expected_impact=(
                        gap.get("expected_impact")
                        or "A differentiated angle that competitors aren't running."
                    ),
                    suggested_action=gap.get("suggested_action")
                    or "Test a new ad-set built around this angle.",
                    metadata={"angle": gap.get("label")},
                )
            )

        result.output_payload = {
            "competitor_count": competitor_count,
            "matrix_source": matrix_source,
            "gap_count": len(gaps),
        }
        return result


# -------------------------------------------------------------------------
# Matrix builders
# -------------------------------------------------------------------------


def _build_matrix(
    ctx: AgentContext,
    profile: OnboardingProfile,
    competitors: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    """Returns (matrix, source). Source is 'llm' or 'deterministic'."""
    llm = get_llm_client_for_workspace(ctx.db, ctx.workspace_id)
    if llm.is_configured() and competitors:
        try:
            return _matrix_via_llm(ctx, profile, competitors), "llm"
        except (LlmError, AdVantaError):
            pass
    return _matrix_deterministic(profile, competitors), "deterministic"


def _matrix_via_llm(
    ctx: AgentContext,
    profile: OnboardingProfile,
    competitors: list[dict[str, Any]],
) -> dict[str, Any]:
    llm = get_llm_client_for_workspace(ctx.db, ctx.workspace_id)
    competitor_lines = "\n".join(
        f"- {c.get('name') or '?'} ({c.get('url') or 'no url'})"
        for c in competitors[:10]
    )
    system = LlmMessage(
        role="system",
        content=(
            "You are a senior B2B growth strategist. Given a company's offer, "
            "audience, and competitor list, return a JSON object with: "
            "rows (array of competitors with positioning_summary, strengths, "
            "weaknesses), gaps (array of {label, summary, expected_impact, "
            "suggested_action}). Be concrete and avoid generic platitudes."
        ),
    )
    user = LlmMessage(
        role="user",
        content=(
            f"Company offer: {profile.offer_description or '—'}\n"
            f"Target audience: {profile.target_audience or '—'}\n"
            f"Brand voice: {profile.brand_voice or '—'}\n"
            f"Competitors:\n{competitor_lines}\n\n"
            "Return JSON only."
        ),
    )
    completion = llm.complete_metered(
        db=ctx.db,
        workspace_id=ctx.workspace_id,
        messages=[system, user],
        max_tokens=1200,
        temperature=0.3,
        purpose="market_intel.positioning_matrix",
    )
    try:
        data = json.loads(completion.text)
    except json.JSONDecodeError:
        # Permissively trim code-fences.
        text = completion.text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        data = json.loads(text)
    if not isinstance(data, dict):
        raise LlmError("Matrix LLM did not return a JSON object.")
    return {
        "rows": data.get("rows") or [],
        "gaps": data.get("gaps") or [],
    }


def _matrix_deterministic(
    profile: OnboardingProfile, competitors: list[dict[str, Any]]
) -> dict[str, Any]:
    """No-LLM fallback: produce a structured but conservative matrix."""
    rows = [
        {
            "name": c.get("name") or "—",
            "url": c.get("url"),
            "positioning_summary": (
                "Manual review required — connect an LLM provider to enrich."
            ),
            "strengths": [],
            "weaknesses": [],
        }
        for c in competitors[:10]
    ]
    gaps: list[dict[str, Any]] = []
    if not profile.brand_voice:
        gaps.append(
            {
                "label": "Brand voice differentiation",
                "summary": (
                    "Brand voice is undefined — every competitor has a chance to "
                    "out-position you on tone alone."
                ),
                "expected_impact": "Improves ad copy resonance and recall.",
                "suggested_action": "Add brand voice to onboarding (tone, vocabulary, taboos).",
            }
        )
    if profile.offer_description and len(profile.offer_description.strip()) < 120:
        gaps.append(
            {
                "label": "Offer specificity",
                "summary": (
                    "Your offer description is short — competitors with sharper "
                    "claims will win the search and ad-impression duel."
                ),
                "expected_impact": "Tightens hero copy, ad headlines, and ICP messaging.",
                "suggested_action": (
                    "Rewrite the offer to name the audience, the outcome, and the wedge."
                ),
            }
        )
    return {"rows": rows, "gaps": gaps}
