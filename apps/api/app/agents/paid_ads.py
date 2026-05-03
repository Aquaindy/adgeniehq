"""Paid Ads Agent — analyzes synced campaign rows and emits recommendations."""

from datetime import date, datetime, timezone

from app.agents.base import BaseAgent
from app.agents.types import (
    AgentContext,
    AgentResult,
    RecommendationRecord,
    SkillOutputRecord,
    TaskRecord,
)
from app.models.agent_task import AgentTaskStatus
from app.models.campaign import Campaign, CampaignStatus
from app.models.recommendation import RiskLevel


PROVIDER_DISPLAY = {
    "google_ads": "Google Ads",
    "meta_ads": "Meta Ads",
    "linkedin_ads": "LinkedIn Ads",
}


class PaidAdsAgent(BaseAgent):
    type = "paid_ads"
    title = "Paid Ads analysis"
    description = (
        "Reads synced campaign data, surfaces budget gaps, stale campaigns, and "
        "platform-diversity risk."
    )

    def run(self, ctx: AgentContext) -> AgentResult:
        result = AgentResult()
        started = datetime.now(timezone.utc)

        campaigns: list[Campaign] = (
            ctx.db.query(Campaign)
            .filter(Campaign.workspace_id == ctx.workspace_id)
            .all()
        )

        # ------------------------------------------------------------------
        # Skill 1 — overall summary
        # ------------------------------------------------------------------
        active = [c for c in campaigns if c.status == CampaignStatus.ACTIVE]
        paused = [c for c in campaigns if c.status == CampaignStatus.PAUSED]
        ended = [c for c in campaigns if c.status == CampaignStatus.ENDED]

        per_provider: dict[str, int] = {}
        for c in campaigns:
            per_provider[c.provider] = per_provider.get(c.provider, 0) + 1

        summary_payload = {
            "total": len(campaigns),
            "active": len(active),
            "paused": len(paused),
            "ended": len(ended),
            "per_provider": per_provider,
        }

        result.tasks.append(
            TaskRecord(
                skill_name="paid_ads.summary",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={},
                output_payload=summary_payload,
                started_at=started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="paid_ads.summary",
                output_type="paid_ads_summary",
                payload=summary_payload,
                task_index=1,
            )
        )

        # If there's nothing to analyze, surface that as a single recommendation.
        if not campaigns:
            result.recommendations.append(
                RecommendationRecord(
                    title="No campaigns synced yet",
                    summary=(
                        "Connect at least one ad platform (Google Ads, Meta Ads, or "
                        "LinkedIn Ads) and run a sync. Without campaign data the Paid "
                        "Ads Agent and Budget Guardian have nothing to optimize."
                    ),
                    recommendation_type="paid_ads.no_campaigns",
                    risk_level=RiskLevel.MEDIUM,
                    expected_impact=(
                        "Unlocks campaign analysis, budget guardrails, and ROAS-aware optimization."
                    ),
                    suggested_action="Open the Integrations Center and connect an ad platform.",
                    platform="paid_ads",
                )
            )
            result.output_payload = summary_payload
            return result

        # ------------------------------------------------------------------
        # Skill 2 — Budget Guardian: check active campaigns have a budget set
        # ------------------------------------------------------------------
        bg_started = datetime.now(timezone.utc)
        budgetless: list[Campaign] = [
            c
            for c in active
            if (c.daily_budget_cents in (None, 0))
            and (c.lifetime_budget_cents in (None, 0))
        ]
        budget_payload = {
            "active_total": len(active),
            "active_without_budget": len(budgetless),
            "budgetless_ids": [str(c.id) for c in budgetless[:25]],
        }
        result.tasks.append(
            TaskRecord(
                skill_name="budget_guardian.budget_set",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={},
                output_payload=budget_payload,
                started_at=bg_started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="budget_guardian.budget_set",
                output_type="budget_check",
                payload=budget_payload,
                task_index=2,
            )
        )
        for c in budgetless:
            result.recommendations.append(
                RecommendationRecord(
                    title=f"Active campaign without budget: {c.name[:80]}",
                    summary=(
                        f"`{c.name}` on {PROVIDER_DISPLAY.get(c.provider, c.provider)} is "
                        "active but has no daily or lifetime budget set."
                    ),
                    recommendation_type="paid_ads.budget_unset",
                    risk_level=RiskLevel.MEDIUM,
                    expected_impact=(
                        "Without a budget, the Budget Guardian can't enforce daily caps "
                        "or stop-loss rules — exposure is unbounded."
                    ),
                    suggested_action=(
                        "Set a daily budget in the platform UI, then re-sync. Start small "
                        "if the campaign is still in test mode."
                    ),
                    platform=c.provider,
                    metadata={"campaign_id": str(c.id), "external_id": c.external_id},
                )
            )

        # ------------------------------------------------------------------
        # Skill 3 — Staleness: active campaigns whose end_date is in the past
        # ------------------------------------------------------------------
        st_started = datetime.now(timezone.utc)
        today = date.today()
        stale = [
            c for c in active if c.end_date is not None and c.end_date < today
        ]
        staleness_payload = {
            "today": today.isoformat(),
            "stale_active": len(stale),
            "stale_ids": [str(c.id) for c in stale[:25]],
        }
        result.tasks.append(
            TaskRecord(
                skill_name="budget_guardian.staleness",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={},
                output_payload=staleness_payload,
                started_at=st_started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="budget_guardian.staleness",
                output_type="staleness_check",
                payload=staleness_payload,
                task_index=3,
            )
        )
        for c in stale:
            result.recommendations.append(
                RecommendationRecord(
                    title=f"Past-end-date campaign still active: {c.name[:80]}",
                    summary=(
                        f"`{c.name}` is marked active but has an end date of "
                        f"{c.end_date.isoformat()}, which is in the past."
                    ),
                    recommendation_type="paid_ads.stale_active",
                    risk_level=RiskLevel.HIGH,
                    expected_impact=(
                        "Stale active campaigns continue spending against an objective "
                        "that's already complete."
                    ),
                    suggested_action="Pause or archive the campaign in the platform UI.",
                    platform=c.provider,
                    metadata={"campaign_id": str(c.id), "external_id": c.external_id},
                )
            )

        # ------------------------------------------------------------------
        # Skill 4 — Platform diversity
        # ------------------------------------------------------------------
        pd_started = datetime.now(timezone.utc)
        active_per_provider = {
            p: len([c for c in active if c.provider == p]) for p in per_provider
        }
        active_providers = [p for p, n in active_per_provider.items() if n > 0]
        diversity_payload = {
            "active_per_provider": active_per_provider,
            "single_platform": len(active_providers) == 1 and len(active) >= 3,
        }
        result.tasks.append(
            TaskRecord(
                skill_name="paid_ads.platform_diversity",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={},
                output_payload=diversity_payload,
                started_at=pd_started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="paid_ads.platform_diversity",
                output_type="platform_diversity",
                payload=diversity_payload,
                task_index=4,
            )
        )
        if diversity_payload["single_platform"]:
            sole = active_providers[0]
            result.recommendations.append(
                RecommendationRecord(
                    title="Concentration risk: all active spend on one platform",
                    summary=(
                        f"Every active campaign runs on "
                        f"{PROVIDER_DISPLAY.get(sole, sole)}. A single platform issue "
                        "(account flag, policy update, attribution change) could halt "
                        "all paid traffic."
                    ),
                    recommendation_type="paid_ads.single_platform",
                    risk_level=RiskLevel.LOW,
                    expected_impact=(
                        "Adding a second platform creates a fallback channel and surfaces "
                        "audience overlaps that improve cross-platform ROAS."
                    ),
                    suggested_action=(
                        "Pilot one campaign on a complementary platform (e.g. Google ↔ Meta)."
                    ),
                    platform="paid_ads",
                )
            )

        result.output_payload = {
            **summary_payload,
            "active_per_provider": active_per_provider,
            "active_without_budget": len(budgetless),
            "stale_active": len(stale),
        }
        return result
