"""Growth Content Studio skill.

Turns a workspace's Growth DNA Profile into a bundle of ready-to-use copy
artifacts, one (or more) per section/segment of the profile:

  * Keyword plan          — paid search + SEO (from offer/industry/audience/geo)
  * Ad copy               — one set per recommended-first-campaign platform
  * Landing-page copy      — hero + benefits + CTA (from offer positioning)
  * Lifecycle emails       — one per Growth DNA email flow
  * Social hooks           — one set per content pillar
  * SEO meta tags          — homepage title tag + meta description

A single metered LLM call produces the whole bundle, grounded in the profile +
the already-generated marketing strategy. Without an LLM — or if the call fails,
returns malformed JSON, or the workspace is credit-capped — a deterministic
builder derives the same bundle from real onboarding inputs and the strategy
text (no fabricated metrics, customers, or claims), so the surface always
returns usable artifacts (per the production-rule "honest fallback").
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import AdGenieError
from app.llm.client import LlmError, LlmMessage, get_llm_client_for_workspace
from app.models.growth_dna_profile import GrowthDnaProfile
from app.models.onboarding_profile import OnboardingProfile
from app.models.suggested_copy import SuggestedCopyType
from app.skills.content.social import (
    SocialContentRequest,
    generate_deterministic_social,
    normalize_hashtags,
)
from app.social.catalog import SocialPlatform, get_platform

# Map LLM/string copy types onto the enum, tolerant of minor variations.
_TYPE_ALIASES = {
    "keywords": SuggestedCopyType.KEYWORDS,
    "keyword_plan": SuggestedCopyType.KEYWORDS,
    "ad_copy": SuggestedCopyType.AD_COPY,
    "ad": SuggestedCopyType.AD_COPY,
    "ads": SuggestedCopyType.AD_COPY,
    "landing_page": SuggestedCopyType.LANDING_PAGE,
    "landing": SuggestedCopyType.LANDING_PAGE,
    "email": SuggestedCopyType.EMAIL,
    "social_post": SuggestedCopyType.SOCIAL_POST,
    "social": SuggestedCopyType.SOCIAL_POST,
    "blog_outline": SuggestedCopyType.BLOG_OUTLINE,
    "blog": SuggestedCopyType.BLOG_OUTLINE,
    "meta_tags": SuggestedCopyType.META_TAGS,
    "meta": SuggestedCopyType.META_TAGS,
    "short_video_script": SuggestedCopyType.SHORT_VIDEO_SCRIPT,
    "video_script": SuggestedCopyType.SHORT_VIDEO_SCRIPT,
    "reel": SuggestedCopyType.SHORT_VIDEO_SCRIPT,
    "short": SuggestedCopyType.SHORT_VIDEO_SCRIPT,
}

# Growth DNA names its recommended platforms for humans ("X / Twitter"); the
# social catalog keys on slugs. Anything unmapped is simply skipped — "YouTube"
# means long-form video, which the short-form catalog deliberately doesn't cover.
_PLATFORM_ALIASES = {
    "linkedin": "linkedin",
    "facebook": "facebook",
    "instagram": "instagram",
    "instagram reels": "instagram_reels",
    "pinterest": "pinterest",
    "threads": "threads",
    "tiktok": "tiktok",
    "x": "x",
    "x / twitter": "x",
    "twitter": "x",
    "x (twitter)": "x",
    "youtube shorts": "youtube_shorts",
}

# When the Growth DNA recommends no platform our catalog covers (e.g. a
# YouTube-only long-form plan), fall back to the broadest organic surface
# rather than emitting nothing.
_FALLBACK_PLATFORM = "linkedin"


@dataclass
class GeneratedCopy:
    copy_type: SuggestedCopyType
    section: str
    title: str
    body: str
    # Social artifacts only. `platform` is a catalog slug; `hashtags` are
    # normalized and "#"-prefixed.
    platform: str | None = None
    hashtags: list[str] | None = None


@dataclass
class CopyBundle:
    copies: list[GeneratedCopy]
    source: str          # "llm" | "deterministic"
    model_used: str | None


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def generate_suggested_copies(
    db: Session,
    *,
    workspace_id: UUID,
    profile: OnboardingProfile,
    dna: GrowthDnaProfile,
    product_name: str,
) -> CopyBundle:
    """Produce the full copy bundle. LLM-tailored when configured + within
    budget; deterministic otherwise. Never raises on LLM problems — it degrades
    to the deterministic builder."""
    llm = get_llm_client_for_workspace(db, workspace_id)
    if llm.is_configured():
        try:
            copies, model = _bundle_via_llm(
                db,
                workspace_id=workspace_id,
                profile=profile,
                dna=dna,
                product_name=product_name,
            )
            if copies:
                return CopyBundle(copies=copies, source="llm", model_used=model)
        except (LlmError, AdGenieError, ValueError):
            # PlanLimitExceededError (an AdGenieError) lands here too, so a
            # credit-capped workspace gets the deterministic bundle, not a 402.
            pass
    return CopyBundle(
        copies=_bundle_deterministic(profile=profile, dna=dna, product_name=product_name),
        source="deterministic",
        model_used=None,
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _clean(text: str | None, *, fallback: str = "") -> str:
    return " ".join(str(text).split()) if text and str(text).strip() else fallback


def _first_sentence(text: str | None, *, max_len: int = 160) -> str:
    raw = _clean(text)
    if not raw:
        return ""
    for sep in (". ", "! ", "? ", "\n"):
        if sep in raw:
            raw = raw.split(sep)[0]
            break
    return raw[:max_len].rstrip(" ,.;:-")


def _recommended_campaigns(dna: GrowthDnaProfile) -> list[dict]:
    rows = dna.recommended_first_campaigns or []
    if isinstance(rows, list) and rows:
        return [r for r in rows if isinstance(r, dict)]
    return [
        {"platform": "Google Ads", "objective": "Capture high-intent search demand"},
        {"platform": "Meta Ads", "objective": "Build problem-aware demand + retarget warm visitors"},
    ]


def _content_pillars(dna: GrowthDnaProfile) -> list[dict]:
    ms = dna.marketing_strategy or {}
    pillars = ms.get("content_pillars") or []
    return [p for p in pillars if isinstance(p, dict)][:5]


def _copy_type_for(platform: SocialPlatform) -> SuggestedCopyType:
    """Video platforms yield a script; text platforms yield a post."""

    return (
        SuggestedCopyType.SHORT_VIDEO_SCRIPT
        if platform.is_video
        else SuggestedCopyType.SOCIAL_POST
    )


def _recommended_social_platforms(dna: GrowthDnaProfile) -> list[SocialPlatform]:
    """Resolve the Growth DNA's `platform_strategy` onto catalog platforms.

    Order is preserved so the highest-priority platform gets the first pillar."""

    ms = dna.marketing_strategy or {}
    resolved: list[SocialPlatform] = []
    for entry in ms.get("platform_strategy") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("platform") or "").strip().lower()
        slug = _PLATFORM_ALIASES.get(name)
        platform = get_platform(slug) if slug else None
        if platform is not None and platform not in resolved:
            resolved.append(platform)
    if not resolved:
        fallback = get_platform(_FALLBACK_PLATFORM)
        if fallback is not None:
            resolved.append(fallback)
    return resolved


def _pillar_topic(pillar: dict, product_name: str) -> str:
    """The strongest available hook becomes the topic; the pillar name is the
    fallback. Hooks are already business-specific, so they generate better."""

    hooks = [h for h in (pillar.get("example_hooks") or []) if _clean(h)]
    if hooks:
        return _clean(hooks[0])
    name = _clean(pillar.get("name"), fallback="Content")
    return f"{name} — {product_name}"


def _social_organic(
    p: OnboardingProfile,
    product_name: str,
    pillar: dict,
    platform: SocialPlatform,
) -> GeneratedCopy:
    """One platform-native organic artifact for a content pillar.

    Reuses the social skill's deterministic builder so the result honors the
    platform's character ceiling, hashtag conventions, and — for TikTok/Reels/
    Shorts — the hook/beats/CTA script shape."""

    name = _clean(pillar.get("name"), fallback="Content")
    keywords = [h for h in (pillar.get("example_hooks") or []) if _clean(h)][:2]

    payload = generate_deterministic_social(
        request=SocialContentRequest(
            platform=platform,
            topic=_pillar_topic(pillar, product_name),
            keywords=[_clean(k) for k in keywords],
            audience=_clean(p.target_audience) or None,
            target_url=_clean(p.website_url) or None,
            notes=_clean(pillar.get("description")) or None,
        ),
        profile=p,
    )

    kind = "Short video" if platform.is_video else "Post"
    return GeneratedCopy(
        copy_type=_copy_type_for(platform),
        section=f"Organic social — {platform.label}: {name}",
        title=f"{kind} — {platform.label} · {name}",
        body=payload.body,
        platform=platform.slug,
        hashtags=payload.hashtags,
    )


def _email_flows(dna: GrowthDnaProfile) -> list[dict]:
    ms = dna.marketing_strategy or {}
    flows = (ms.get("email_strategy") or {}).get("flows") or []
    return [f for f in flows if isinstance(f, dict)][:4]


# ---------------------------------------------------------------------------
# LLM path — one structured call returns the whole bundle
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are AdGenieHQ's Growth Content Studio — a senior performance copywriter. "
    "Given a business profile and its marketing strategy, produce a bundle of "
    "ready-to-use copy artifacts, one or more per requested section. Ground every "
    "line in the business's ACTUAL offer, audience, and outcomes. Do NOT invent "
    "metrics, customer names, testimonials, or claims you can't support — leave a "
    "clearly-marked [placeholder] where a real proof point belongs. Match the brand "
    "voice. Return STRICT JSON only (no prose, no code fences) of the form:\n"
    '{"copies": [{"copy_type": str, "section": str, "title": str, "body": str, '
    '"platform": str|null, "hashtags": [str]|null}, ...]}\n'
    "copy_type MUST be one of: keywords, ad_copy, landing_page, email, social_post, "
    "short_video_script, meta_tags. `body` is plain text and may use simple markdown "
    "(## headings, - bullets). "
    "Produce: ONE keywords plan (grouped: brand, problem, solution/category, competitor, "
    "long-tail); ONE ad_copy set per recommended platform (3 headlines + 2 descriptions + "
    "1 CTA each); ONE landing_page (hero headline, subhead, 3 benefit bullets, CTA); ONE "
    "email per email flow (subject line + body); ONE organic social artifact per content "
    "pillar; ONE meta_tags (title tag <=60 chars + meta description <=155 chars).\n"
    "ORGANIC SOCIAL rules — one artifact per content pillar, assigned to a platform from "
    "`organic_social_platforms` (rotate through them, do not reuse one platform for every "
    "pillar):\n"
    "- Set `platform` to that entry's `slug` and `hashtags` to a list WITHOUT the leading #.\n"
    "- For a text platform (`format` = post): copy_type is social_post and `body` is the post "
    "exactly as it should be pasted, within the entry's `hard_char_limit` INCLUDING the "
    "hashtags, honoring its `hashtag_range`.\n"
    "- For a video platform (`format` = video_script): copy_type is short_video_script and "
    "`body` is a shot-by-shot script — a hook in the first 2 seconds, 3-5 beats each with "
    "narration plus on-screen text, then a CTA — sized to the entry's duration.\n"
    "Be concrete and concise; do not pad."
)


def _bundle_via_llm(
    db: Session,
    *,
    workspace_id: UUID,
    profile: OnboardingProfile,
    dna: GrowthDnaProfile,
    product_name: str,
) -> tuple[list[GeneratedCopy], str | None]:
    llm = get_llm_client_for_workspace(db, workspace_id)
    ms = dna.marketing_strategy or {}
    facts = {
        "product_name": product_name,
        "industry": profile.industry,
        "website_url": profile.website_url,
        "target_audience": profile.target_audience,
        "offer_description": profile.offer_description,
        "pain_points": profile.pain_points,
        "primary_conversion_goal": profile.primary_conversion_goal,
        "geographic_target": profile.geographic_target,
        "brand_voice": profile.brand_voice,
        "offer_positioning": dna.offer_positioning,
        "competitors": [
            c.get("name") if isinstance(c, dict) else c
            for c in (profile.competitors or [])
        ][:6],
        "recommended_campaigns": [
            {"platform": c.get("platform"), "objective": c.get("objective")}
            for c in _recommended_campaigns(dna)
        ],
        "content_pillars": [p.get("name") for p in _content_pillars(dna)],
        "email_flows": [
            {"name": f.get("name"), "trigger": f.get("trigger"), "goal": f.get("goal")}
            for f in _email_flows(dna)
        ],
        # Authoring constraints travel with the platform list so the model
        # writes within each network's real limits instead of guessing.
        "organic_social_platforms": [
            {
                "slug": sp.slug,
                "label": sp.label,
                "format": sp.format.value,
                "hard_char_limit": sp.hard_char_limit,
                "hashtag_range": list(sp.hashtag_range),
                "duration_seconds": list(sp.duration_seconds) if sp.duration_seconds else None,
                "guidance": sp.guidance,
            }
            for sp in _recommended_social_platforms(dna)
        ],
        "business_model": (ms.get("overview") or {}).get("model"),
    }
    user = LlmMessage(
        role="user",
        content=(
            "BUSINESS + STRATEGY (JSON):\n"
            + json.dumps(facts, ensure_ascii=False)
            + "\n\nReturn the copy bundle as JSON only."
        ),
    )
    completion = llm.complete_metered(
        db=db,
        workspace_id=workspace_id,
        messages=[LlmMessage(role="system", content=_SYSTEM_PROMPT), user],
        max_tokens=6000,
        temperature=0.6,
        purpose="growth_content.copies",
    )
    data = _coerce_json(completion.text)
    raw = data.get("copies") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        raise LlmError("Copy studio LLM did not return a 'copies' array.")

    social_types = {
        SuggestedCopyType.SOCIAL_POST,
        SuggestedCopyType.SHORT_VIDEO_SCRIPT,
    }
    copies: list[GeneratedCopy] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        ctype = _TYPE_ALIASES.get(str(item.get("copy_type", "")).strip().lower())
        title = _clean(item.get("title"))
        body = str(item.get("body") or "").strip()
        if ctype is None or not title or not body:
            continue

        platform: SocialPlatform | None = None
        hashtags: list[str] | None = None
        if ctype in social_types:
            raw_slug = str(item.get("platform") or "").strip().lower()
            platform = get_platform(_PLATFORM_ALIASES.get(raw_slug, raw_slug))
            if platform is None:
                # The model named a platform we don't model. Keep the copy but
                # don't mislabel it — an unattributed social post is still useful.
                hashtags = None
            else:
                hashtags = normalize_hashtags(item.get("hashtags"), platform=platform)
                # Trust the model's format claim only where it agrees with the
                # catalog; a "post" for TikTok is a script by definition.
                ctype = _copy_type_for(platform)

        copies.append(
            GeneratedCopy(
                copy_type=ctype,
                section=_clean(item.get("section"), fallback=ctype.value)[:255],
                title=title[:512],
                body=body,
                platform=platform.slug if platform else None,
                hashtags=hashtags,
            )
        )
    if not copies:
        raise LlmError("Copy studio LLM produced no usable copies.")
    return copies, completion.model


def _coerce_json(text: str) -> dict:
    body = (text or "").strip()
    if body.startswith("```"):
        lines = body.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        body = "\n".join(lines)
    if not body.startswith("{") and "{" in body:
        body = body[body.index("{"):]
    if body.endswith("```"):
        body = body[: body.rindex("```")]
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("Copy studio LLM output was not a JSON object.")
    return parsed


# ---------------------------------------------------------------------------
# Deterministic builder — derived from real inputs + the strategy
# ---------------------------------------------------------------------------


def _bundle_deterministic(
    *,
    profile: OnboardingProfile,
    dna: GrowthDnaProfile,
    product_name: str,
) -> list[GeneratedCopy]:
    copies: list[GeneratedCopy] = []
    copies.append(_keywords(profile, product_name))
    for campaign in _recommended_campaigns(dna):
        copies.append(_ad_copy(profile, product_name, campaign))
    copies.append(_landing_page(profile, dna, product_name))
    for flow in _email_flows(dna):
        copies.append(_email(profile, product_name, flow))
    # Organic social: one platform-native artifact per pillar, rotating through
    # the platforms the Growth DNA actually recommends. Rotating (rather than
    # pillar x platform) keeps the artifact count flat as platforms are added.
    platforms = _recommended_social_platforms(dna)
    for index, pillar in enumerate(_content_pillars(dna)):
        copies.append(
            _social_organic(profile, product_name, pillar, platforms[index % len(platforms)])
        )
    copies.append(_meta_tags(profile, product_name))
    return copies


def _keywords(p: OnboardingProfile, product_name: str) -> GeneratedCopy:
    industry = _clean(p.industry, fallback="your category")
    audience = _clean(p.target_audience, fallback="your buyers")
    geo = _clean(p.geographic_target)
    brand = product_name
    competitors = [
        _clean(c.get("name")) if isinstance(c, dict) else _clean(c)
        for c in (p.competitors or [])
    ]
    competitors = [c for c in competitors if c][:4]

    brand_kws = [brand, f"{brand} reviews", f"{brand} pricing", f"{brand} alternative"]
    problem_kws = [
        f"how to improve {industry.lower()}",
        f"best way to {_first_sentence(p.primary_conversion_goal, max_len=40).lower() or 'grow'}",
        f"{industry.lower()} problems",
    ]
    solution_kws = [
        f"best {industry.lower()} solution",
        f"{industry.lower()} for {audience.lower()[:40]}",
        f"{industry.lower()} software",
        f"{industry.lower()} tools",
    ]
    competitor_kws = [f"{c} alternative" for c in competitors] or [
        f"top {industry.lower()} companies"
    ]
    longtail = [
        f"{industry.lower()} for {audience.lower()[:30]}{(' in ' + geo) if geo else ''}",
        f"affordable {industry.lower()}",
        f"{industry.lower()} that works",
    ]

    def _bullets(items: list[str]) -> str:
        return "\n".join(f"- {kw}" for kw in items if kw)

    body = (
        f"Keyword plan for {product_name}. Group campaigns by intent; add negatives weekly.\n\n"
        f"## Brand\n{_bullets(brand_kws)}\n\n"
        f"## Problem / pain-aware\n{_bullets(problem_kws)}\n\n"
        f"## Solution / category\n{_bullets(solution_kws)}\n\n"
        f"## Competitor\n{_bullets(competitor_kws)}\n\n"
        f"## Long-tail / intent\n{_bullets(longtail)}"
    )
    return GeneratedCopy(
        copy_type=SuggestedCopyType.KEYWORDS,
        section="Paid Search & SEO",
        title=f"Keyword plan — {product_name}",
        body=body,
    )


def _ad_copy(p: OnboardingProfile, product_name: str, campaign: dict) -> GeneratedCopy:
    platform = _clean(campaign.get("platform"), fallback="Ads")
    objective = _clean(campaign.get("objective"))
    audience = _clean(p.target_audience, fallback="your buyers")
    industry = _clean(p.industry, fallback="your category")
    offer = _first_sentence(p.offer_description, max_len=90) or f"Built for {industry} teams"
    cta = "Get started"

    headlines = [
        f"Built for {industry}"[:30],
        f"For {audience[:24]}"[:30],
        "Less guessing, more growth"[:30],
    ]
    descriptions = [
        offer[:90],
        f"{product_name}: {objective or 'turn interest into customers'}."[:90],
    ]
    body = (
        f"{platform} ad copy for {product_name}."
        + (f" Objective: {objective}." if objective else "")
        + "\n\n## Headlines\n"
        + "\n".join(f"- {h}" for h in headlines)
        + "\n\n## Descriptions\n"
        + "\n".join(f"- {d}" for d in descriptions)
        + f"\n\n## CTA\n- {cta}"
    )
    return GeneratedCopy(
        copy_type=SuggestedCopyType.AD_COPY,
        section=f"Paid: {platform}",
        title=f"{platform} ad copy — {product_name}",
        body=body,
    )


def _landing_page(
    p: OnboardingProfile, dna: GrowthDnaProfile, product_name: str
) -> GeneratedCopy:
    audience = _clean(p.target_audience, fallback="your buyers")
    offer = _first_sentence(p.offer_description, max_len=140) or _first_sentence(
        dna.offer_positioning, max_len=140
    )
    goal = _first_sentence(p.primary_conversion_goal, max_len=60) or "get started"
    body = (
        f"# {product_name}\n\n"
        f"## Hero headline\nThe {_clean(p.industry, fallback='growth')} platform built for {audience}.\n\n"
        f"## Subhead\n{offer or 'A focused way to move from interest to outcome.'}\n\n"
        "## Benefit bullets\n"
        f"- Made for {audience} — not a generic, one-size tool.\n"
        "- Clear setup, fast time-to-value, no busywork.\n"
        "- [Add a proof point: result, metric, or customer logo].\n\n"
        "## Social proof\n[Add 1-2 real testimonials or recognizable logos here.]\n\n"
        f"## Primary CTA\n{goal.capitalize()} →\n\n"
        "## Secondary CTA\nSee how it works"
    )
    return GeneratedCopy(
        copy_type=SuggestedCopyType.LANDING_PAGE,
        section="Landing page / CRO",
        title=f"Landing page copy — {product_name}",
        body=body,
    )


def _email(p: OnboardingProfile, product_name: str, flow: dict) -> GeneratedCopy:
    name = _clean(flow.get("name"), fallback="Lifecycle email")
    trigger = _clean(flow.get("trigger"))
    goal = _clean(flow.get("goal"))
    audience = _clean(p.target_audience, fallback="there")
    offer = _first_sentence(p.offer_description, max_len=140)
    subject = f"{product_name}: {goal[:50]}" if goal else f"Welcome to {product_name}"
    body = (
        f"Flow: {name}." + (f" Trigger: {trigger}." if trigger else "")
        + (f" Goal: {goal}." if goal else "")
        + f"\n\n## Subject line\n{subject}\n\n"
        "## Preview text\n"
        f"{offer[:90] if offer else 'A quick note to help you get value fast.'}\n\n"
        "## Body\n"
        f"Hi {audience.split(' ')[0] if audience else 'there'},\n\n"
        f"{offer or f'Thanks for your interest in {product_name}.'}\n\n"
        f"{('Here is the next step: ' + goal + '.') if goal else 'Here is a simple next step to get value.'}\n\n"
        "[One clear CTA button →]\n\n"
        f"Thanks,\nThe {product_name} team"
    )
    return GeneratedCopy(
        copy_type=SuggestedCopyType.EMAIL,
        section=f"Email: {name}",
        title=f"{name} email — {product_name}",
        body=body,
    )


def _meta_tags(p: OnboardingProfile, product_name: str) -> GeneratedCopy:
    industry = _clean(p.industry, fallback="growth")
    audience = _clean(p.target_audience, fallback="teams")
    offer = _first_sentence(p.offer_description, max_len=120)
    host = ""
    if p.website_url:
        host = urlparse(p.website_url).netloc or ""
    title_tag = f"{product_name} — {industry} for {audience}"[:60]
    meta_desc = (offer or f"{product_name} helps {audience} with {industry}. Get started today.")[:155]
    body = (
        (f"Homepage meta tags for {host or product_name}.\n\n")
        + f"## Title tag (<=60 chars)\n{title_tag}\n\n"
        f"## Meta description (<=155 chars)\n{meta_desc}"
    )
    return GeneratedCopy(
        copy_type=SuggestedCopyType.META_TAGS,
        section="SEO meta tags",
        title=f"Homepage meta tags — {product_name}",
        body=body,
    )
