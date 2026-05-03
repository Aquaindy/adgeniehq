"""ICP & Persona Agent.

Generates buyer personas, awareness-stage map, objection list, and a messaging
matrix from the onboarding profile. LLM-enriched when available; deterministic
skeleton otherwise.
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
from app.core.exceptions import AdVantaError
from app.llm.client import LlmError, LlmMessage, get_llm_client_for_workspace
from app.models.agent_task import AgentTaskStatus
from app.models.onboarding_profile import OnboardingProfile
from app.models.recommendation import RiskLevel


class IcpPersonaAgent(BaseAgent):
    type = "icp_persona"
    title = "ICP & Persona"
    description = (
        "Generates buyer personas, an awareness-stage map, and a messaging "
        "matrix tailored to your onboarding profile."
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
                    skill_name="icp.review",
                    status=AgentTaskStatus.SKIPPED,
                    input_payload={},
                    error_message="Onboarding has not been completed.",
                    started_at=started,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            result.recommendations.append(
                RecommendationRecord(
                    title="Complete onboarding to unlock ICP research",
                    summary=(
                        "ICP & Persona needs your offer, audience, and pain points "
                        "to generate useful personas."
                    ),
                    recommendation_type="icp.onboarding_incomplete",
                    risk_level=RiskLevel.MEDIUM,
                    expected_impact="Unlocks personas, messaging matrix, and ad targeting suggestions.",
                    suggested_action="Finish the onboarding wizard.",
                )
            )
            result.output_payload = {"skipped": True, "reason": "onboarding_incomplete"}
            return result

        # ------------------------------------------------------------------
        # Skill 1 — persona generation
        # ------------------------------------------------------------------
        personas, source = _generate_personas(ctx, profile)
        result.tasks.append(
            TaskRecord(
                skill_name="icp.personas",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={},
                output_payload={"persona_count": len(personas), "source": source},
                started_at=started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="icp.personas",
                output_type="personas",
                payload={"personas": personas, "source": source},
                task_index=1,
            )
        )

        # ------------------------------------------------------------------
        # Skill 2 — messaging matrix
        # ------------------------------------------------------------------
        msg_started = datetime.now(timezone.utc)
        matrix = _build_messaging_matrix(personas)
        result.tasks.append(
            TaskRecord(
                skill_name="icp.messaging_matrix",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={},
                output_payload={"row_count": len(matrix)},
                started_at=msg_started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="icp.messaging_matrix",
                output_type="messaging_matrix",
                payload={"matrix": matrix},
                task_index=2,
            )
        )

        # ------------------------------------------------------------------
        # Recommendations
        # ------------------------------------------------------------------
        if personas and source == "deterministic":
            result.recommendations.append(
                RecommendationRecord(
                    title="Connect an LLM provider for richer personas",
                    summary=(
                        "Deterministic personas are correct in shape but light on "
                        "specificity. Configure OPENAI_API_KEY (or equivalent) to "
                        "generate persona detail from your offer and audience."
                    ),
                    recommendation_type="icp.llm_unconfigured",
                    risk_level=RiskLevel.LOW,
                    expected_impact="Sharper messaging matrix and ad targeting.",
                    suggested_action="Set OPENAI_API_KEY in workspace settings.",
                )
            )

        result.output_payload = {
            "persona_count": len(personas),
            "source": source,
        }
        return result


# -------------------------------------------------------------------------
# Persona generation
# -------------------------------------------------------------------------


def _generate_personas(
    ctx: AgentContext, profile: OnboardingProfile
) -> tuple[list[dict], str]:
    llm = get_llm_client_for_workspace(ctx.db, ctx.workspace_id)
    if llm.is_configured():
        try:
            return _personas_via_llm(ctx, profile), "llm"
        except (LlmError, AdVantaError):
            pass
    return _personas_deterministic(profile), "deterministic"


def _personas_via_llm(ctx: AgentContext, profile: OnboardingProfile) -> list[dict]:
    llm = get_llm_client_for_workspace(ctx.db, ctx.workspace_id)
    system = LlmMessage(
        role="system",
        content=(
            "You are a senior B2B marketing strategist. Generate 2 ICP personas as a "
            "JSON array. Each persona must include: name, role, company_size, "
            "primary_pain, buying_trigger, top_objection, awareness_stage "
            "(unaware|problem|solution|product|most), preferred_channels (array). "
            "Be specific to the offer. Return JSON only."
        ),
    )
    user = LlmMessage(
        role="user",
        content=(
            f"Offer: {profile.offer_description or '—'}\n"
            f"Target audience: {profile.target_audience or '—'}\n"
            f"Pain points: {profile.pain_points or '—'}\n"
            f"Industry: {profile.industry or '—'}\n"
            f"Brand voice: {profile.brand_voice or '—'}\n\n"
            "Return JSON array."
        ),
    )
    completion = llm.complete_metered(
        db=ctx.db,
        workspace_id=ctx.workspace_id,
        messages=[system, user],
        max_tokens=1000,
        temperature=0.4,
        purpose="icp.personas",
    )
    text = completion.text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LlmError(f"Persona LLM returned non-JSON: {exc}") from exc
    if not isinstance(data, list):
        raise LlmError("Persona LLM did not return a JSON array.")
    return data[:5]


def _personas_deterministic(profile: OnboardingProfile) -> list[dict]:
    """Deterministic skeleton — useful when LLM isn't configured."""
    audience = (profile.target_audience or "").strip() or "—"
    pain = (profile.pain_points or "").strip() or "—"
    industry = profile.industry or "—"

    return [
        {
            "name": "Primary buyer",
            "role": f"Decision-maker in {industry}",
            "company_size": "—",
            "primary_pain": pain,
            "buying_trigger": "Quarterly review reveals a gap that costs revenue.",
            "top_objection": "Implementation effort.",
            "awareness_stage": "problem",
            "preferred_channels": ["search", "linkedin"],
            "audience_summary": audience,
        },
        {
            "name": "Champion / influencer",
            "role": f"Practitioner in {industry}",
            "company_size": "—",
            "primary_pain": "Manual process burning hours each week.",
            "buying_trigger": "Their team's quality scores drop below threshold.",
            "top_objection": "Trust — needs proof from peers.",
            "awareness_stage": "solution",
            "preferred_channels": ["organic", "communities", "youtube"],
            "audience_summary": audience,
        },
    ]


def _build_messaging_matrix(personas: list[dict]) -> list[dict]:
    """Maps each persona × awareness stage to a recommended hook + offer."""
    rows: list[dict] = []
    for p in personas:
        rows.append(
            {
                "persona": p.get("name") or "—",
                "awareness_stage": p.get("awareness_stage") or "problem",
                "hook": (
                    f"{p.get('primary_pain', '—')[:80]}"
                ),
                "offer_framing": "Deliverable + 30-day outcome",
                "preferred_cta": "Book a 15-min walkthrough"
                if p.get("awareness_stage") in ("solution", "product", "most")
                else "Read the playbook",
                "channels": p.get("preferred_channels") or [],
            }
        )
    return rows
