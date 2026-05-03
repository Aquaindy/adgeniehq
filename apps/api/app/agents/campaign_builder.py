"""Campaign Builder Agent.

Produces a launch-ready campaign blueprint: objective, naming convention,
ad-set / ad-group structure, audience mapping, budget split, conversion event,
tracking checklist, and a launch-ready checklist for the operator.

The agent never writes to platforms directly — it produces a structured plan
saved as a SkillOutput, plus a Recommendation that requires explicit human
approval before any execution agent picks it up.

Inputs (all optional):
- input_payload.objective: "lead_gen" | "traffic" | "conversions" | "awareness"
- input_payload.platform: "google_ads" | "meta_ads" | "linkedin_ads"
- input_payload.budget_cents: int (overrides onboarding monthly budget)
- input_payload.audience_size: "narrow" | "balanced" | "broad"
"""

from __future__ import annotations

from datetime import date, datetime, timezone
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
from app.models.onboarding_profile import OnboardingProfile
from app.models.recommendation import RiskLevel


_OBJECTIVES = {
    "lead_gen": "Generate leads via form fills.",
    "traffic": "Drive qualified clicks to a landing page.",
    "conversions": "Optimize for the primary conversion goal.",
    "awareness": "Maximize unique reach against the ICP.",
}

_PLATFORM_LABELS = {
    "google_ads": "Google Ads",
    "meta_ads": "Meta Ads",
    "linkedin_ads": "LinkedIn Ads",
}


class CampaignBuilderAgent(BaseAgent):
    type = "campaign_builder"
    title = "Campaign Builder"
    description = (
        "Builds a launch-ready campaign blueprint (objective, structure, "
        "budget split, tracking checklist) you can review + approve before "
        "any platform write."
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
                    skill_name="campaign_builder.review",
                    status=AgentTaskStatus.SKIPPED,
                    input_payload={},
                    error_message="Onboarding has not been completed.",
                    started_at=started,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            result.recommendations.append(
                RecommendationRecord(
                    title="Complete onboarding to build a campaign blueprint",
                    summary=(
                        "Campaign Builder needs your offer, audience, and budget "
                        "to produce a structured plan."
                    ),
                    recommendation_type="campaign_builder.onboarding_incomplete",
                    risk_level=RiskLevel.MEDIUM,
                    expected_impact="Unlocks structured launch plans.",
                    suggested_action="Finish the onboarding wizard.",
                )
            )
            result.output_payload = {"skipped": True, "reason": "onboarding_incomplete"}
            return result

        objective = str(ctx.input_payload.get("objective") or "conversions").lower()
        if objective not in _OBJECTIVES:
            objective = "conversions"

        platform = str(ctx.input_payload.get("platform") or "").lower()
        if platform not in _PLATFORM_LABELS:
            # Pick the first connected platform from onboarding, else google_ads.
            current = profile.current_ad_platforms or []
            platform = next(
                (p for p in current if p in _PLATFORM_LABELS), "google_ads"
            )

        # Use input override if given; otherwise fall back to onboarding's
        # budget range. Plan against the ceiling so the campaign blueprint
        # represents the customer's full intended spend; if only one bound
        # is set we use whichever is present.
        budget_cents_raw = ctx.input_payload.get("budget_cents")
        if isinstance(budget_cents_raw, int) and budget_cents_raw > 0:
            budget_cents = budget_cents_raw
        else:
            ceiling = (
                profile.monthly_ad_budget_max_usd
                or profile.monthly_ad_budget_min_usd
                or 1000
            )
            budget_cents = ceiling * 100

        audience_size = str(
            ctx.input_payload.get("audience_size") or "balanced"
        ).lower()
        if audience_size not in ("narrow", "balanced", "broad"):
            audience_size = "balanced"

        blueprint = _build_blueprint(
            profile=profile,
            objective=objective,
            platform=platform,
            budget_cents=budget_cents,
            audience_size=audience_size,
        )
        result.tasks.append(
            TaskRecord(
                skill_name="campaign_builder.blueprint",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={
                    "objective": objective,
                    "platform": platform,
                    "budget_cents": budget_cents,
                    "audience_size": audience_size,
                },
                output_payload={"ad_groups": len(blueprint["ad_groups"])},
                started_at=started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="campaign_builder.blueprint",
                output_type="campaign_blueprint",
                payload=blueprint,
                task_index=1,
            )
        )

        # Surface the blueprint as an approval-gated recommendation. Execution
        # is deliberately *not* automatic — operators must review the plan,
        # then a separate execution agent (post-Autopilot) writes to the
        # platform if approved.
        result.recommendations.append(
            RecommendationRecord(
                title=(
                    f"Launch-ready blueprint: {blueprint['campaign_name']} "
                    f"({_PLATFORM_LABELS[platform]})"
                ),
                summary=(
                    f"Objective: {_OBJECTIVES[objective]} "
                    f"Budget: ${budget_cents / 100:,.0f}/mo across "
                    f"{len(blueprint['ad_groups'])} ad groups."
                ),
                recommendation_type="campaign_builder.blueprint",
                risk_level=RiskLevel.HIGH,  # any spend gate must be approved
                expected_impact=(
                    "Ready-to-launch structure — typically 1–2 weeks faster than "
                    "starting from a blank slate."
                ),
                suggested_action=(
                    "Review the blueprint, edit if needed, then approve to send "
                    "to the appropriate execution agent."
                ),
                platform=platform,
                metadata={
                    "blueprint": blueprint,
                    "budget_cents": budget_cents,
                    "objective": objective,
                    "audience_size": audience_size,
                },
            )
        )

        result.output_payload = {
            "objective": objective,
            "platform": platform,
            "budget_cents": budget_cents,
            "ad_group_count": len(blueprint["ad_groups"]),
        }
        return result


def _build_blueprint(
    *,
    profile: OnboardingProfile,
    objective: str,
    platform: str,
    budget_cents: int,
    audience_size: str,
) -> dict[str, Any]:
    """Deterministic blueprint construction. Naming follows the convention
    `{objective}_{platform}_{audience_size}_{YYYYMM}` so structure is stable
    when the LLM is offline."""
    period = date.today().strftime("%Y%m")
    base_name = (
        f"{objective}_{platform}_{audience_size}_{period}"
    )

    # 70/30 split between primary ad group and a test ad group.
    primary_daily = int((budget_cents * 0.70) / 30)
    test_daily = int((budget_cents * 0.30) / 30)

    ad_groups: list[dict[str, Any]] = [
        {
            "name": f"{base_name}__primary",
            "audience_persona": "Primary buyer",
            "audience_size": audience_size,
            "daily_budget_cents": primary_daily,
            "creative_count_target": 3,
            "notes": (
                "Primary ad group — highest-intent audience, most budget. "
                "Pair with the strongest landing page."
            ),
        },
        {
            "name": f"{base_name}__test",
            "audience_persona": "Champion / influencer",
            "audience_size": "narrow" if audience_size == "balanced" else audience_size,
            "daily_budget_cents": test_daily,
            "creative_count_target": 2,
            "notes": (
                "Test ad group — narrower audience, smaller budget, used to "
                "validate angles before scaling."
            ),
        },
    ]

    landing_pages = profile.landing_page_urls or []
    primary_landing = landing_pages[0] if landing_pages else None

    tracking_checklist = [
        "GA4 conversion event configured for primary goal",
        f"{_PLATFORM_LABELS[platform]} conversion / pixel firing on goal page",
        "UTMs include platform + ad-group params",
        "Approval flow points new spend to Budget Guardian",
    ]

    return {
        "campaign_name": base_name,
        "platform": platform,
        "objective": objective,
        "monthly_budget_cents": budget_cents,
        "primary_landing_page": primary_landing,
        "ad_groups": ad_groups,
        "tracking_checklist": tracking_checklist,
        "naming_convention": "{objective}_{platform}_{audience}_{YYYYMM}",
    }
