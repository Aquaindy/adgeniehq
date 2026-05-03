from datetime import datetime, timezone

from app.agents.base import BaseAgent
from app.agents.types import (
    AgentContext,
    AgentResult,
    SkillOutputRecord,
    TaskRecord,
)
from app.models.agent_task import AgentTaskStatus
from app.models.content_draft import ContentDraftType
from app.models.onboarding_profile import OnboardingProfile
from app.skills.content.generation import (
    ContentRequest,
    generate_content_draft,
)


class ContentWriterAgent(BaseAgent):
    type = "content_writer"
    title = "Content drafter"
    description = (
        "Drafts long-form, landing-page, ad, email, social, or meta copy and saves it as "
        "a content_draft awaiting review. Uses the configured LLM when available; "
        "falls back to a deterministic template populated from your onboarding profile."
    )

    def run(self, ctx: AgentContext) -> AgentResult:
        result = AgentResult()
        started = datetime.now(timezone.utc)

        payload = ctx.input_payload or {}
        type_str = (payload.get("type") or "blog_post").strip().lower()
        try:
            content_type = ContentDraftType(type_str)
        except ValueError:
            result.tasks.append(
                TaskRecord(
                    skill_name="content.generation",
                    status=AgentTaskStatus.FAILED,
                    input_payload={"type": type_str},
                    error_message=(
                        f"Unsupported content type `{type_str}`. "
                        f"Allowed: {[t.value for t in ContentDraftType]}"
                    ),
                    started_at=started,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            return result

        topic = (payload.get("topic") or "").strip()
        if not topic:
            result.tasks.append(
                TaskRecord(
                    skill_name="content.generation",
                    status=AgentTaskStatus.FAILED,
                    input_payload=payload,
                    error_message="Provide a topic to draft about.",
                    started_at=started,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            return result

        keywords = payload.get("keywords") or []
        if not isinstance(keywords, list):
            keywords = []

        request = ContentRequest(
            type=content_type,
            topic=topic,
            keywords=[str(k) for k in keywords],
            target_url=payload.get("target_url"),
            audience=payload.get("audience"),
            notes=payload.get("notes"),
        )

        profile = (
            ctx.db.query(OnboardingProfile)
            .filter(OnboardingProfile.workspace_id == ctx.workspace_id)
            .first()
        )

        draft = generate_content_draft(
            request=request,
            profile=profile,
            db=ctx.db,
            workspace_id=ctx.workspace_id,
        )

        # Optional hero image (DALL-E). Only for SEO-relevant content types
        # by default; caller can opt-out with `include_image=False`.
        image_url: str | None = None
        include_image = bool(payload.get("include_image", True))
        if include_image and content_type in (
            ContentDraftType.BLOG_POST,
            ContentDraftType.LANDING_PAGE,
            ContentDraftType.SOCIAL_POST,
        ):
            from app.llm import LlmError, LlmNotConfiguredError
            from app.llm.client import get_llm_client_for_workspace

            client = get_llm_client_for_workspace(ctx.db, ctx.workspace_id)
            if client.is_configured():
                try:
                    img = client.generate_image(
                        prompt=(
                            f"Editorial hero image for an article titled "
                            f"'{draft.title}'. Modern, clean, no text overlay."
                        ),
                        size="1024x1024",
                    )
                    image_url = img.url
                except (LlmError, LlmNotConfiguredError):
                    # Skip silently — image is optional.
                    image_url = None

        # JSON-LD schema markup. Always emit when the type is page-shaped.
        from app.skills.content.schema_markup import build_jsonld

        jsonld = build_jsonld(
            type=content_type,
            title=draft.title,
            body=draft.body,
            target_url=request.target_url,
            image_url=image_url,
            site_name=(profile.business_name if profile and profile.business_name else None),
            keywords=draft.keywords,
        )

        # Fold image_url + jsonld into seo_metadata for round-trip on the
        # public schema; image_url also lives as a top-level column on the
        # ContentDraft row.
        seo_metadata = dict(draft.seo_metadata or {})
        if jsonld is not None:
            seo_metadata["jsonld"] = jsonld
        if image_url:
            seo_metadata["image_url"] = image_url

        result.tasks.append(
            TaskRecord(
                skill_name="content.generation",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={
                    "type": content_type.value,
                    "topic": topic,
                    "keyword_count": len(keywords),
                },
                output_payload={
                    "source": draft.source,
                    "model_used": draft.model_used,
                },
                started_at=started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="content.generation",
                output_type="content_draft_payload",
                payload={
                    "type": content_type.value,
                    "title": draft.title,
                    "body": draft.body,
                    "seo_metadata": seo_metadata,
                    "keywords": draft.keywords,
                    "source": draft.source,
                    "model_used": draft.model_used,
                    "topic": topic,
                    "target_url": request.target_url,
                    "notes": request.notes,
                    "image_url": image_url,
                },
                task_index=1,
            )
        )

        result.output_payload = {
            "type": content_type.value,
            "topic": topic,
            "source": draft.source,
            "model_used": draft.model_used,
        }
        return result
