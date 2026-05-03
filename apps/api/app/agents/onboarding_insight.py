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
from app.models.growth_dna_profile import GrowthDnaProfile
from app.models.onboarding_profile import OnboardingProfile
from app.models.recommendation import RiskLevel


class OnboardingInsightAgent(BaseAgent):
    type = "onboarding_insight"
    title = "Onboarding gap analysis"
    description = (
        "Reviews onboarding answers and the latest Growth DNA Profile to identify which "
        "fields would most improve readiness scores if sharpened."
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
            result.output_payload = {"skipped": True, "reason": "onboarding_incomplete"}
            result.tasks.append(
                TaskRecord(
                    skill_name="onboarding.review",
                    status=AgentTaskStatus.SKIPPED,
                    input_payload={},
                    error_message="Onboarding has not been completed.",
                    started_at=started,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            return result

        latest_dna = (
            ctx.db.query(GrowthDnaProfile)
            .filter(GrowthDnaProfile.workspace_id == ctx.workspace_id)
            .order_by(GrowthDnaProfile.created_at.desc())
            .first()
        )

        gaps = self._collect_gaps(profile)
        scores = (
            {
                "funnel": latest_dna.funnel_readiness_score,
                "paid_ads": latest_dna.paid_ads_readiness_score,
            }
            if latest_dna
            else None
        )

        result.tasks.append(
            TaskRecord(
                skill_name="onboarding.review",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={},
                output_payload={"gap_count": len(gaps), "scores": scores},
                started_at=started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="onboarding.review",
                output_type="onboarding_gaps",
                payload={"gaps": gaps, "scores": scores},
                task_index=1,
            )
        )

        for gap in gaps:
            result.recommendations.append(
                RecommendationRecord(
                    title=gap["title"],
                    summary=gap["summary"],
                    recommendation_type=f"onboarding.gap.{gap['field']}",
                    risk_level=gap["risk"],
                    expected_impact=gap["impact"],
                    suggested_action=gap["action"],
                    metadata={"field": gap["field"]},
                )
            )

        result.output_payload = {
            "completed_at": profile.completed_at.isoformat() if profile.completed_at else None,
            "gap_count": len(gaps),
            "scores": scores,
        }
        return result

    def _collect_gaps(self, p: OnboardingProfile) -> list[dict]:
        gaps: list[dict] = []

        if not p.offer_description or len(p.offer_description.strip()) < 80:
            gaps.append(
                {
                    "field": "offer_description",
                    "title": "Tighten your offer description",
                    "summary": (
                        "Your offer description is short — landing-page copy and ad angles will "
                        "fall back to category defaults until it's expanded."
                    ),
                    "risk": RiskLevel.MEDIUM,
                    "impact": (
                        "Sharpens generated ad copy, hero headlines, and ICP messaging."
                    ),
                    "action": "Expand to 2–3 sentences: who it's for, what it does, why it's different.",
                }
            )

        if not p.brand_voice:
            gaps.append(
                {
                    "field": "brand_voice",
                    "title": "Define brand voice",
                    "summary": "Brand voice is undefined — generated copy will sound generic.",
                    "risk": RiskLevel.LOW,
                    "impact": "Improves consistency across ads, landing pages, and reports.",
                    "action": "Add a short paragraph describing tone, sentence length, and what to avoid.",
                }
            )

        if not p.competitors:
            gaps.append(
                {
                    "field": "competitors",
                    "title": "Add 1–3 competitors",
                    "summary": "No competitors listed — Market Intelligence has no starting set.",
                    "risk": RiskLevel.LOW,
                    "impact": "Enables competitor angle research and positioning gap discovery.",
                    "action": "List a few competitors with their URLs.",
                }
            )

        if not p.landing_page_urls:
            gaps.append(
                {
                    "field": "landing_page_urls",
                    "title": "Provide landing page URLs",
                    "summary": "No landing pages listed — the Website Agent has no surface to audit.",
                    "risk": RiskLevel.HIGH,
                    "impact": (
                        "Unlocks landing-page conversion scoring, copy critiques, and A/B test ideas."
                    ),
                    "action": "Add the primary landing page URL (homepage or pricing page is fine).",
                }
            )

        if p.analytics_status != "configured":
            gaps.append(
                {
                    "field": "analytics_status",
                    "title": "Get analytics fully configured",
                    "summary": (
                        "Analytics is reported as "
                        f"`{p.analytics_status or 'unknown'}`. Without trustworthy "
                        "conversion data the Budget Guardian can't enforce ROAS thresholds."
                    ),
                    "risk": RiskLevel.HIGH,
                    "impact": "Unlocks ROAS-based optimization, attribution, and stop-loss rules.",
                    "action": "Set up GA4 with conversion events for the primary goal.",
                }
            )

        if not p.geographic_target:
            gaps.append(
                {
                    "field": "geographic_target",
                    "title": "Set geographic targets",
                    "summary": "Geographic targets are empty — paid budgets may bleed into the wrong markets.",
                    "risk": RiskLevel.MEDIUM,
                    "impact": "Sharpens audience targeting and reduces wasted reach.",
                    "action": "List the countries / regions where your customers actually convert.",
                }
            )

        return gaps
