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

import re
from urllib.parse import urlparse
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


def _strip_platform_prefix(text: str, platform) -> str:
    """Drop a leading platform label used as a caption prefix — e.g.
    "LinkedIn post:", "X post -", "Instagram Reels script —".

    Belt-and-suspenders: the live prompt no longer names the platform, but this
    ensures such a label can never reach the model as text even if a title
    carries it (or a stray one slips through). Requires the label to be followed
    by "post"/"script" or a separator, so real titles like "LinkedIn posts that
    convert" are left untouched."""

    s = (text or "").strip()
    if not s or platform is None:
        return s
    label = re.escape(platform.label)
    for pattern in (
        rf"^{label}\s+(?:post|script)\b[\s:–—-]*",
        rf"^{label}\s*[:–—-]\s*",
    ):
        stripped = re.sub(pattern, "", s, count=1, flags=re.IGNORECASE).strip()
        if stripped and stripped != s:
            return stripped
    return s


def _overlay_headline(draft: ContentDraft) -> str:
    """The headline text to render ON a social image.

    Uses the draft's own TITLE (minus any platform label) so the image matches
    the content title the operator sees on the card — and differs per platform
    the way the titles do, instead of collapsing to one shared product hook.
    Capped at SEO-title length; the prompt's wrap/fit instruction handles
    sizing rather than aggressive truncation. Falls back to a stored
    `overlay_headline` only when there's no title."""

    raw = str(
        draft.title or (draft.seo_metadata or {}).get("overlay_headline") or ""
    ).strip()
    if not raw:
        return ""
    raw = _strip_platform_prefix(
        raw, get_platform(draft.platform) if draft.platform else None
    )
    if not raw:
        return ""
    if len(raw) > 70:  # backstop; wrap/fit in the prompt does the real work
        raw = raw[:70].rsplit(" ", 1)[0].strip() or raw[:70]
    return raw


def _promo_cta(draft: ContentDraft, profile) -> str:
    """CTA text for a product-cover image: the promoted link's domain, else the
    workspace website, else a short default. Kept short so it renders cleanly."""

    url = (draft.target_url or (getattr(profile, "website_url", None) or "") or "").strip()
    if url:
        netloc = urlparse(url if "://" in url else f"https://{url}").netloc
        domain = (netloc or url).replace("www.", "").strip("/")
        if domain:
            return f"Visit {domain}"
    return "Get instant access"


def _build_prompt(
    db: Session, workspace_id: UUID, draft: ContentDraft, *, style: str = "concept"
) -> str:
    """Compose an image prompt from the draft plus workspace brand context.

    For a social post we render a SHORT headline on the image as designed
    typography with supporting graphics (gpt-image renders short text reliably).
    `style="product"` instead composes a digital-product promo: the post title,
    a 3D ebook/product-box mockup, topical icon accents, and a CTA bar.
    Other surfaces (blog hero, landing page) stay text-free — a full headline
    there reads as a garbled caption."""

    from app.models.onboarding_profile import OnboardingProfile

    profile = (
        db.query(OnboardingProfile)
        .filter(OnboardingProfile.workspace_id == workspace_id)
        .first()
    )
    business = (profile.business_name if profile and profile.business_name else "").strip()
    industry = (profile.industry if profile and profile.industry else "").strip()

    platform = get_platform(draft.platform) if draft.platform else None

    # A short subject line — the draft title, else the first line of the body.
    subject = (draft.title or "").strip()
    if not subject:
        subject = next(
            (ln.strip() for ln in (draft.body or "").splitlines() if ln.strip()),
            "the topic",
        )
    subject = _strip_platform_prefix(subject, platform)[:200]

    context_bits = [b for b in (business, industry) if b]
    context = f" for {', '.join(context_bits)}" if context_bits else ""

    headline = _overlay_headline(draft) if platform is not None else ""

    if platform is not None and style == "product" and headline:
        cta = _promo_cta(draft, profile)
        box = (
            f"a photorealistic 3D ebook / software product-box mockup labelled "
            f"“{business}”"
            if business
            else "a photorealistic 3D ebook / software product-box mockup"
        )
        return (
            f"Design a premium, scroll-stopping social media promo graphic{context}. "
            f"Prominently render this post title as the bold, correctly spelled "
            f"focal headline: “{headline}”. Show the COMPLETE title — size and "
            f"wrap it across up to 3 lines so every word fits fully in frame "
            f"with margins; never crop or cut off any word. "
            f"Feature {box} as a hero element with soft reflections and depth. "
            f"Add a PROMINENT, clearly readable call-to-action button/bar near "
            f"the bottom — a solid rounded pill in an accent color — with the "
            f"text: “{cta}”. This CTA must always be present and legible. "
            f"Include a few tasteful, topical icon / emoji-style graphics and "
            f"accents that reinforce the theme. "
            f"Use this only as thematic direction, never as extra rendered text: "
            f"{subject}. "
            "Vibrant, high-contrast brand colors with real depth, dimension, "
            "studio lighting and a modern tech aesthetic; balanced, layered, "
            "premium composition. "
            "Lay out the title, product name, and CTA so each is fully visible "
            "and never cropped. "
            "Spell only the title, the product name, and the CTA EXACTLY as "
            "written; render NO other words, paragraphs, platform names, "
            "hashtags, watermarks, or UI."
        )

    if headline:
        cta = _promo_cta(draft, profile)
        return (
            f"Design a scroll-stopping social media post graphic{context}. "
            f"Exactly TWO text elements, both spelled EXACTLY as written: "
            f"(1) the headline as the bold, legible focal point — “{headline}” — "
            f"shown COMPLETE, sized and wrapped across up to 3 lines so every "
            f"word fits inside the frame with margins, never cropped; and "
            f"(2) a PROMINENT, clearly readable call-to-action bar/button near "
            f"the bottom — a solid rounded pill in an accent color — with the "
            f"text: “{cta}”. The CTA must always be present and legible. "
            f"Use this only as thematic direction for the imagery, never as "
            f"rendered text: {subject}. "
            "Support them with tasteful graphics — modern iconography, "
            "geometric shapes, or a clean illustration — using a vibrant, "
            "high-contrast color palette with real depth, dimension, and "
            "lighting (avoid flat, washed-out looks). "
            "Render NO other words beyond the headline and the CTA — no platform "
            "name, labels, hashtags, paragraphs, logos, watermarks, or UI. "
            "Balanced, professional composition."
        )

    # Non-social surfaces: clean, text-free marketing visual.
    return (
        f"A polished, editorial marketing image{context}. "
        f"Theme: {subject}. "
        "Modern, clean, high-quality photography or tasteful illustration with "
        "strong focal composition, vibrant color, depth, and brand-friendly "
        "lighting. "
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
    style: str = "concept",
    request: Request | None = None,
) -> ContentDraft:
    """Generate + persist one image for a draft, returning the updated draft.

    `style` is "concept" (headline + graphics) or "product" (a digital-product
    promo: title + 3D product-box mockup + CTA). Charges image-generation
    credits, records a usage event, and writes an audit log. Spending money on
    an image is a Marketer+ action."""

    require_role_at_least(actor_role, Role.MARKETER)

    style = "product" if str(style).lower() == "product" else "concept"

    draft = content_draft_service.get_draft(
        db, workspace_id=workspace_id, draft_id=draft_id
    )

    client = _resolve_openai_client(db, workspace_id)
    if client is None or not client.is_configured():
        raise ImageProviderNotConfiguredError(
            "Connect an OpenAI API key (Settings → AI providers) to generate images."
        )

    billing_service.assert_within_image_generation_limit(db, workspace_id=workspace_id)

    prompt = _build_prompt(db, workspace_id, draft, style=style)
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
    meta["image_style"] = style
    headline = _overlay_headline(draft) if draft.platform else ""
    if headline:
        meta["image_headline"] = headline
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
