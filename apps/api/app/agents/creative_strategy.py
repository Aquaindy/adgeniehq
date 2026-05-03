"""Creative Strategy Agent.

Generates ad-copy variants (headlines + descriptions) and persists them to the
`creatives` table tagged `source='ai_generated'`. Variants are grounded in the
onboarding profile (offer, audience, brand voice) plus any persona records the
ICP agent already produced.

LLM-enriched when configured; deterministic skeleton otherwise so the agent
always produces *something* the operator can edit.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

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
from app.models.agent_run import AgentRun
from app.models.agent_task import AgentTaskStatus
from app.models.creative import Creative, CreativeSource, CreativeType
from app.models.onboarding_profile import OnboardingProfile
from app.models.recommendation import RiskLevel
from app.models.skill_output import SkillOutput


class CreativeStrategyAgent(BaseAgent):
    type = "creative_strategy"
    title = "Creative Strategy"
    description = (
        "Generates 3–6 ad-copy variants per request and saves them as creatives "
        "ready for testing. Pulls from your offer, audience, and any personas "
        "the ICP agent has already produced."
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
                    skill_name="creative_strategy.review",
                    status=AgentTaskStatus.SKIPPED,
                    input_payload={},
                    error_message="Onboarding has not been completed.",
                    started_at=started,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            result.recommendations.append(
                RecommendationRecord(
                    title="Complete onboarding to unlock creative generation",
                    summary=(
                        "Creative Strategy needs your offer + audience to generate "
                        "ad copy that actually reflects your business."
                    ),
                    recommendation_type="creative_strategy.onboarding_incomplete",
                    risk_level=RiskLevel.MEDIUM,
                    expected_impact="Unlocks ad-copy generation tied to your ICP.",
                    suggested_action="Finish the onboarding wizard.",
                )
            )
            result.output_payload = {"skipped": True, "reason": "onboarding_incomplete"}
            return result

        # Optional persona context — pulled from the most recent ICP run.
        personas = _load_latest_personas(ctx)

        creative_type_input = str(
            ctx.input_payload.get("creative_type") or "search_ad"
        ).lower()
        try:
            creative_type = CreativeType(creative_type_input)
        except ValueError:
            creative_type = CreativeType.SEARCH_AD

        # ------------------------------------------------------------------
        # Skill 1 — generate variants
        # ------------------------------------------------------------------
        variants, source = _generate_variants(ctx, profile, personas, creative_type)
        gen_payload = {
            "source": source,
            "variant_count": len(variants),
            "creative_type": creative_type.value,
        }
        result.tasks.append(
            TaskRecord(
                skill_name="creative_strategy.generate",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={"creative_type": creative_type.value},
                output_payload=gen_payload,
                started_at=started,
                completed_at=datetime.now(timezone.utc),
            )
        )

        # ------------------------------------------------------------------
        # Skill 2 — persist creatives
        # ------------------------------------------------------------------
        persist_started = datetime.now(timezone.utc)
        persisted: list[dict[str, Any]] = []
        for v in variants:
            creative = Creative(
                workspace_id=ctx.workspace_id,
                type=creative_type,
                source=CreativeSource.AI_GENERATED,
                title=v.get("title"),
                headline=v.get("headline"),
                description=v.get("description"),
                primary_text=v.get("primary_text"),
                cta=v.get("cta"),
                metadata_json={
                    "angle": v.get("angle"),
                    "persona": v.get("persona"),
                    "source": source,
                },
            )
            ctx.db.add(creative)
            ctx.db.flush()
            persisted.append({"creative_id": str(creative.id), **v})

        result.tasks.append(
            TaskRecord(
                skill_name="creative_strategy.persist",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={},
                output_payload={"persisted_count": len(persisted)},
                started_at=persist_started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="creative_strategy.persist",
                output_type="creative_variants",
                payload={"variants": persisted, "creative_type": creative_type.value},
                task_index=2,
            )
        )

        # Surface a summary recommendation so the variants get reviewed.
        if persisted:
            result.recommendations.append(
                RecommendationRecord(
                    title=f"Review {len(persisted)} new creative variants",
                    summary=(
                        f"Generated {len(persisted)} {creative_type.value.replace('_', ' ')} "
                        "variants from your offer + brand voice."
                    ),
                    recommendation_type="creative_strategy.variants_generated",
                    risk_level=RiskLevel.LOW,
                    expected_impact=(
                        "Faster time-to-test new ad angles without writing copy from scratch."
                    ),
                    suggested_action=(
                        "Open the Creatives tab, edit, and attach to ad groups."
                    ),
                    metadata={
                        "creative_ids": [p["creative_id"] for p in persisted],
                        "creative_type": creative_type.value,
                        "source": source,
                    },
                )
            )

        result.output_payload = {
            "creative_type": creative_type.value,
            "source": source,
            "variant_count": len(persisted),
        }
        return result


# -------------------------------------------------------------------------
# Variant generation
# -------------------------------------------------------------------------


def _load_latest_personas(ctx: AgentContext) -> list[dict[str, Any]]:
    """Pull personas from the most recent successful icp_persona run, if any."""
    latest_icp = (
        ctx.db.query(AgentRun)
        .filter(
            AgentRun.workspace_id == ctx.workspace_id,
            AgentRun.agent_type == "icp_persona",
        )
        .order_by(AgentRun.created_at.desc())
        .first()
    )
    if latest_icp is None:
        return []
    output = (
        ctx.db.query(SkillOutput)
        .filter(
            SkillOutput.agent_run_id == latest_icp.id,
            SkillOutput.skill_name == "icp.personas",
        )
        .order_by(SkillOutput.created_at.desc())
        .first()
    )
    if output is None or not isinstance(output.payload, dict):
        return []
    personas = output.payload.get("personas") or []
    return personas if isinstance(personas, list) else []


def _generate_variants(
    ctx: AgentContext,
    profile: OnboardingProfile,
    personas: list[dict[str, Any]],
    creative_type: CreativeType,
) -> tuple[list[dict[str, Any]], str]:
    llm = get_llm_client_for_workspace(ctx.db, ctx.workspace_id)
    if llm.is_configured():
        try:
            return _variants_via_llm(ctx, profile, personas, creative_type), "llm"
        except (LlmError, AdVantaError):
            pass
    return _variants_deterministic(profile, personas, creative_type), "deterministic"


def _variants_via_llm(
    ctx: AgentContext,
    profile: OnboardingProfile,
    personas: list[dict[str, Any]],
    creative_type: CreativeType,
) -> list[dict[str, Any]]:
    llm = get_llm_client_for_workspace(ctx.db, ctx.workspace_id)
    persona_lines = "\n".join(
        f"- {p.get('name', '?')}: {p.get('primary_pain', '—')}"
        for p in personas[:3]
    )

    if creative_type == CreativeType.SEARCH_AD:
        schema_hint = (
            "Each variant: {headline (<=30 chars), description (<=90 chars), "
            "cta, angle}."
        )
    elif creative_type in (CreativeType.SINGLE_IMAGE, CreativeType.RESPONSIVE_DISPLAY):
        schema_hint = (
            "Each variant: {headline (<=40 chars), primary_text (<=125 chars), "
            "cta, angle}."
        )
    else:
        schema_hint = (
            "Each variant: {headline, primary_text, description, cta, angle}."
        )

    system = LlmMessage(
        role="system",
        content=(
            "You are a senior performance copywriter. Generate 4 distinct ad-copy "
            f"variants as a JSON array. Type: {creative_type.value}. {schema_hint} "
            "Respect the brand voice. Avoid emojis unless the brand voice asks. "
            "Return JSON only."
        ),
    )
    user = LlmMessage(
        role="user",
        content=(
            f"Offer: {profile.offer_description or '—'}\n"
            f"Audience: {profile.target_audience or '—'}\n"
            f"Brand voice: {profile.brand_voice or '—'}\n"
            f"Personas:\n{persona_lines or '(none provided)'}\n\n"
            "Return JSON array."
        ),
    )
    completion = llm.complete_metered(
        db=ctx.db,
        workspace_id=ctx.workspace_id,
        messages=[system, user],
        max_tokens=900,
        temperature=0.7,
        purpose="creative_strategy.variants",
    )
    text = completion.text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LlmError(f"Variant LLM returned non-JSON: {exc}") from exc
    if not isinstance(data, list):
        raise LlmError("Variant LLM did not return a JSON array.")
    return data[:8]


def _variants_deterministic(
    profile: OnboardingProfile,
    personas: list[dict[str, Any]],
    creative_type: CreativeType,
) -> list[dict[str, Any]]:
    """Conservative skeleton — encourages editing rather than shipping as-is."""
    industry = profile.industry or "your category"
    audience = (profile.target_audience or "buyers").strip()
    offer = (profile.offer_description or "").strip().split(".")[0][:90] or "—"

    variants: list[dict[str, Any]] = [
        {
            "headline": f"Built for {industry} teams",
            "description": offer,
            "primary_text": offer,
            "cta": "Learn more",
            "angle": "category_authority",
            "persona": personas[0].get("name") if personas else None,
        },
        {
            "headline": f"For {audience[:24]}",
            "description": "Cut waste. Ship faster.",
            "primary_text": offer,
            "cta": "Get started",
            "angle": "outcome_first",
            "persona": personas[1].get("name") if len(personas) > 1 else None,
        },
        {
            "headline": "Less guessing, more growth",
            "description": offer,
            "primary_text": offer,
            "cta": "See it in action",
            "angle": "pain_relief",
            "persona": None,
        },
    ]
    if creative_type == CreativeType.SEARCH_AD:
        # Search ads need headline ≤ 30 chars; truncate.
        for v in variants:
            v["headline"] = v["headline"][:30]
            v["description"] = (v["description"] or "")[:90]
    return variants
