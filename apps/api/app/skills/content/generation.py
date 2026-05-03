"""Content drafting skill.

Generates a draft for the requested content type using the configured LLM.
If no LLM is configured the skill falls back to a deterministic template
populated from the workspace's onboarding profile, so the surface area still
returns a *real* artifact (per the production-rule "honest empty states")
rather than fabricating numbers or facts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.llm import (
    LlmClient,
    LlmError,
    LlmMessage,
    LlmNotConfiguredError,
    get_llm_client,
    get_llm_client_for_workspace,
)
from app.models.content_draft import ContentDraftType
from app.models.onboarding_profile import OnboardingProfile


def _resolve_client(db, workspace_id):
    """Pick the workspace's BYOK client when both db + workspace_id are
    available; fall back to the env-backed singleton otherwise."""
    if db is not None and workspace_id is not None:
        return get_llm_client_for_workspace(db, workspace_id)
    return get_llm_client()

# How long the body should be by content type (used as a soft hint to the model
# and as a trim ceiling on the deterministic fallback).
TARGET_BODY_LENGTH: dict[ContentDraftType, tuple[int, int]] = {
    ContentDraftType.BLOG_POST: (600, 1100),
    ContentDraftType.LANDING_PAGE: (300, 600),
    ContentDraftType.AD_COPY: (60, 180),
    ContentDraftType.META_DESCRIPTION: (110, 155),
    ContentDraftType.EMAIL: (180, 380),
    ContentDraftType.SOCIAL_POST: (60, 240),
}


@dataclass
class ContentRequest:
    type: ContentDraftType
    topic: str
    keywords: list[str]
    target_url: str | None
    audience: str | None
    notes: str | None


@dataclass
class ContentDraftPayload:
    title: str
    body: str
    seo_metadata: dict[str, Any]
    keywords: list[str]
    model_used: str | None
    source: str  # "llm" | "deterministic"


@dataclass
class RefreshRequest:
    type: ContentDraftType
    existing_title: str
    existing_body: str
    instructions: str | None  # e.g., "Update for 2026 stats", "Tighten the intro"
    keywords: list[str]
    target_url: str | None


def refresh_content_draft(
    *,
    request: RefreshRequest,
    profile: OnboardingProfile | None,
    llm: LlmClient | None = None,
    db: Session | None = None,
    workspace_id: UUID | None = None,
) -> ContentDraftPayload:
    """Take an existing piece of content and rewrite it.

    Uses the LLM when configured. Without an LLM, applies a deterministic
    "lightly edited" pass — appends a refresh notice, normalizes whitespace,
    keeps the substance intact. Honest fallback rather than fabrication."""

    client = llm or _resolve_client(db, workspace_id)
    if client.is_configured():
        try:
            return _refresh_with_llm(
                client=client,
                request=request,
                profile=profile,
                db=db,
                workspace_id=workspace_id,
            )
        except (LlmError, LlmNotConfiguredError, AdVantaError):
            pass
    return _refresh_deterministic(request=request, profile=profile)


def _refresh_with_llm(
    *,
    client: LlmClient,
    request: RefreshRequest,
    profile: OnboardingProfile | None,
    db: Session | None = None,
    workspace_id: UUID | None = None,
) -> ContentDraftPayload:
    voice = (profile.brand_voice if profile and profile.brand_voice else "Professional, concrete, no fluff.")
    business = (
        f"{profile.business_name}" if profile and profile.business_name else "this business"
    )
    target_low, target_high = TARGET_BODY_LENGTH[request.type]

    system = (
        f"You are AdVanta AI's content refresher for {business}. Brand voice: "
        f"{voice}. Rewrite the user's existing content per their instructions, "
        "preserving any specific facts unless they're flagged for replacement. "
        "Do not invent metrics, customer names, or claims. Return strict JSON "
        "with keys: title, body, meta_title, meta_description, keywords."
    )
    user_lines = [
        f"Content type: {request.type.value}",
        f"Target body length: {target_low}-{target_high} characters",
        f"Existing title: {request.existing_title}",
        f"Existing body:\n{request.existing_body}",
    ]
    if request.instructions:
        user_lines.append(f"Refresh instructions: {request.instructions}")
    if request.keywords:
        user_lines.append(f"Keep these keywords prominent: {', '.join(request.keywords)}")
    if request.target_url:
        user_lines.append(f"Target URL (don't change): {request.target_url}")
    user_lines.append('Return: {"title":"...","body":"...","meta_title":"...","meta_description":"...","keywords":[...]}')

    msgs = [
        LlmMessage(role="system", content=system),
        LlmMessage(role="user", content="\n".join(user_lines)),
    ]
    if db is not None and workspace_id is not None:
        completion = client.complete_metered(
            db=db,
            workspace_id=workspace_id,
            messages=msgs,
            max_tokens=1600,
            temperature=0.4,
            purpose="content_refresh",
        )
    else:
        completion = client.complete(messages=msgs, max_tokens=1600, temperature=0.4)

    parsed = _parse_payload(completion.text)
    title = (parsed.get("title") or request.existing_title).strip()
    body = (parsed.get("body") or "").strip()
    if not body:
        raise LlmError("Refresh produced an empty body.")

    seo = {
        "meta_title": (parsed.get("meta_title") or title)[:70].strip(),
        "meta_description": (parsed.get("meta_description") or "")[:160].strip(),
    }
    kws = parsed.get("keywords")
    if not isinstance(kws, list):
        kws = list(request.keywords)
    return ContentDraftPayload(
        title=title[:512],
        body=body,
        seo_metadata=seo,
        keywords=[str(k) for k in kws][:20],
        model_used=completion.model,
        source="llm_refresh",
    )


def _refresh_deterministic(
    *,
    request: RefreshRequest,
    profile: OnboardingProfile | None,
) -> ContentDraftPayload:
    """Without an LLM we don't fabricate updated content. Surface the
    original verbatim with a refresh banner so the user sees what they
    started from and can edit by hand."""

    business = profile.business_name if profile and profile.business_name else "Your team"
    instructions_line = (
        f"\n\n> [Refresh requested: {request.instructions}]\n"
        if request.instructions
        else "\n\n> [Refresh requested.]\n"
    )
    body = request.existing_body + instructions_line + (
        f"\n_Refreshed copy below — replace this banner._\n\n"
        f"{request.existing_body}"
    )
    return ContentDraftPayload(
        title=f"{request.existing_title} (refreshed)"[:512],
        body=body,
        seo_metadata={
            "meta_title": request.existing_title[:70],
            "meta_description": (request.instructions or "Refreshed content")[:160],
        },
        keywords=request.keywords[:20],
        model_used=None,
        source="deterministic_refresh",
    )


def generate_content_draft(
    *,
    request: ContentRequest,
    profile: OnboardingProfile | None,
    llm: LlmClient | None = None,
    db: Session | None = None,
    workspace_id: UUID | None = None,
) -> ContentDraftPayload:
    """Produce a draft. When `db` + `workspace_id` are provided, the LLM call
    is metered + plan-gated; once the workspace hits its LLM token cap we
    fall back to the deterministic template rather than raising."""

    client = llm or _resolve_client(db, workspace_id)
    if client.is_configured():
        try:
            return _generate_with_llm(
                client=client,
                request=request,
                profile=profile,
                db=db,
                workspace_id=workspace_id,
            )
        except (LlmError, LlmNotConfiguredError, AdVantaError):
            # AdVantaError catches PlanLimitExceededError specifically so a
            # capped workspace gets a draft via the deterministic path
            # instead of a 402.
            pass
    return _generate_deterministic(request=request, profile=profile)


# ---------------------------------------------------------------------------
# LLM path
# ---------------------------------------------------------------------------


def _system_prompt(profile: OnboardingProfile | None) -> str:
    voice = (profile.brand_voice or "Professional, concrete, no fluff.") if profile else "Professional, concrete, no fluff."
    business = (
        f"{profile.business_name} ({profile.industry or 'unknown industry'})"
        if profile and profile.business_name
        else "this business"
    )
    audience = (profile and profile.target_audience) or "the company's primary audience"
    offer = (profile and profile.offer_description) or "the product the user described"
    return (
        "You are AdVanta AI's content drafter. Produce a single draft for the requested "
        f"content type for {business}. Target audience: {audience}. Offer: {offer}. "
        f"Brand voice: {voice}. Do not invent metrics, customer names, or claims you can't "
        "support. Return strict JSON with keys: title (string), body (string), "
        "meta_title (string), meta_description (string), keywords (array of strings)."
    )


def _user_prompt(request: ContentRequest) -> str:
    target_low, target_high = TARGET_BODY_LENGTH[request.type]
    parts = [
        f"Content type: {request.type.value}",
        f"Topic: {request.topic}",
        f"Keywords to weave in: {', '.join(request.keywords) if request.keywords else '(none)'}",
        f"Body length target: roughly {target_low}-{target_high} characters",
    ]
    if request.target_url:
        parts.append(f"Target URL: {request.target_url}")
    if request.audience:
        parts.append(f"Audience focus: {request.audience}")
    if request.notes:
        parts.append(f"Notes: {request.notes}")
    parts.append('Return JSON of the form: {"title":"...","body":"...","meta_title":"...","meta_description":"...","keywords":[...]}')
    return "\n".join(parts)


def _generate_with_llm(
    *,
    client: LlmClient,
    request: ContentRequest,
    profile: OnboardingProfile | None,
    db: Session | None = None,
    workspace_id: UUID | None = None,
) -> ContentDraftPayload:
    messages = [
        LlmMessage(role="system", content=_system_prompt(profile)),
        LlmMessage(role="user", content=_user_prompt(request)),
    ]
    if db is not None and workspace_id is not None:
        completion = client.complete_metered(
            db=db,
            workspace_id=workspace_id,
            messages=messages,
            max_tokens=1400,
            temperature=0.5,
            purpose="content_draft",
        )
    else:
        completion = client.complete(messages=messages, max_tokens=1400, temperature=0.5)

    parsed = _parse_payload(completion.text)
    title = (parsed.get("title") or request.topic).strip()
    body = (parsed.get("body") or "").strip()
    if not body:
        raise LlmError("LLM produced an empty body.")

    seo = {
        "meta_title": (parsed.get("meta_title") or title)[:70].strip(),
        "meta_description": (parsed.get("meta_description") or "")[:160].strip(),
    }
    kws = parsed.get("keywords")
    if not isinstance(kws, list):
        kws = list(request.keywords)
    return ContentDraftPayload(
        title=title[:512],
        body=body,
        seo_metadata=seo,
        keywords=[str(k) for k in kws][:20],
        model_used=completion.model,
        source="llm",
    )


def _parse_payload(text: str) -> dict[str, Any]:
    import json

    body = text.strip()
    if body.startswith("```"):
        lines = body.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        body = "\n".join(lines)
    if not body.startswith("{") and "{" in body:
        body = body[body.index("{") :]
    try:
        return json.loads(body)
    except ValueError as exc:
        raise LlmError(f"Could not parse LLM JSON output: {exc}") from exc


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------


def _generate_deterministic(
    *,
    request: ContentRequest,
    profile: OnboardingProfile | None,
) -> ContentDraftPayload:
    business = (profile.business_name if profile and profile.business_name else "Your team")
    # Request-provided audience wins so the user's input is preserved verbatim.
    audience = (
        request.audience
        or (profile.target_audience if profile and profile.target_audience else "your prospects")
    )
    offer_line = (
        profile.offer_description if profile and profile.offer_description else None
    )

    title, body, meta_desc = _template_for_type(
        request=request,
        business=business,
        audience=audience,
        offer_line=offer_line,
    )
    keywords = list(request.keywords) or ([] if not request.topic else [request.topic])
    return ContentDraftPayload(
        title=title[:512],
        body=body,
        seo_metadata={
            "meta_title": title[:70],
            "meta_description": meta_desc[:160],
        },
        keywords=keywords[:20],
        model_used=None,
        source="deterministic",
    )


def _template_for_type(
    *,
    request: ContentRequest,
    business: str,
    audience: str,
    offer_line: str | None,
) -> tuple[str, str, str]:
    topic = request.topic.strip() or "Your next campaign"
    kw_phrase = ", ".join(request.keywords) if request.keywords else topic
    cta = "Talk to us" if request.target_url is None else f"Learn more at {request.target_url}"

    if request.type == ContentDraftType.BLOG_POST:
        title = f"{topic}: a practical guide"
        body = (
            f"{topic} matters because {audience} need clear, decision-grade information before they buy. "
            f"In this post we cover what {kw_phrase} means in practice and how {business} approaches it.\n\n"
            "## What we recommend\n\n"
            f"- Start with the smallest test that proves the value of {topic}.\n"
            "- Measure conversion at the moment of decision, not at the top of the funnel.\n"
            "- Tighten copy until each sentence either lowers risk or raises clarity.\n\n"
            "## Why it works\n\n"
            f"{offer_line or 'Our approach is built on the principle that prospects buy from teams that look honest, fast, and competent.'}\n\n"
            f"### Next step\n\n{cta}."
        )
        meta = f"{topic}: a practical guide for {audience}. {kw_phrase}."
    elif request.type == ContentDraftType.LANDING_PAGE:
        title = f"{topic} — built for {audience}"
        body = (
            f"# {topic}\n\nFor {audience}.\n\n"
            f"{offer_line or 'A focused way to move from interest to outcome.'}\n\n"
            "## Why teams choose us\n"
            f"- Clear pricing\n- Real examples\n- Fast time-to-value\n\n"
            f"### Get started\n{cta}"
        )
        meta = f"{topic} for {audience}. {offer_line or kw_phrase}."
    elif request.type == ContentDraftType.AD_COPY:
        title = f"Ad: {topic}"
        body = (
            f"Headline: {topic} for {audience}\n"
            f"Description: {offer_line or kw_phrase}. {cta}.\n"
            f"CTA: {cta}"
        )
        meta = f"{topic} ad copy."
    elif request.type == ContentDraftType.META_DESCRIPTION:
        title = topic
        body = (
            f"{topic} — built for {audience}. {offer_line or kw_phrase}. {cta}."
        )[:160]
        meta = body
    elif request.type == ContentDraftType.EMAIL:
        title = f"{topic} — quick note"
        body = (
            f"Hi,\n\n{topic} caught my attention because {audience} are increasingly asking about {kw_phrase}.\n\n"
            f"{offer_line or 'I think there is a reasonable fit between what we do and where your team is headed.'}\n\n"
            f"Worth a 15-minute conversation? {cta}.\n\nThanks,\n{business}"
        )
        meta = f"{topic} — outreach email."
    else:  # SOCIAL_POST
        title = f"Social: {topic}"
        body = (
            f"{topic}.\n\n"
            f"For {audience}: {offer_line or kw_phrase}.\n\n{cta}"
        )
        meta = f"{topic} for {audience}."

    return title, body, meta
