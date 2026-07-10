"""Social content agent.

One parametric generator across every platform in `app/social/catalog.py`,
rather than a class per network — the same shape as `TrafficAssetAgent`. Given
a topic and a set of platforms it emits one `social_content_payload` skill
output per platform, which `content_draft_service` turns into reviewable
ContentDraft rows.

A failure on one platform is isolated: that platform's task is marked FAILED
and the rest still produce drafts.
"""

from datetime import datetime, timezone

from app.agents.base import BaseAgent
from app.agents.types import (
    AgentContext,
    AgentResult,
    SkillOutputRecord,
    TaskRecord,
)
from app.models.agent_task import AgentTaskStatus
from app.models.onboarding_profile import OnboardingProfile
from app.skills.content.social import (
    SocialContentRequest,
    generate_social_content,
)
from app.social.catalog import get_platform, list_platforms

# Guard against a caller asking for an unbounded fan-out of metered LLM calls.
_MAX_PLATFORMS = 9

SKILL_NAME = "content.social"
OUTPUT_TYPE = "social_content_payload"


class SocialContentAgent(BaseAgent):
    type = "social_content"
    title = "Social content studio"
    description = (
        "Turns one topic into platform-native posts (Facebook, X, Instagram, "
        "Pinterest, LinkedIn, Threads) and short-form video scripts (TikTok, "
        "Reels, Shorts), each with its own keywords and hashtags. Uses the "
        "configured LLM when available; falls back to a deterministic skeleton "
        "built from your onboarding profile."
    )

    def run(self, ctx: AgentContext) -> AgentResult:
        result = AgentResult()
        started = datetime.now(timezone.utc)
        payload = ctx.input_payload or {}

        topic = (payload.get("topic") or "").strip()
        if not topic:
            result.tasks.append(
                TaskRecord(
                    skill_name=SKILL_NAME,
                    status=AgentTaskStatus.FAILED,
                    input_payload=payload,
                    error_message="Provide a topic to draft about.",
                    started_at=started,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            return result

        raw_platforms = payload.get("platforms") or []
        if not isinstance(raw_platforms, list) or not raw_platforms:
            result.tasks.append(
                TaskRecord(
                    skill_name=SKILL_NAME,
                    status=AgentTaskStatus.FAILED,
                    input_payload=payload,
                    error_message=(
                        "Select at least one platform. Available: "
                        f"{[p.slug for p in list_platforms()]}"
                    ),
                    started_at=started,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            return result

        # Dedupe while preserving the caller's order.
        slugs: list[str] = []
        for raw in raw_platforms:
            slug = str(raw).strip().lower()
            if slug and slug not in slugs:
                slugs.append(slug)

        unknown = [s for s in slugs if get_platform(s) is None]
        if unknown:
            result.tasks.append(
                TaskRecord(
                    skill_name=SKILL_NAME,
                    status=AgentTaskStatus.FAILED,
                    input_payload={"platforms": slugs},
                    error_message=(
                        f"Unknown platform(s): {unknown}. Available: "
                        f"{[p.slug for p in list_platforms()]}"
                    ),
                    started_at=started,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            return result

        if len(slugs) > _MAX_PLATFORMS:
            result.tasks.append(
                TaskRecord(
                    skill_name=SKILL_NAME,
                    status=AgentTaskStatus.FAILED,
                    input_payload={"platform_count": len(slugs)},
                    error_message=(
                        f"Too many platforms ({len(slugs)}); the maximum per run "
                        f"is {_MAX_PLATFORMS}."
                    ),
                    started_at=started,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            return result

        keywords = payload.get("keywords") or []
        if not isinstance(keywords, list):
            keywords = []
        keywords = [str(k).strip() for k in keywords if str(k).strip()]

        profile = (
            ctx.db.query(OnboardingProfile)
            .filter(OnboardingProfile.workspace_id == ctx.workspace_id)
            .first()
        )

        generated = 0
        errors: list[str] = []
        for slug in slugs:
            platform = get_platform(slug)
            assert platform is not None  # validated above
            task_started = datetime.now(timezone.utc)

            request = SocialContentRequest(
                platform=platform,
                topic=topic,
                keywords=keywords,
                audience=payload.get("audience"),
                target_url=payload.get("target_url"),
                notes=payload.get("notes"),
                call_to_action=payload.get("call_to_action"),
                source_url=payload.get("source_url"),
                source_title=payload.get("source_title"),
                source_content=payload.get("source_content"),
            )

            try:
                draft = generate_social_content(
                    request=request,
                    profile=profile,
                    db=ctx.db,
                    workspace_id=ctx.workspace_id,
                )
            except Exception as exc:  # noqa: BLE001 — isolate per-platform failure
                # Keep the exception type: without it a NameError in the skill
                # reads identically to a legitimate content failure.
                detail = f"{platform.label}: {type(exc).__name__}: {exc}"
                errors.append(detail)
                result.tasks.append(
                    TaskRecord(
                        skill_name=SKILL_NAME,
                        status=AgentTaskStatus.FAILED,
                        input_payload={"platform": slug, "topic": topic},
                        error_message=detail,
                        started_at=task_started,
                        completed_at=datetime.now(timezone.utc),
                    )
                )
                continue

            task_index = len(result.tasks) + 1
            result.tasks.append(
                TaskRecord(
                    skill_name=SKILL_NAME,
                    status=AgentTaskStatus.SUCCEEDED,
                    input_payload={
                        "platform": slug,
                        "topic": topic,
                        "keyword_count": len(keywords),
                    },
                    output_payload={
                        "source": draft.source,
                        "model_used": draft.model_used,
                        "character_count": len(draft.body),
                        "hashtag_count": len(draft.hashtags),
                    },
                    started_at=task_started,
                    completed_at=datetime.now(timezone.utc),
                )
            )

            seo_metadata = dict(draft.seo_metadata or {})
            if draft.script is not None:
                seo_metadata["script"] = draft.script

            result.skill_outputs.append(
                SkillOutputRecord(
                    skill_name=SKILL_NAME,
                    output_type=OUTPUT_TYPE,
                    payload={
                        "platform": slug,
                        "draft_type": platform.draft_type.value,
                        "title": draft.title,
                        "body": draft.body,
                        "hashtags": draft.hashtags,
                        "keywords": draft.keywords,
                        "seo_metadata": seo_metadata,
                        "source": draft.source,
                        "model_used": draft.model_used,
                        "topic": topic,
                        "target_url": request.target_url,
                        "notes": request.notes,
                    },
                    task_index=task_index,
                )
            )
            generated += 1

        result.output_payload = {
            "topic": topic,
            "requested_platforms": slugs,
            "generated": generated,
            "failed": len(slugs) - generated,
            "errors": errors,
        }
        return result
