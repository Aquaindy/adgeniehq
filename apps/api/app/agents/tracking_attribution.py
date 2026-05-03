"""Tracking & Attribution Agent.

Validates that the workspace has trustworthy measurement before any spend goes
out. Inspects connected accounts, the SEO project, and onboarding self-reports
to compute a tracking health score (0-100) and issues a recommendation per
missing piece.

This agent does NOT execute fixes itself — it only describes what's missing
and what to do about it.
"""

from __future__ import annotations

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
from app.models.connected_account import ConnectedAccount, ConnectionStatus
from app.models.onboarding_profile import OnboardingProfile
from app.models.recommendation import RiskLevel
from app.models.seo_project import SeoProject


_AD_PLATFORMS = ("google_ads", "meta_ads", "linkedin_ads")


class TrackingAttributionAgent(BaseAgent):
    type = "tracking_attribution"
    title = "Tracking & Attribution"
    description = (
        "Inspects connected analytics + ad accounts and rates how trustworthy "
        "your conversion measurement is on a 0-100 scale."
    )

    def run(self, ctx: AgentContext) -> AgentResult:
        result = AgentResult()
        started = datetime.now(timezone.utc)

        connected = (
            ctx.db.query(ConnectedAccount)
            .filter(
                ConnectedAccount.workspace_id == ctx.workspace_id,
                ConnectedAccount.status == ConnectionStatus.CONNECTED,
            )
            .all()
        )
        connected_providers = {c.provider for c in connected}

        seo_project = (
            ctx.db.query(SeoProject)
            .filter(SeoProject.workspace_id == ctx.workspace_id)
            .first()
        )
        profile = (
            ctx.db.query(OnboardingProfile)
            .filter(OnboardingProfile.workspace_id == ctx.workspace_id)
            .first()
        )

        # ------------------------------------------------------------------
        # Skill 1 — analytics presence
        # ------------------------------------------------------------------
        ga4_connected = "google_analytics" in connected_providers
        gsc_connected = "google_search_console" in connected_providers
        analytics_self_report = (
            profile.analytics_status if profile is not None else None
        )

        analytics_payload = {
            "ga4_connected": ga4_connected,
            "gsc_connected": gsc_connected,
            "analytics_self_report": analytics_self_report,
            "seo_site_url": seo_project.site_url if seo_project else None,
        }
        result.tasks.append(
            TaskRecord(
                skill_name="tracking.analytics_presence",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={},
                output_payload=analytics_payload,
                started_at=started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="tracking.analytics_presence",
                output_type="analytics_presence",
                payload=analytics_payload,
                task_index=1,
            )
        )

        # ------------------------------------------------------------------
        # Skill 2 — ad-platform conversion readiness
        # ------------------------------------------------------------------
        ad_started = datetime.now(timezone.utc)
        ad_platforms_connected = sorted(
            p for p in _AD_PLATFORMS if p in connected_providers
        )
        ad_payload = {
            "ad_platforms_connected": ad_platforms_connected,
            "current_ad_platforms_self_report": (
                profile.current_ad_platforms if profile is not None else []
            ),
        }
        result.tasks.append(
            TaskRecord(
                skill_name="tracking.ad_platform_readiness",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={},
                output_payload=ad_payload,
                started_at=ad_started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="tracking.ad_platform_readiness",
                output_type="ad_platform_readiness",
                payload=ad_payload,
                task_index=2,
            )
        )

        # ------------------------------------------------------------------
        # Score (0-100)
        # ------------------------------------------------------------------
        score = 0
        if ga4_connected:
            score += 30
        if gsc_connected:
            score += 15
        if ad_platforms_connected:
            score += 25
        if profile is not None:
            if (profile.analytics_status or "").lower() == "configured":
                score += 15
            if profile.primary_conversion_goal:
                score += 10
            if profile.landing_page_urls:
                score += 5
        score = min(score, 100)

        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="tracking.health_score",
                output_type="tracking_health",
                payload={"score": score, "max": 100},
                task_index=2,
            )
        )

        # ------------------------------------------------------------------
        # Recommendations — surface every missing piece individually
        # ------------------------------------------------------------------
        if not ga4_connected:
            result.recommendations.append(
                RecommendationRecord(
                    title="Connect GA4 — without it, attribution is guesswork",
                    summary=(
                        "GA4 is the workspace's source of truth for conversions. "
                        "Without it the Budget Guardian can't enforce ROAS rules."
                    ),
                    recommendation_type="tracking.missing_ga4",
                    risk_level=RiskLevel.HIGH,
                    expected_impact=(
                        "Unlocks ROAS-based optimization, attribution comparisons, "
                        "and stop-loss rules."
                    ),
                    suggested_action=(
                        "Open the Integrations Center and connect Google Analytics 4."
                    ),
                    platform="google_analytics",
                )
            )
        if not gsc_connected:
            result.recommendations.append(
                RecommendationRecord(
                    title="Connect Google Search Console for organic visibility",
                    summary=(
                        "Without GSC the SEO Agent can't surface keyword "
                        "opportunities or track position changes."
                    ),
                    recommendation_type="tracking.missing_gsc",
                    risk_level=RiskLevel.MEDIUM,
                    expected_impact="Unlocks SEO opportunity scoring + position tracking.",
                    suggested_action="Connect Search Console from the Integrations Center.",
                    platform="google_search_console",
                )
            )
        if not ad_platforms_connected:
            result.recommendations.append(
                RecommendationRecord(
                    title="Connect at least one ad platform",
                    summary=(
                        "No ad platforms are connected. Without one, "
                        "campaign analysis and Budget Guardian have nothing to inspect."
                    ),
                    recommendation_type="tracking.no_ad_platform",
                    risk_level=RiskLevel.HIGH,
                    expected_impact=(
                        "Enables campaign sync, recommendations, and budget pacing checks."
                    ),
                    suggested_action="Connect Google Ads, Meta Ads, or LinkedIn Ads.",
                    platform="paid_ads",
                )
            )
        if profile is not None and not profile.primary_conversion_goal:
            result.recommendations.append(
                RecommendationRecord(
                    title="Define a primary conversion goal",
                    summary=(
                        "No primary conversion goal is set — there's nothing for "
                        "agents to optimize against."
                    ),
                    recommendation_type="tracking.no_primary_goal",
                    risk_level=RiskLevel.MEDIUM,
                    expected_impact="Sharpens optimization across paid, SEO, and CRO.",
                    suggested_action=(
                        "Add the primary conversion goal in workspace onboarding."
                    ),
                )
            )

        result.output_payload = {
            "score": score,
            "ga4_connected": ga4_connected,
            "gsc_connected": gsc_connected,
            "ad_platforms_connected": ad_platforms_connected,
            "primary_goal_set": bool(
                profile and profile.primary_conversion_goal
            ),
        }
        return result
