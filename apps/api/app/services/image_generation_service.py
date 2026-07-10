"""Generate a creative image for a content draft.

Turns an approved-or-draft post into a finished visual using OpenAI's image
models (gpt-image / dall-e). The generated image is persisted to the workspace
upload store and its URL stamped onto `content_drafts.image_url`.

Image generation requires an OpenAI key specifically — a workspace using Claude
or Gemini for text still needs an OpenAI credential (or the env key) here.
There is no deterministic fallback: without a key we return an honest error
rather than a placeholder image (production rule: never fabricate assets).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AdGenieError
from app.llm.client import ImageResult, LlmError, LlmNotConfiguredError, OpenAIClient
from app.models.audit_log import AuditActorType
from app.models.content_draft import ContentDraft
from app.models.usage_event import UsageEventType
from app.security.permissions import Role, require_role_at_least
from app.services import (
    audit_service,
    billing_service,
    content_draft_service,
    image_upload_service,
)
from app.social.catalog import get_platform


class ImageGenerationError(AdGenieError):
    status_code = 502
    code = "image_generation_failed"


class ImageProviderNotConfiguredError(AdGenieError):
    status_code = 400
    code = "image_provider_not_configured"


# gpt-image / dall-e-3 accept exactly these sizes. We pick the closest match to
# each surface's native aspect ratio.
_SIZE_SQUARE = "1024x1024"
_SIZE_PORTRAIT = "1024x1536"
_SIZE_LANDSCAPE = "1536x1024"

# Text platforms whose feed images read best square; everything else posts wide.
_SQUARE_SLUGS = {"instagram", "threads"}
_PORTRAIT_SLUGS = {"pinterest"}


def _resolve_openai_client(db: Session, workspace_id: UUID) -> OpenAIClient | None:
    """Find an OpenAI client for this workspace: a saved OpenAI credential
    first, then the env key. Returns None when neither exists."""

    from app.models.provider_credential import ProviderCredentialProvider
    from app.security.encryption import decrypt
    from app.services import provider_credentials_service

    for cred in provider_credentials_service.get_active_credentials(
        db, workspace_id=workspace_id
    ):
        if cred.provider == ProviderCredentialProvider.OPENAI:
            return OpenAIClient(api_key=decrypt(cred.encrypted_secret))

    if settings.openai_api_key:
        return OpenAIClient(api_key=settings.openai_api_key)
    return None


def _image_size_for(draft: ContentDraft) -> str:
    """Map the draft's platform to the nearest supported image size."""

    if draft.platform:
        platform = get_platform(draft.platform)
        if platform is not None:
            if platform.is_video:
                # Vertical cover frame for a Reel/Short.
                return _SIZE_PORTRAIT
            if platform.slug in _SQUARE_SLUGS:
                return _SIZE_SQUARE
            if platform.slug in _PORTRAIT_SLUGS:
                return _SIZE_PORTRAIT
            return _SIZE_LANDSCAPE
    # Non-social drafts (blog hero, landing page) default to landscape.
    return _SIZE_LANDSCAPE


def _build_prompt(db: Session, workspace_id: UUID, draft: ContentDraft) -> str:
    """Compose an image prompt from the draft plus workspace brand context.

    We ask for a clean, on-brand marketing visual with NO text — models render
    text unreliably, and a garbled headline ruins the asset."""

    from app.models.onboarding_profile import OnboardingProfile

    profile = (
        db.query(OnboardingProfile)
        .filter(OnboardingProfile.workspace_id == workspace_id)
        .first()
    )
    business = (profile.business_name if profile and profile.business_name else "").strip()
    industry = (profile.industry if profile and profile.industry else "").strip()

    platform = get_platform(draft.platform) if draft.platform else None
    surface = platform.label if platform else "social media"

    # A short subject line — the draft title, else the first line of the body.
    subject = (draft.title or "").strip()
    if not subject:
        subject = next(
            (ln.strip() for ln in (draft.body or "").splitlines() if ln.strip()),
            "the topic",
        )
    subject = subject[:200]

    context_bits = [b for b in (business, industry) if b]
    context = f" for {', '.join(context_bits)}" if context_bits else ""

    return (
        f"A polished, editorial marketing image for a {surface} post{context}. "
        f"Theme: {subject}. "
        "Modern, clean, high-quality photography or tasteful illustration with "
        "strong focal composition and brand-friendly lighting. "
        "Do NOT include any text, words, letters, logos, watermarks, or UI. "
        "No collage, no borders. Leave calm negative space so a caption could "
        "sit alongside it."
    )


def generate_for_draft(
    db: Session,
    *,
    workspace_id: UUID,
    draft_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    request: Request | None = None,
) -> ContentDraft:
    """Generate + persist one image for a draft, returning the updated draft.

    Charges image-generation credits, records a usage event, and writes an
    audit log. Spending money on an image is a Marketer+ action."""

    require_role_at_least(actor_role, Role.MARKETER)

    draft = content_draft_service.get_draft(
        db, workspace_id=workspace_id, draft_id=draft_id
    )

    client = _resolve_openai_client(db, workspace_id)
    if client is None or not client.is_configured():
        raise ImageProviderNotConfiguredError(
            "Connect an OpenAI API key (Settings → AI providers) to generate images."
        )

    billing_service.assert_within_image_generation_limit(db, workspace_id=workspace_id)

    prompt = _build_prompt(db, workspace_id, draft)
    size = _image_size_for(draft)

    try:
        result: ImageResult = client.generate_image(prompt=prompt, size=size)
    except (LlmError, LlmNotConfiguredError) as exc:
        raise ImageGenerationError(str(exc)) from exc

    # gpt-image → bytes we host ourselves; dall-e → a (temporary) URL.
    if result.image_bytes:
        saved = image_upload_service.save_image_bytes(
            workspace_id=workspace_id,
            data=result.image_bytes,
            content_type=result.content_type or "image/png",
        )
        image_url = saved["url"]
    elif result.url:
        image_url = result.url
    else:
        raise ImageGenerationError("Image provider returned neither bytes nor a URL.")

    draft.image_url = image_url
    meta = dict(draft.seo_metadata or {})
    meta["image_model"] = result.model
    meta["image_size"] = size
    draft.seo_metadata = meta

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="content_draft.image_generated",
        resource_type="content_draft",
        resource_id=draft.id,
        metadata={"model": result.model, "size": size, "platform": draft.platform},
        request=request,
    )
    billing_service.record_usage_event(
        db,
        workspace_id=workspace_id,
        event_type=UsageEventType.IMAGE_GENERATION,
        metadata={"model": result.model, "size": size, "draft_id": str(draft.id)},
    )

    db.commit()
    db.refresh(draft)
    return draft
