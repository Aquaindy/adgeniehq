"""Social content drafting skill.

Turns one topic/keyword set into platform-native copy: a post for text
platforms, a shot-by-shot script for vertical video. Every draft carries its
own keywords (search intent) and hashtags (reach), tuned to the platform's
conventions in `app/social/catalog.py`.

Like `skills/content/generation.py`, this degrades honestly: with no LLM
configured (or a workspace over its token cap) it returns a deterministic
skeleton built from the onboarding profile and the operator's own topic. It
never fabricates metrics, customer names, or social proof.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import AdGenieError
from app.llm import (
    LlmClient,
    LlmError,
    LlmMessage,
    LlmNotConfiguredError,
    get_llm_client,
    get_llm_client_for_workspace,
)
from app.models.onboarding_profile import OnboardingProfile
from app.social.catalog import SocialPlatform

# Cap on hashtags we keep even if the platform convention is generous and the
# model gets enthusiastic. Instagram permits 30; past ~15 it reads as spam.
_HASHTAG_CEILING = 15
# A tag longer than this is unusable — nobody searches it, and on X it would
# eat the whole 280-character budget. Drop rather than truncate: a truncated
# tag is a different (wrong) tag.
_MAX_HASHTAG_LENGTH = 40
_MAX_KEYWORDS = 20


@dataclass
class SocialContentRequest:
    platform: SocialPlatform
    topic: str
    keywords: list[str] = field(default_factory=list)
    audience: str | None = None
    target_url: str | None = None
    notes: str | None = None
    call_to_action: str | None = None
    # When the operator generates from a web link, the fetched article's title
    # and readable text are threaded in here. Present → the draft repurposes
    # this content instead of writing from the topic alone.
    source_url: str | None = None
    source_title: str | None = None
    source_content: str | None = None


@dataclass
class SocialContentPayload:
    title: str
    body: str
    hashtags: list[str]
    keywords: list[str]
    # Structured beats for video scripts; None for text posts.
    script: dict[str, Any] | None
    seo_metadata: dict[str, Any]
    model_used: str | None
    source: str  # "llm" | "deterministic"


def _resolve_client(db: Session | None, workspace_id: UUID | None) -> LlmClient:
    if db is not None and workspace_id is not None:
        return get_llm_client_for_workspace(db, workspace_id)
    return get_llm_client()


def generate_social_content(
    *,
    request: SocialContentRequest,
    profile: OnboardingProfile | None,
    llm: LlmClient | None = None,
    db: Session | None = None,
    workspace_id: UUID | None = None,
) -> SocialContentPayload:
    """Produce one platform-native draft. Metered + plan-gated when `db` and
    `workspace_id` are supplied; a capped workspace silently falls back to the
    deterministic skeleton rather than raising a 402."""

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
        except (LlmError, LlmNotConfiguredError, AdGenieError):
            # AdGenieError covers PlanLimitExceededError / InsufficientCredits.
            pass
    return _generate_deterministic(request=request, profile=profile)


# ---------------------------------------------------------------------------
# LLM path
# ---------------------------------------------------------------------------


def _system_prompt(
    platform: SocialPlatform,
    profile: OnboardingProfile | None,
    *,
    source_content: str | None = None,
) -> str:
    voice = (
        (profile.brand_voice if profile and profile.brand_voice else None)
        or "Professional, concrete, no fluff."
    )
    business = (
        f"{profile.business_name} ({profile.industry or 'unknown industry'})"
        if profile and profile.business_name
        else "this business"
    )
    audience = (profile and profile.target_audience) or "the company's primary audience"
    offer = (profile and profile.offer_description) or "the product the user described"

    base = (
        f"You are AdGenieHQ's social content strategist writing for {platform.label}. "
        f"Business: {business}. Audience: {audience}. Offer: {offer}. "
        f"Brand voice: {voice}.\n\n"
        f"Platform guidance: {platform.guidance}\n\n"
        "Never invent metrics, customer names, testimonials, awards, or claims "
        "you cannot support from the information given. Write as the business, "
        "not about it."
    )
    if source_content:
        base += (
            "\n\nThe user supplied a SOURCE ARTICLE (below the topic). Repurpose "
            "its substance into a native post for this platform — pull the "
            "strongest idea, stat, or takeaway from it and reframe it in the "
            "platform's voice. Draw only from the source and the business facts "
            "above; do not add claims the article doesn't support."
        )

    if platform.is_video:
        low, high = platform.duration_seconds or (20, 60)
        return (
            f"{base}\n\n"
            f"Produce a {low}-{high} second vertical ({platform.aspect_ratio}) "
            "short-form video script. Return strict JSON with keys: "
            "title (string), hook (string — the spoken first line, under 2 "
            "seconds), beats (array of objects with keys: narration, "
            "on_screen_text, visual), cta (string), hashtags (array of "
            "strings), keywords (array of strings). Use 3 to 5 beats."
        )

    low, high = platform.body_length
    limit_note = (
        f" The platform hard-caps posts at {platform.hard_char_limit} characters — "
        f"never exceed it."
        if platform.hard_char_limit
        else ""
    )
    hlow, hhigh = platform.hashtag_range
    return (
        f"{base}\n\n"
        f"Write one post of roughly {low}-{high} characters.{limit_note} "
        f"Include {hlow}-{hhigh} hashtags. Return strict JSON with keys: "
        "title (string — an internal label, not shown to readers), body "
        "(string — the post exactly as it should be pasted), hashtags "
        "(array of strings), keywords (array of strings)."
    )


def _user_prompt(request: SocialContentRequest) -> str:
    p = request.platform
    parts = [
        f"Platform: {p.label}",
        f"Topic: {request.topic or request.source_title or '(derive from the source article)'}",
        f"Keywords to weave in: {', '.join(request.keywords) if request.keywords else '(none)'}",
    ]
    if p.is_video:
        low, high = p.duration_seconds or (20, 60)
        parts.append(f"Target duration: {low}-{high} seconds ({p.aspect_ratio})")
    else:
        low, high = p.body_length
        parts.append(f"Body length target: roughly {low}-{high} characters")
        if p.hard_char_limit:
            parts.append(f"Hard character limit: {p.hard_char_limit}")
    hlow, hhigh = p.hashtag_range
    parts.append(f"Hashtag count: {hlow}-{hhigh}")
    if request.audience:
        parts.append(f"Audience focus: {request.audience}")
    if request.call_to_action:
        parts.append(f"Call to action: {request.call_to_action}")
    if request.target_url:
        parts.append(f"Link to promote: {request.target_url}")
    if request.notes:
        parts.append(f"Notes: {request.notes}")
    if request.source_content:
        # Kept last and clearly delimited so the model treats it as reference
        # material, not instructions.
        parts.append(
            "\nSOURCE ARTICLE to repurpose"
            + (f" (from {request.source_url})" if request.source_url else "")
            + ":\n"
            + "\"\"\"\n"
            + request.source_content
            + "\n\"\"\""
        )
    return "\n".join(parts)


def _generate_with_llm(
    *,
    client: LlmClient,
    request: SocialContentRequest,
    profile: OnboardingProfile | None,
    db: Session | None,
    workspace_id: UUID | None,
) -> SocialContentPayload:
    messages = [
        LlmMessage(
            role="system",
            content=_system_prompt(
                request.platform, profile, source_content=request.source_content
            ),
        ),
        LlmMessage(role="user", content=_user_prompt(request)),
    ]
    kwargs: dict[str, Any] = {
        "messages": messages,
        "max_tokens": 1200,
        "temperature": 0.7,
    }
    if db is not None and workspace_id is not None:
        completion = client.complete_metered(
            db=db,
            workspace_id=workspace_id,
            purpose=f"social_content.{request.platform.slug}",
            **kwargs,
        )
    else:
        completion = client.complete(**kwargs)

    parsed = _parse_payload(completion.text)

    if request.platform.is_video:
        script = _coerce_script(parsed, request=request)
        body = _render_script(script, platform=request.platform)
    else:
        script = None
        body = (parsed.get("body") or "").strip()
        if not body:
            raise LlmError("LLM produced an empty post body.")

    title = (parsed.get("title") or request.topic).strip()
    hashtags = normalize_hashtags(parsed.get("hashtags"), platform=request.platform)
    keywords = _normalize_keywords(parsed.get("keywords"), fallback=request.keywords)

    # Hashtags share the character budget on text platforms, so reserve their
    # room before trimming the body.
    body = _enforce_char_limit(
        body,
        platform=request.platform,
        reserved=_hashtag_block_length(hashtags),
    )

    return SocialContentPayload(
        title=title[:512],
        body=body,
        hashtags=hashtags,
        keywords=keywords,
        script=script,
        seo_metadata=_build_metadata(body=body, hashtags=hashtags, request=request),
        model_used=completion.model,
        source="llm",
    )


def _parse_payload(text: str) -> dict[str, Any]:
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
        parsed = json.loads(body)
    except ValueError as exc:
        raise LlmError(f"Could not parse LLM JSON output: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LlmError("LLM returned JSON that was not an object.")
    return parsed


def _coerce_script(
    parsed: dict[str, Any], *, request: SocialContentRequest
) -> dict[str, Any]:
    raw_beats = parsed.get("beats")
    if not isinstance(raw_beats, list) or not raw_beats:
        raise LlmError("LLM returned no beats for a video script.")

    beats: list[dict[str, str]] = []
    for raw in raw_beats[:6]:
        if not isinstance(raw, dict):
            continue
        narration = str(raw.get("narration") or "").strip()
        if not narration:
            continue
        beats.append(
            {
                "narration": narration,
                "on_screen_text": str(raw.get("on_screen_text") or "").strip(),
                "visual": str(raw.get("visual") or "").strip(),
            }
        )
    if not beats:
        raise LlmError("LLM returned beats with no narration.")

    hook = str(parsed.get("hook") or "").strip()
    if not hook:
        raise LlmError("LLM returned no hook for a video script.")

    cta = str(parsed.get("cta") or "").strip() or (
        request.call_to_action or "Follow for more."
    )
    low, high = request.platform.duration_seconds or (20, 60)
    return {
        "hook": hook,
        "beats": beats,
        "cta": cta,
        "aspect_ratio": request.platform.aspect_ratio,
        "target_duration_seconds": [low, high],
    }


def _render_script(script: dict[str, Any], *, platform: SocialPlatform) -> str:
    """Flatten the structured script into the readable body a creator shoots
    from. The structured form is preserved separately in seo_metadata so the
    UI can render beats as a table."""

    low, high = script.get("target_duration_seconds") or (20, 60)
    lines = [
        f"HOOK (0-2s): {script['hook']}",
        "",
    ]
    for i, beat in enumerate(script["beats"], start=1):
        lines.append(f"BEAT {i}")
        lines.append(f"  Narration: {beat['narration']}")
        if beat.get("on_screen_text"):
            lines.append(f"  On-screen: {beat['on_screen_text']}")
        if beat.get("visual"):
            lines.append(f"  Visual: {beat['visual']}")
        lines.append("")
    lines.append(f"CTA: {script['cta']}")
    lines.append("")
    lines.append(f"Format: {platform.aspect_ratio} vertical, {low}-{high}s")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


_NON_TAG_CHARS = re.compile(r"[^0-9A-Za-z_]+")


def normalize_hashtags(raw: Any, *, platform: SocialPlatform) -> list[str]:
    """Strip punctuation, dedupe case-insensitively, re-prefix with `#`, and
    trim to the platform's conventional ceiling."""

    if not isinstance(raw, list):
        return []
    limit = min(platform.hashtag_range[1], _HASHTAG_CEILING)
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        tag = _NON_TAG_CHARS.sub("", str(item))
        if not tag or len(tag) > _MAX_HASHTAG_LENGTH:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(f"#{tag}")
        if len(out) >= limit:
            break
    return out


def _normalize_keywords(raw: Any, *, fallback: list[str]) -> list[str]:
    source = raw if isinstance(raw, list) else fallback
    out: list[str] = []
    seen: set[str] = set()
    for item in source:
        kw = str(item).strip()
        if not kw:
            continue
        key = kw.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(kw)
        if len(out) >= _MAX_KEYWORDS:
            break
    return out


def _hashtag_block_length(hashtags: list[str]) -> int:
    """Characters the hashtags occupy when appended to the post, including the
    separating space. Zero when there are none."""

    if not hashtags:
        return 0
    return len(" ".join(hashtags)) + 1  # +1 for the space before the block


def _enforce_char_limit(
    body: str, *, platform: SocialPlatform, reserved: int = 0
) -> str:
    """Trim to the platform's hard ceiling on a word boundary. A post the
    composer would reject is worse than a slightly shorter one.

    `reserved` holds back room for text that shares the platform's budget but
    lives outside `body` — chiefly hashtags, which X counts inside its 280.
    The count is conservative for links: X shortens every URL to a fixed 23
    characters via t.co, while we count the raw string, so we may trim a few
    characters more than strictly necessary."""

    limit = platform.hard_char_limit
    if limit is None:
        return body
    budget = limit - max(0, reserved)
    if budget <= 0:
        # Pathological: hashtags alone blow the limit. Keep the post, let the
        # UI's over-limit warning surface it rather than returning "".
        return body
    if len(body) <= budget:
        return body
    clipped = body[:budget].rsplit(" ", 1)[0].rstrip()
    return clipped or body[:budget]


def _build_metadata(
    *, body: str, hashtags: list[str], request: SocialContentRequest
) -> dict[str, Any]:
    p = request.platform
    hashtag_chars = _hashtag_block_length(hashtags)
    meta: dict[str, Any] = {
        "platform": p.slug,
        "platform_label": p.label,
        "format": p.format.value,
        "character_count": len(body),
        "topic": request.topic,
    }
    if p.hard_char_limit:
        meta["character_limit"] = p.hard_char_limit
        # What the platform actually counts when the operator pastes the post
        # with its hashtags appended.
        meta["hashtag_character_count"] = hashtag_chars
        meta["composed_character_count"] = len(body) + hashtag_chars
    if p.is_video:
        meta["aspect_ratio"] = p.aspect_ratio
        meta["target_duration_seconds"] = list(p.duration_seconds or (20, 60))
    if request.target_url:
        meta["target_url"] = request.target_url
    if request.source_url:
        meta["source_url"] = request.source_url
    return meta


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------


def _slug_tag(text: str) -> str:
    """"paid ads" → "PaidAds"; "cpa" → "cpa".

    Capitalize the first letter of each word without lowercasing the rest, so
    acronyms survive: `str.title()` would turn "CPA" into "Cpa"."""

    words = [w for w in text.strip().split() if w]
    if not words:
        return ""
    if len(words) == 1:
        return _NON_TAG_CHARS.sub("", words[0])
    joined = "".join(w[:1].upper() + w[1:] for w in words)
    return _NON_TAG_CHARS.sub("", joined)


def _fallback_hashtags(request: SocialContentRequest) -> list[str]:
    """Derive tags from what the operator actually typed. We do not invent
    trending tags we have no data for."""

    seeds = [*request.keywords, request.topic]
    raw = [_slug_tag(s) for s in seeds if s and s.strip()]
    return normalize_hashtags(raw, platform=request.platform)


def _source_lead(source_content: str, *, max_chars: int) -> str:
    """The first substantive paragraph of the source, for the deterministic
    path. Without an LLM we don't rewrite — we honestly surface a lead excerpt
    the operator edits, rather than fabricating a repurposed post."""

    for block in source_content.split("\n\n"):
        candidate = " ".join(block.split()).strip()
        if len(candidate) >= 40:  # skip nav crumbs / one-word lines
            if len(candidate) > max_chars:
                candidate = candidate[:max_chars].rsplit(" ", 1)[0].rstrip() + "…"
            return candidate
    # Nothing substantial — fall back to a flattened prefix.
    flat = " ".join(source_content.split()).strip()
    return flat[:max_chars]


def generate_deterministic_social(
    *,
    request: SocialContentRequest,
    profile: OnboardingProfile | None,
) -> SocialContentPayload:
    """Build a draft without touching the LLM.

    Callers that already own an LLM budget (the Growth Content Studio makes one
    bundle call for every artifact) use this to get platform-native structure —
    limits, hashtags, script beats — without a second metered call per platform."""

    return _generate_deterministic(request=request, profile=profile)


def _generate_deterministic(
    *,
    request: SocialContentRequest,
    profile: OnboardingProfile | None,
) -> SocialContentPayload:
    p = request.platform
    # A plural noun phrase, so the templates below stay grammatical. "your
    # audience" would produce "what most your audience miss".
    audience = (
        request.audience
        or (profile.target_audience if profile and profile.target_audience else "growth teams")
    )
    offer = profile.offer_description if profile and profile.offer_description else None
    topic = (
        request.topic.strip()
        or (request.source_title or "").strip()
        or "Your next campaign"
    )
    kw_phrase = ", ".join(request.keywords) if request.keywords else topic
    cta = request.call_to_action or (
        f"Learn more: {request.target_url}" if request.target_url else "Follow for more."
    )

    hashtags = _fallback_hashtags(request)
    keywords = _normalize_keywords(request.keywords, fallback=[topic])

    # When repurposing a link, ground the skeleton in a real excerpt from the
    # page rather than the generic onboarding template.
    lead = _source_lead(request.source_content, max_chars=600) if request.source_content else ""

    if p.is_video:
        low, high = p.duration_seconds or (20, 60)
        first_beat = (
            lead
            if lead
            else f"{audience} keep hitting the same wall with {kw_phrase}."
        )
        script = {
            "hook": f"{topic} — here's what {audience} keep missing.",
            "beats": [
                {
                    "narration": first_beat,
                    "on_screen_text": topic,
                    "visual": "Talking head, direct to camera.",
                },
                {
                    "narration": offer
                    or "Here's the approach that actually moves the number.",
                    "on_screen_text": "The fix",
                    "visual": "Screen recording or B-roll of the workflow.",
                },
                {
                    "narration": "Show the change, don't claim it.",
                    "on_screen_text": "Before / after",
                    "visual": "Split screen.",
                },
            ],
            "cta": cta,
            "aspect_ratio": p.aspect_ratio,
            "target_duration_seconds": [low, high],
        }
        body = _render_script(script, platform=p)
        title = f"{p.label}: {topic}"
    else:
        script = None
        title = f"{p.label}: {topic}"
        middle = lead if lead else f"For {audience}: {offer or kw_phrase}."
        body = _enforce_char_limit(
            f"{topic}\n\n{middle}\n\n{cta}",
            platform=p,
            reserved=_hashtag_block_length(hashtags),
        )

    payload_meta = _build_metadata(body=body, hashtags=hashtags, request=request)
    payload_meta["fallback"] = (
        "Drafted from the source excerpt without an LLM — edit before posting. "
        "Connect an LLM key for a full platform-tuned rewrite."
        if lead
        else "Drafted from your onboarding profile without an LLM. "
        "Connect an LLM key for platform-tuned copy."
    )
    return SocialContentPayload(
        title=title[:512],
        body=body,
        hashtags=hashtags,
        keywords=keywords,
        script=script,
        seo_metadata=payload_meta,
        model_used=None,
        source="deterministic",
    )
