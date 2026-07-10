"""Growth Content Studio Agent.

Reads a workspace's Growth DNA Profile and, for each section/segment, generates
ready-to-use copy — a keyword plan, ad copy per recommended platform, landing-
page copy, lifecycle emails, organic social content per content pillar, and SEO
meta tags. Organic social is platform-native: each pillar is assigned a platform
from the Growth DNA's own `platform_strategy`, and produces either a post (within
that network's character ceiling, with hashtags) or a Reels/Shorts/TikTok script.
Each artifact is persisted as a `SuggestedCopy` (surfaced on the Creatives page
under "Suggested Copies" and downloadable as .txt / .docx).

Every run is stamped with the product/service name — taken from the run's
`product_name` input, else the onboarding business name — so the agent always
knows which profile it is generating for.

LLM-grounded when configured; deterministic skeleton otherwise so the agent
always produces real, editable artifacts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

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
from app.models.suggested_copy import SuggestedCopy
from app.models.workspace import Workspace
from app.skills.content.copy_studio import generate_suggested_copies


class GrowthContentAgent(BaseAgent):
    type = "growth_content"
    title = "Growth Content Studio"
    description = (
        "Turns each section of your Growth DNA into ready-to-use copy — a keyword "
        "plan, ad copy per recommended platform, landing-page copy, lifecycle "
        "emails, platform-native organic social posts and Reels/Shorts scripts per "
        "content pillar, and SEO meta tags. Saved under Suggested Copies on the "
        "Creatives page and downloadable as .txt or .docx."
    )

    def run(self, ctx: AgentContext) -> AgentResult:
        result = AgentResult()
        started = datetime.now(timezone.utc)

        dna = _resolve_growth_dna(ctx)
        if dna is None:
            result.tasks.append(
                TaskRecord(
                    skill_name="growth_content.review",
                    status=AgentTaskStatus.SKIPPED,
                    input_payload={},
                    error_message="No Growth DNA Profile found for this workspace.",
                    started_at=started,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            result.recommendations.append(
                RecommendationRecord(
                    title="Generate a Growth DNA Profile to unlock content",
                    summary=(
                        "Growth Content Studio writes copy from each section of your "
                        "Growth DNA — generate the profile first."
                    ),
                    recommendation_type="growth_content.no_growth_dna",
                    risk_level=RiskLevel.MEDIUM,
                    expected_impact="Unlocks keyword, ad, landing-page, email, and social copy.",
                    suggested_action="Finish onboarding, then generate your Growth DNA Profile.",
                )
            )
            result.output_payload = {"skipped": True, "reason": "no_growth_dna"}
            return result

        profile = (
            ctx.db.query(OnboardingProfile)
            .filter(OnboardingProfile.id == dna.onboarding_profile_id)
            .first()
        )
        if profile is None:
            profile = (
                ctx.db.query(OnboardingProfile)
                .filter(OnboardingProfile.workspace_id == ctx.workspace_id)
                .first()
            )

        product_name = _resolve_product_name(ctx, profile)

        # ------------------------------------------------------------------
        # Skill — generate the copy bundle
        # ------------------------------------------------------------------
        bundle = generate_suggested_copies(
            ctx.db,
            workspace_id=ctx.workspace_id,
            profile=profile,
            dna=dna,
            product_name=product_name,
        )
        result.tasks.append(
            TaskRecord(
                skill_name="growth_content.generate",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={"product_name": product_name},
                output_payload={
                    "source": bundle.source,
                    "copy_count": len(bundle.copies),
                },
                started_at=started,
                completed_at=datetime.now(timezone.utc),
            )
        )

        # ------------------------------------------------------------------
        # Skill — persist suggested copies
        # ------------------------------------------------------------------
        persist_started = datetime.now(timezone.utc)
        persisted: list[dict] = []
        by_type: dict[str, int] = {}
        for c in bundle.copies:
            row = SuggestedCopy(
                workspace_id=ctx.workspace_id,
                growth_dna_profile_id=dna.id,
                product_name=product_name,
                copy_type=c.copy_type,
                section=c.section,
                title=c.title,
                body=c.body,
                source=bundle.source,
                model_used=bundle.model_used,
                metadata_json={
                    "section": c.section,
                    # Only organic-social artifacts carry these.
                    **({"platform": c.platform} if c.platform else {}),
                    **({"hashtags": c.hashtags} if c.hashtags else {}),
                },
            )
            ctx.db.add(row)
            ctx.db.flush()
            persisted.append(
                {"id": str(row.id), "copy_type": c.copy_type.value, "section": c.section}
            )
            by_type[c.copy_type.value] = by_type.get(c.copy_type.value, 0) + 1

        result.tasks.append(
            TaskRecord(
                skill_name="growth_content.persist",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={},
                output_payload={"persisted_count": len(persisted)},
                started_at=persist_started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="growth_content.persist",
                output_type="suggested_copies",
                payload={
                    "product_name": product_name,
                    "source": bundle.source,
                    "model_used": bundle.model_used,
                    "count": len(persisted),
                    "by_type": by_type,
                    "copy_ids": [p["id"] for p in persisted],
                },
                task_index=1,
            )
        )

        if persisted:
            result.recommendations.append(
                RecommendationRecord(
                    title=f"Review {len(persisted)} suggested copies for {product_name}",
                    summary=(
                        f"Generated {len(persisted)} copy artifacts across "
                        f"{len(by_type)} content types from your Growth DNA "
                        f"({bundle.source})."
                    ),
                    recommendation_type="growth_content.copies_generated",
                    risk_level=RiskLevel.LOW,
                    expected_impact=(
                        "Faster time-to-launch — keyword, ad, landing-page, email, and "
                        "social copy ready to edit and ship."
                    ),
                    suggested_action=(
                        "Open Creatives → Suggested Copies to review, edit, and download "
                        "as .txt or .docx."
                    ),
                    metadata={
                        "product_name": product_name,
                        "by_type": by_type,
                        "growth_dna_profile_id": str(dna.id),
                    },
                )
            )

        result.output_payload = {
            "product_name": product_name,
            "source": bundle.source,
            "copy_count": len(persisted),
            "by_type": by_type,
        }
        return result


def _resolve_growth_dna(ctx: AgentContext) -> GrowthDnaProfile | None:
    raw_id = ctx.input_payload.get("growth_dna_profile_id") or ctx.input_payload.get(
        "profile_id"
    )
    if raw_id:
        try:
            wanted = UUID(str(raw_id))
        except (ValueError, TypeError):
            wanted = None
        if wanted is not None:
            found = (
                ctx.db.query(GrowthDnaProfile)
                .filter(
                    GrowthDnaProfile.id == wanted,
                    GrowthDnaProfile.workspace_id == ctx.workspace_id,
                )
                .first()
            )
            if found is not None:
                return found
    # Fall back to the latest profile for the workspace.
    return (
        ctx.db.query(GrowthDnaProfile)
        .filter(GrowthDnaProfile.workspace_id == ctx.workspace_id)
        .order_by(GrowthDnaProfile.created_at.desc())
        .first()
    )


def _resolve_product_name(
    ctx: AgentContext, profile: OnboardingProfile | None
) -> str:
    explicit = ctx.input_payload.get("product_name")
    if explicit and str(explicit).strip():
        return str(explicit).strip()[:255]
    if profile is not None and profile.business_name:
        return profile.business_name[:255]
    workspace = (
        ctx.db.query(Workspace).filter(Workspace.id == ctx.workspace_id).first()
    )
    if workspace is not None and getattr(workspace, "name", None):
        return workspace.name[:255]
    return "your business"
