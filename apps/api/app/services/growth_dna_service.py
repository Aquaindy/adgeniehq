"""Deterministic Growth DNA engine.

This generates the Growth DNA Profile from a workspace's onboarding inputs alone.
Every field is honestly derived from user-supplied data — no fabricated metrics, no
LLM-generated narrative passed off as facts. When an LLM is wired in (M4+), it will
augment the narrative fields and bump `engine_version` accordingly.
"""

from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.models.growth_dna_profile import GrowthDnaProfile
from app.models.onboarding_profile import OnboardingProfile

ENGINE_VERSION = "deterministic-v2"


class OnboardingIncompleteError(AdVantaError):
    status_code = 422
    code = "onboarding_incomplete"


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _bool_score(value: bool, weight: float) -> float:
    return weight if value else 0.0


def _has_text(value: str | None, *, min_chars: int = 1) -> bool:
    return bool(value and value.strip() and len(value.strip()) >= min_chars)


def _has_list(value: list | None) -> bool:
    return bool(value)


def _cap(text: str | None, max_len: int) -> str:
    """Collapse whitespace and truncate to a clean, single-line phrase."""
    if not text:
        return ""
    collapsed = " ".join(str(text).split())
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[: max_len - 1].rstrip(" ,.;:-") + "…"


def _short_goal(p: OnboardingProfile) -> str:
    """A concise, display-safe version of the primary conversion goal.

    Users often paste multi-paragraph goal descriptions during onboarding.
    We take the first line / first clause so campaign objectives stay readable
    instead of dumping the whole blob.
    """
    raw = (p.primary_conversion_goal or "").strip()
    if not raw:
        return "lead generation"
    first = raw.splitlines()[0].strip()
    for sep in (". ", " — ", " - ", "; ", ": ", " (", " — "):
        if sep in first:
            first = first.split(sep)[0].strip()
            break
    return _cap(first, 64) or "lead generation"


# ---------------------------------------------------------------------------
# Business-model inference — drives channel tailoring
# ---------------------------------------------------------------------------

_ECOMMERCE_SIGNALS = (
    "ecommerce", "e-commerce", "online store", "shopify", "woocommerce",
    "dtc", "d2c", "direct-to-consumer", "retail", "apparel", "cosmetic",
    "skincare", "beauty brand", "merch", "storefront", "cpg", "marketplace",
)
_B2B_SIGNALS = (
    "b2b", "saas", "enterprise", "agency", "agencies", "founder", "startup",
    "company", "companies", "business", "businesses", "team", "teams",
    "professional", "wholesale", "manufactur", "consult", "freelancer",
)
_B2C_SIGNALS = (
    "consumer", "individual", "student", "patient", "homeowner", "parent",
    "traveler", "fitness", "creator", "subscriber", "member", "shopper",
)


def _business_model(p: OnboardingProfile) -> str:
    """Coarse model bucket: 'ecommerce' | 'b2b' | 'b2c' | 'general'."""
    blob = " ".join(
        filter(None, [p.industry, p.target_audience, p.offer_description])
    ).lower()
    if not blob:
        return "general"
    # Explicit self-labels win over keyword inference — "B2C SaaS" is B2C even
    # though it contains "saas" (a B2B signal).
    if "b2c" in blob or "d2c" in blob or "b2b2c" in blob:
        return "b2c"
    if "b2b" in blob:
        return "b2b"
    if any(s in blob for s in _ECOMMERCE_SIGNALS):
        return "ecommerce"
    if any(s in blob for s in _B2B_SIGNALS):
        return "b2b"
    if any(s in blob for s in _B2C_SIGNALS):
        return "b2c"
    return "general"


def _budget_ceiling(p: OnboardingProfile) -> int:
    return int(p.monthly_ad_budget_max_usd or p.monthly_ad_budget_min_usd or 0)


def compute_funnel_readiness(p: OnboardingProfile) -> int:
    score = 0.0
    score += _bool_score(_has_text(p.target_audience), 0.15)
    score += _bool_score(_has_text(p.offer_description), 0.15)
    score += _bool_score(_has_text(p.pain_points), 0.10)
    score += _bool_score(_has_list(p.landing_page_urls), 0.15)
    score += _bool_score(_has_text(p.brand_voice), 0.10)
    score += _bool_score(p.analytics_status == "configured", 0.15)
    score += _bool_score(_has_text(p.offer_description, min_chars=80), 0.10)
    score += _bool_score(_has_list(p.competitors), 0.10)
    return round(score * 100)


def compute_paid_ads_readiness(p: OnboardingProfile) -> int:
    score = 0.0
    # Use the *minimum* budget bound for readiness — a range like $0–$5000
    # only counts as "ad-ready" if the floor is meaningful.
    budget_floor = p.monthly_ad_budget_min_usd or p.monthly_ad_budget_max_usd
    has_budget = budget_floor is not None and budget_floor >= 500
    score += _bool_score(has_budget, 0.20)
    score += _bool_score(_has_text(p.primary_conversion_goal), 0.15)
    score += _bool_score(_has_text(p.target_audience), 0.15)
    score += _bool_score(_has_text(p.geographic_target), 0.10)
    score += _bool_score(_has_list(p.current_ad_platforms), 0.15)
    score += _bool_score(p.analytics_status == "configured", 0.15)
    score += _bool_score(_has_list(p.landing_page_urls), 0.10)
    return round(score * 100)


# ---------------------------------------------------------------------------
# Narrative helpers — derived from inputs only
# ---------------------------------------------------------------------------

def build_business_summary(p: OnboardingProfile) -> str:
    pieces: list[str] = []
    if p.business_name:
        pieces.append(p.business_name)
    if p.industry:
        pieces.append(f"({p.industry})")
    if p.website_url:
        host = urlparse(p.website_url).netloc or p.website_url
        pieces.append(f"at {host}")

    header = " ".join(pieces) if pieces else "Your business"
    body = p.offer_description.strip() if p.offer_description else (
        "We don't have an offer description yet — add one in onboarding to sharpen targeting."
    )
    return f"{header}. {body}"


def build_icp_summary(p: OnboardingProfile) -> str:
    audience = (p.target_audience or "").strip()
    pain = (p.pain_points or "").strip()
    geo = (p.geographic_target or "").strip()

    if not audience and not pain:
        return (
            "ICP is not yet defined. Add a target audience and pain points in onboarding so "
            "the ICP & Persona Agent has something to work with."
        )

    parts: list[str] = []
    if audience:
        parts.append(f"Target audience: {audience}.")
    if pain:
        parts.append(f"Top pains heard from prospects: {pain}.")
    if geo:
        parts.append(f"Geographies: {geo}.")
    return " ".join(parts)


def build_offer_positioning(p: OnboardingProfile) -> str:
    if not p.offer_description:
        return "Add an offer description so we can score positioning clarity."
    text = p.offer_description.strip()
    if len(text) < 80:
        return (
            f"Current offer: \"{text}\". This is short — expanding to ~2–3 sentences makes "
            "ad angles and landing-page copy generation much stronger."
        )
    return f"Current offer: \"{text}\""


def build_seo_geo_summary(p: OnboardingProfile) -> str:
    if not p.website_url:
        return (
            "No website connected yet. SEO & GEO analysis runs after a site URL is provided "
            "and Search Console is connected."
        )
    host = urlparse(p.website_url).netloc or p.website_url
    return (
        f"Once Search Console is connected for {host}, the SEO & GEO Agent will surface "
        "keyword gaps, technical issues, and AI-search visibility opportunities. Expect a "
        "first opportunity scan within hours of connection."
    )


def build_website_risks(p: OnboardingProfile) -> list[str]:
    risks: list[str] = []
    if not p.landing_page_urls:
        risks.append("No landing pages provided — the Website Agent has no surface to audit yet.")
    if p.analytics_status != "configured":
        risks.append("Analytics is not fully configured — conversion data will be unreliable.")
    if not p.offer_description or len(p.offer_description.strip()) < 80:
        risks.append("Offer description is short — landing pages may lack clarity above the fold.")
    if not p.brand_voice:
        risks.append("Brand voice is undefined — generated copy will rely on category defaults.")
    if not p.target_audience:
        risks.append("Target audience is empty — messaging will be generic until this is set.")
    return risks


def build_tracking_readiness(p: OnboardingProfile) -> str:
    status = p.analytics_status
    if status == "configured":
        return (
            "Analytics is reported as configured. The Tracking Agent will validate pixel + "
            "conversion event quality during the integration setup pass."
        )
    if status == "partial":
        return (
            "Analytics is partially set up. Expect a tracking remediation task in the first "
            "week so the Budget Guardian has trustworthy data."
        )
    if status == "none":
        return (
            "No analytics in place. Tracking foundations (GA4 + conversion events) become the "
            "first task before any paid spend."
        )
    return (
        "Analytics status is unknown. The Tracking Agent will run a discovery audit before "
        "campaign work begins."
    )


# ---------------------------------------------------------------------------
# Recommendations + plan
# ---------------------------------------------------------------------------

PLATFORM_DISPLAY = {
    "google_ads": "Google Ads",
    "meta_ads": "Meta Ads",
    "linkedin_ads": "LinkedIn Ads",
    "tiktok_ads": "TikTok Ads",
    "microsoft_ads": "Microsoft Ads",
    "x_ads": "X Ads",
    "pinterest_ads": "Pinterest Ads",
    "other": "Other ad platform",
}

PLATFORM_OBJECTIVES = {
    "google_ads": "Captures high-intent search demand for solution-aware buyers.",
    "meta_ads": "Builds problem-aware demand and retargets site visitors.",
    "linkedin_ads": "Targets job titles + company size for B2B lead capture.",
    "tiktok_ads": "Reaches new audiences through short-form social proof.",
    "microsoft_ads": "Captures the Bing search slice often missed by Google-only stacks.",
    "x_ads": "Reaches engaged niche audiences with creator-style placements.",
    "pinterest_ads": "Hits high-intent buyers in lifestyle and home categories.",
    "other": "Allocate manually; we'll wire detailed analytics once the platform is supported.",
}

# Short, platform-specific objective frame. Combined with the (truncated)
# primary goal so each card reads as a distinct one-line objective instead of
# dumping the whole pasted goal description identically across every platform.
PLATFORM_OBJECTIVE_FRAME = {
    "google_ads": "Capture high-intent search demand",
    "meta_ads": "Build problem-aware demand + retarget warm visitors",
    "linkedin_ads": "Target B2B titles, seniority & company size",
    "tiktok_ads": "Reach new audiences with short-form creative",
    "microsoft_ads": "Capture the Bing / Edge search slice",
    "x_ads": "Engage niche communities & trending conversations",
    "pinterest_ads": "Reach high-intent lifestyle & shopping buyers",
    "other": "Test, measure, then scale the winners",
}


def build_campaign_recommendations(p: OnboardingProfile) -> list[dict]:
    platforms = p.current_ad_platforms or []
    if not platforms:
        # Conservative default: Google + Meta if no platforms picked yet.
        platforms = ["google_ads", "meta_ads"]

    goal = _short_goal(p)
    n = len(platforms)
    base_share = 100 // n if n else 0
    remainder = 100 - base_share * n if n else 0

    suggestions: list[dict] = []
    for idx, platform in enumerate(platforms):
        share = base_share + (1 if idx < remainder else 0)
        frame = PLATFORM_OBJECTIVE_FRAME.get(platform, "Test, measure, then scale the winners")
        suggestions.append(
            {
                "platform": PLATFORM_DISPLAY.get(platform, platform.replace("_", " ").title()),
                "objective": _cap(f"{frame} for {goal}", 120),
                "budget_share_pct": share,
                "rationale": PLATFORM_OBJECTIVES.get(platform, "Test, measure, then scale winners."),
            }
        )
    return suggestions


def build_thirty_day_plan(
    p: OnboardingProfile, *, funnel_score: int, paid_score: int
) -> list[dict]:
    foundation_first = funnel_score < 60 or paid_score < 60

    week1: list[str] = ["Connect Google Ads, Meta Ads, GA4, and Search Console."]
    if p.analytics_status != "configured":
        week1.append("Set up GA4 with conversion events for the primary goal.")
    if not p.landing_page_urls:
        week1.append("Identify or build a primary landing page for the offer.")
    if not p.offer_description or len(p.offer_description.strip()) < 80:
        week1.append("Tighten the offer description to 2–3 sentences.")

    week2: list[str]
    if foundation_first:
        week2 = [
            "Fix the highest-priority Website Agent risks before any spend.",
            "Run the Tracking Agent's pixel + event validation pass.",
            "Build first ad creative variants from the offer + ICP outputs.",
        ]
    else:
        platforms_label = ", ".join(
            PLATFORM_DISPLAY.get(plat, plat) for plat in (p.current_ad_platforms or ["google_ads", "meta_ads"])
        )
        week2 = [
            f"Launch first campaigns on {platforms_label} at modest daily budgets.",
            "Activate Budget Guardian rules: max daily spend, min ROAS threshold, stop-loss.",
            "Daily checks: anomaly detection, fatigue warnings, copy variant performance.",
        ]

    week3 = [
        "Pause underperforming ad sets; double budget on top performers (max +30% / day).",
        "SEO & GEO Agent ships first content + technical fixes from Search Console data.",
        "Website Agent drafts landing-page copy improvements based on conversion data.",
    ]

    week4 = [
        "Add a second platform or expand existing audiences with the winning angles.",
        "Reporting Agent ships the first monthly executive summary.",
        "Review Growth DNA: re-score readiness and lock the next month's plan.",
    ]

    return [
        {"week": 1, "focus": "Foundations & connections", "deliverables": week1},
        {"week": 2, "focus": "Launch (or finish foundations)", "deliverables": week2},
        {"week": 3, "focus": "Optimize", "deliverables": week3},
        {"week": 4, "focus": "Scale & report", "deliverables": week4},
    ]


# ---------------------------------------------------------------------------
# Comprehensive marketing strategy (full channel mix)
# ---------------------------------------------------------------------------
#
# This is the backbone of the Growth DNA Profile: a complete, cross-channel
# marketing playbook (paid, organic social, email/lifecycle, SEO, GEO, content,
# CRO, automation, referral, measurement) derived honestly from onboarding
# inputs. The same shape is produced by the LLM enhancer when a model is
# configured — so the UI renders identically whether the source is `ai` or
# `deterministic`.

# Organic social platform emphasis by business model.
_SOCIAL_PLATFORMS_BY_MODEL = {
    "b2b": [
        ("LinkedIn", "3–5×/week", "Thought leadership, customer proof, hiring/build-in-public"),
        ("X / Twitter", "Daily", "Industry takes, threads, founder POV"),
        ("YouTube", "1×/week", "Demos, webinars, long-form explainers"),
    ],
    "ecommerce": [
        ("Instagram", "Daily (posts + Reels)", "Product visuals, UGC reposts, results"),
        ("TikTok", "Daily", "Trends, unboxings, fast product demos"),
        ("Pinterest", "3–5×/week", "Shoppable pins, lookbooks, how-to"),
        ("Facebook", "4×/week", "Community, offers, retarget audiences"),
    ],
    "b2c": [
        ("Instagram", "Daily", "Lifestyle visuals, Reels, social proof"),
        ("TikTok", "Daily", "Trend-led discovery, short demos"),
        ("YouTube Shorts", "3×/week", "Evergreen tips, before/after"),
        ("Facebook", "4×/week", "Community + retargeting pool"),
    ],
    "general": [
        ("LinkedIn", "3×/week", "Authority, customer stories, hiring"),
        ("Instagram", "Daily", "Visual proof, Reels, behind-the-scenes"),
        ("YouTube", "1×/week", "Demos and evergreen tutorials"),
    ],
}

# Email lifecycle flows by business model.
_EMAIL_FLOWS_BY_MODEL = {
    "b2b": [
        ("Lead-magnet nurture", "New subscriber from a content/asset opt-in", "Move toward a demo or trial"),
        ("Trial / demo follow-up", "Started a trial or booked a demo", "Activation + sales-assist handoff"),
        ("Re-engagement", "No opens in 45 days", "Win back or sunset cold contacts"),
    ],
    "ecommerce": [
        ("Welcome + first purchase", "Newsletter or pop-up signup", "Convert subscriber to first order"),
        ("Abandoned cart", "Added to cart, no checkout in 1h/24h", "Recover the lost order"),
        ("Browse abandonment", "Viewed product, no add-to-cart", "Bring the shopper back"),
        ("Post-purchase + win-back", "Order delivered / 60d since last order", "Reviews, replenishment, reactivation"),
    ],
    "b2c": [
        ("Welcome / onboarding", "New account or signup", "Drive the first key action"),
        ("Engagement loop", "Completed onboarding", "Build the habit around your core value"),
        ("Re-engagement", "Dormant 30–45 days", "Reactivate before churn"),
    ],
    "general": [
        ("Welcome series", "New subscriber", "Introduce the offer and best content"),
        ("Nurture sequence", "Engaged with a lead magnet", "Build trust toward the primary conversion"),
        ("Re-engagement", "Inactive 45 days", "Win back or clean the list"),
    ],
}

# Content pillars + the 80/20 rule. Allocation percentages sum to 100.
_CONTENT_PILLARS_BY_MODEL = {
    "b2b": [
        ("Education & POV", 35, "Teach your buyer's job. Frameworks, myths, how-tos. Earns saves + authority."),
        ("Customer proof & results", 25, "Case studies, before/after, ROI stories. Social proof without a hard sell."),
        ("Product & demos", 20, "Show the workflow. Screen-recorded walkthroughs and feature reveals."),
        ("Build-in-public & culture", 12, "What you shipped, what broke, the team behind it. Trust + reach."),
        ("Direct promotion", 8, "Clear CTAs: trial, demo, launch. Kept light so every promo lands."),
    ],
    "ecommerce": [
        ("Product in action", 30, "Demos, unboxings, styling, before/after. Highest-reach discovery content."),
        ("UGC & social proof", 25, "Customer photos/videos, reviews, results. Compounds trust over time."),
        ("Education & tips", 20, "How to use, care guides, buying advice. Earns saves and shares."),
        ("Brand & story", 15, "Founder story, values, behind-the-scenes. Builds an audience that returns."),
        ("Offers & launches", 10, "Drops, bundles, limited offers. Direct revenue posts kept minimal."),
    ],
    "b2c": [
        ("Entertainment & trends", 30, "Trend-led, relatable, shareable. Top-of-funnel discovery engine."),
        ("Education & value", 25, "Tips, how-tos, myth-busting tied to your core value."),
        ("Social proof & stories", 20, "User wins, testimonials, transformations."),
        ("Brand & community", 15, "Behind-the-scenes, values, community spotlights."),
        ("Promotion", 10, "Free trial, new feature, limited offer. Clear, minimal CTAs."),
    ],
    "general": [
        ("Education & how-to", 35, "Teach the outcome your audience wants. Saves + authority."),
        ("Proof & results", 25, "Case studies, testimonials, before/after."),
        ("Product & demos", 20, "Show how it works in 30–60 seconds."),
        ("Story & behind-the-scenes", 12, "Founder/team updates, build-in-public."),
        ("Direct promotion", 8, "Trial / demo / offer CTAs, kept light."),
    ],
}


def _status_for(prereq_ok: bool, *, selected: bool = False) -> str:
    if selected and prereq_ok:
        return "ready"
    if not prereq_ok:
        return "needs_setup"
    return "recommended"


def build_channel_strategies(
    p: OnboardingProfile, *, funnel_score: int, paid_score: int
) -> list[dict]:
    """The full cross-channel marketing mix, tailored to onboarding inputs."""
    model = _business_model(p)
    platforms = set(p.current_ad_platforms or [])
    has_search = bool(platforms & {"google_ads", "microsoft_ads"})
    has_paid_social = bool(
        platforms & {"meta_ads", "linkedin_ads", "tiktok_ads", "pinterest_ads", "x_ads"}
    )
    analytics_ok = p.analytics_status == "configured"
    has_site = bool(p.website_url)
    has_lp = bool(p.landing_page_urls) or has_site
    budget = _budget_ceiling(p)
    goal = _short_goal(p)
    geo = (p.geographic_target or "your target markets").strip()
    social_label = ", ".join(name for name, _, _ in _SOCIAL_PLATFORMS_BY_MODEL[model][:3])

    channels: list[dict] = [
        {
            "channel": "Paid Search",
            "category": "paid",
            "priority": "high" if budget >= 500 or has_search else "medium",
            "status": _status_for(analytics_ok, selected=has_search),
            "cadence": "Always-on, reviewed weekly",
            "summary": (
                f"Capture buyers already searching for solutions to drive {goal}. "
                "Start with high-intent exact/phrase keywords and a tight, conversion-focused account."
            ),
            "tactics": [
                "Build campaigns around buyer-intent keyword themes (problem, solution, competitor, brand).",
                "Write 3–4 responsive search ads per ad group; pin the offer + proof.",
                "Add negative keywords weekly to kill wasted spend.",
                "Point every campaign at a dedicated, message-matched landing page.",
            ],
            "kpis": ["CTR", "CPC", "Conversion rate", "CPA", "Search impression share", "Quality Score"],
            "first_step": "Connect Google Ads and export the search terms report to seed the keyword plan.",
        },
        {
            "channel": "Paid Social",
            "category": "paid",
            "priority": "high" if budget >= 500 or has_paid_social else "medium",
            "status": _status_for(analytics_ok, selected=has_paid_social),
            "cadence": "Always-on; refresh creative every 2–3 weeks",
            "summary": (
                "Generate problem-aware demand with thumb-stopping creative, then retarget warm "
                f"audiences across {social_label}."
            ),
            "tactics": [
                "Run a 3–5 creative-angle test (pain, proof, offer, founder, UGC) per audience.",
                "Separate prospecting and retargeting into distinct campaigns/budgets.",
                "Lead with a hook in the first 3 seconds; caption for sound-off.",
                "Rotate winners into a scaling campaign; retire fatigued creative on frequency.",
            ],
            "kpis": ["CPM", "Hook rate", "CTR", "CPA", "ROAS", "Frequency"],
            "first_step": "Install the pixel/CAPI and define your core conversion event.",
        },
        {
            "channel": "Retargeting & Remarketing",
            "category": "paid",
            "priority": "high" if has_site else "medium",
            "status": _status_for(analytics_ok and has_site),
            "cadence": "Always-on",
            "summary": (
                "Convert the 95%+ who don't act on the first visit with sequenced retargeting across "
                "search, social, and display."
            ),
            "tactics": [
                "Build audiences by intent depth: all visitors, product/pricing viewers, cart/lead starters.",
                "Sequence messaging: reminder → proof/testimonial → incentive.",
                "Cap frequency and exclude recent converters.",
            ],
            "kpis": ["View-through rate", "CTR", "CPA", "ROAS", "Frequency"],
            "first_step": "Create remarketing audiences in GA4 / Ads once the pixel is live.",
        },
        {
            "channel": "Search Engine Optimization (SEO)",
            "category": "owned",
            "priority": "high",
            "status": _status_for(has_site),
            "cadence": "2–4 publishes/month + ongoing technical fixes",
            "summary": (
                f"Build a compounding organic channel for {geo}: fix technical foundations, then publish "
                "intent-mapped content around the topics your buyers search."
            ),
            "tactics": [
                "Run a technical audit (indexation, speed, mobile, schema) and fix blockers first.",
                "Map keywords to funnel stage and build topic clusters with internal linking.",
                "Publish cornerstone pages for your highest-intent commercial keywords.",
                "Refresh decaying pages quarterly using Search Console data.",
            ],
            "kpis": ["Organic sessions", "Keyword rankings", "Indexed pages", "Organic conversions"],
            "first_step": "Connect Google Search Console to surface impressions you're already earning.",
        },
        {
            "channel": "Generative Engine Optimization (GEO)",
            "category": "owned",
            "priority": "medium",
            "status": _status_for(has_site),
            "cadence": "Monthly review",
            "summary": (
                "Get cited inside AI answer engines (ChatGPT, Google AI Overviews, Perplexity) where a "
                "growing share of research now happens."
            ),
            "tactics": [
                "Structure content as clear, extractable Q&A and definitions.",
                "Add FAQ + how-to schema and concise summary blocks.",
                "Build entity authority: consistent naming, citations, and third-party mentions.",
            ],
            "kpis": ["AI-answer citations", "Branded search volume", "Referral traffic from AI engines"],
            "first_step": "Add an FAQ section answering the top 10 questions buyers ask about your category.",
        },
        {
            "channel": "Content Marketing",
            "category": "owned",
            "priority": "high" if model in ("b2b", "general") else "medium",
            "status": "recommended",
            "cadence": "Weekly",
            "summary": (
                "Create a library of demand-generating assets (articles, guides, lead magnets, video) that "
                "feed SEO, social, email, and retargeting."
            ),
            "tactics": [
                "Build 1–2 lead magnets mapped to the primary conversion goal.",
                "Repurpose every long-form asset into 5–8 social posts and an email.",
                "Anchor content to the pillars below and the 80/20 value-to-promo ratio.",
            ],
            "kpis": ["Organic traffic", "Lead-magnet conversions", "Assisted conversions", "Time on page"],
            "first_step": "Ship one cornerstone asset that answers your buyer's biggest question.",
        },
        {
            "channel": "Organic Social Media",
            "category": "owned",
            "priority": "high" if model in ("ecommerce", "b2c") else "medium",
            "status": "recommended",
            "cadence": "Daily–weekly per platform (see platform plan)",
            "summary": (
                f"Build an owned audience on {social_label} with a pillar-driven calendar that compounds "
                "reach and trust without paying for every impression."
            ),
            "tactics": [
                "Post to a fixed weekly cadence per platform; lead with hooks.",
                "Follow the 80/20 rule: mostly value/proof, sparing promotion.",
                "Repurpose top performers into Reels/Shorts; double down on what spikes.",
                "Engage daily — comments and DMs drive the algorithm and relationships.",
            ],
            "kpis": ["Follower growth", "Engagement rate", "Reach", "Profile-to-site clicks", "Saves/shares"],
            "first_step": "Lock a weekly posting schedule and batch the first two weeks of content.",
        },
        {
            "channel": "Email Marketing & Lifecycle",
            "category": "owned",
            "priority": "high",
            "status": "recommended",
            "cadence": "Automated flows + 1 broadcast/week",
            "summary": (
                "Own the highest-ROI channel: capture emails, then run automated lifecycle flows plus a "
                "regular broadcast so you're never dependent on rented ad audiences."
            ),
            "tactics": [
                "Stand up the core flows below before scaling paid traffic.",
                "Add list-growth capture: exit-intent, lead magnet, and checkout/opt-in.",
                "Segment by behavior and lifecycle stage; personalize subject + offer.",
                "Send a weekly value-first broadcast with one clear CTA.",
            ],
            "kpis": ["List growth", "Open rate", "Click rate", "Conversion rate", "Revenue per email", "Unsub rate"],
            "first_step": "Pick an ESP and build the welcome flow first.",
        },
        {
            "channel": "Marketing Automation & Lead Nurture",
            "category": "owned",
            "priority": "medium",
            "status": _status_for(analytics_ok),
            "cadence": "Set up once, optimize monthly",
            "summary": (
                "Connect capture → CRM → nurture → handoff so no lead goes cold and the funnel runs "
                "without manual effort."
            ),
            "tactics": [
                "Score leads by fit + engagement; route hot leads to sales/booking fast.",
                "Trigger nurture sequences from on-site and email behavior.",
                "Sync conversions back to ad platforms for better optimization.",
            ],
            "kpis": ["Lead-to-MQL rate", "Sequence completion", "Reply/booking rate", "Pipeline influenced"],
            "first_step": "Map your lead stages and where each one currently leaks.",
        },
        {
            "channel": "Conversion Rate Optimization (CRO)",
            "category": "owned",
            "priority": "high" if has_lp else "medium",
            "status": _status_for(has_lp and analytics_ok),
            "cadence": "Continuous test cycle",
            "summary": (
                "Make every click work harder. Tighten above-the-fold clarity, proof, and form friction so "
                "paid and organic traffic converts at a higher rate."
            ),
            "tactics": [
                "Audit hero clarity: who it's for, what it does, why it's different — in 5 seconds.",
                "Add trust signals (logos, reviews, guarantees) near every CTA.",
                "Reduce form fields and friction; test one variable at a time.",
                "Run A/B tests on headline, offer framing, and CTA.",
            ],
            "kpis": ["Landing page conversion rate", "Bounce rate", "Form-start / add-to-cart rate", "Checkout completion"],
            "first_step": "Run a 5-second clarity test on your primary landing page.",
        },
        {
            "channel": "Referral, Partnerships & Affiliates",
            "category": "earned",
            "priority": "medium" if model in ("ecommerce", "b2c") else "low",
            "status": "recommended",
            "cadence": "Launch once, nurture ongoing",
            "summary": (
                "Turn happy customers and aligned partners into a low-CAC acquisition channel through "
                "referrals, affiliates, and co-marketing."
            ),
            "tactics": [
                "Add a referral incentive at the post-purchase / activation moment.",
                "Recruit affiliates or creators who already reach your audience.",
                "Run co-marketing (webinars, bundles, guest content) with complementary brands.",
            ],
            "kpis": ["Referral signups", "Partner-sourced revenue", "Affiliate ROI"],
            "first_step": "Identify your 10 happiest customers and ask for a referral or review.",
        },
        {
            "channel": "Analytics & Attribution",
            "category": "foundation",
            "priority": "high" if not analytics_ok else "medium",
            "status": "ready" if analytics_ok else "needs_setup",
            "cadence": "Foundational, audited monthly",
            "summary": (
                "Trustworthy measurement underpins every channel. Without clean conversion tracking, "
                "optimization and budget decisions are guesses."
            ),
            "tactics": [
                "Stand up GA4 with conversion events for the primary goal.",
                "Implement server-side / CAPI tracking for resilient attribution.",
                "Define a single source of truth and a weekly KPI dashboard.",
            ],
            "kpis": ["Event coverage", "Attribution accuracy", "Data freshness"],
            "first_step": (
                "Configure GA4 conversion events for your primary goal."
                if not analytics_ok
                else "Validate event quality and de-duplicate conversions across platforms."
            ),
        },
    ]
    return channels


def build_content_pillars(p: OnboardingProfile) -> list[dict]:
    model = _business_model(p)
    pillars = _CONTENT_PILLARS_BY_MODEL[model]
    return [
        {
            "name": name,
            "allocation_pct": pct,
            "description": desc,
            "example_hooks": [],  # filled by the LLM enhancer when available
        }
        for name, pct, desc in pillars
    ]


def build_platform_strategy(p: OnboardingProfile) -> list[dict]:
    model = _business_model(p)
    return [
        {"platform": name, "cadence": cadence, "focus": focus, "best_for": focus}
        for name, cadence, focus in _SOCIAL_PLATFORMS_BY_MODEL[model]
    ]


def build_email_strategy(p: OnboardingProfile) -> dict:
    model = _business_model(p)
    flows = [
        {"name": name, "trigger": trigger, "goal": goal}
        for name, trigger, goal in _EMAIL_FLOWS_BY_MODEL[model]
    ]
    return {
        "summary": (
            "Email is your highest-ROI, fully-owned channel. Capture demand from every other channel "
            "into a list, then let automated lifecycle flows do the selling while a weekly broadcast "
            "keeps the audience warm."
        ),
        "newsletter_cadence": "1 value-first broadcast per week",
        "flows": flows,
        "kpis": ["List growth", "Open rate", "Click rate", "Conversion rate", "Revenue per email"],
    }


def build_budget_allocation(p: OnboardingProfile, *, paid_score: int) -> list[dict]:
    """A starting % split across channel groups, weighted by readiness/model."""
    model = _business_model(p)
    if model == "ecommerce":
        split = [("Paid social & retargeting", 40), ("Paid search", 20),
                 ("Email & lifecycle", 15), ("Organic social & content", 15), ("CRO & creative", 10)]
    elif model == "b2b":
        split = [("Paid search", 30), ("Paid social (LinkedIn-led)", 25),
                 ("Content & SEO", 20), ("Email & nurture", 15), ("CRO & analytics", 10)]
    else:
        split = [("Paid search", 30), ("Paid social", 25),
                 ("Email & lifecycle", 15), ("Organic social & content", 20), ("CRO", 10)]
    return [{"channel": name, "pct": pct, "rationale": ""} for name, pct in split]


def build_marketing_strategy(
    p: OnboardingProfile, *, funnel_score: int, paid_score: int
) -> dict:
    """Assemble the full deterministic marketing strategy bundle."""
    model = _business_model(p)
    channels = build_channel_strategies(p, funnel_score=funnel_score, paid_score=paid_score)
    priorities = [
        c["channel"] for c in channels if c["priority"] == "high"
    ][:5] or [c["channel"] for c in channels[:4]]
    thesis_by_model = {
        "b2b": "Win on intent + trust: capture high-intent search, build authority through content and "
               "LinkedIn, and nurture long cycles with email until sales-ready.",
        "ecommerce": "Win on creative + lifecycle: feed paid and organic social with strong creative, then "
               "convert and retain with retargeting, email flows, and CRO.",
        "b2c": "Win on discovery + retention: lead with short-form social and paid social to discover "
               "audiences, then retain with email and community.",
        "general": "Win on a balanced full-funnel mix: high-intent paid search, demand-gen social, owned "
               "email and content, all measured on clean attribution.",
    }
    return {
        "overview": {
            "model": model,
            "thesis": thesis_by_model[model],
            "priorities": priorities,
            "budget_allocation": build_budget_allocation(p, paid_score=paid_score),
        },
        "channels": channels,
        "content_pillars": build_content_pillars(p),
        "platform_strategy": build_platform_strategy(p),
        "email_strategy": build_email_strategy(p),
        "content_calendar": [],  # filled by the LLM enhancer when available
        "source": "deterministic",
        "model_used": None,
    }


# ---------------------------------------------------------------------------
# LLM enhancement — tailors the creative/specific parts when a model is configured
# ---------------------------------------------------------------------------

_MARKETING_SYSTEM_PROMPT = (
    "You are a senior growth marketing strategist tailoring a cross-channel marketing strategy for a "
    "specific business. You are given the business profile and a baseline (a fixed list of channels with "
    "their categories). Your job is to make the CREATIVE and STRATEGIC parts specific to THIS business. "
    "Return JSON ONLY (no prose, no code fences) matching EXACTLY this schema:\n"
    "{\n"
    '  "overview": {"thesis": str, "priorities": [str, ...]},\n'
    '  "channels": [{"channel": str, "summary": str, "first_step": str}, ...],\n'
    '  "content_pillars": [{"name": str, "allocation_pct": int, "description": str, "example_hooks": [str, str]}, ...],\n'
    '  "platform_strategy": [{"platform": str, "cadence": str, "focus": str, "best_for": str}, ...],\n'
    '  "email_strategy": {"summary": str, "newsletter_cadence": str, "flows": [{"name": str, "trigger": str, "goal": str}, ...], "kpis": [str, ...]},\n'
    '  "content_calendar": [{"day": int, "channel": str, "format": str, "pillar": str, "hook": str, "caption_direction": str}, ...]\n'
    "}\n"
    "CRITICAL rules to keep the response small enough to be valid JSON:\n"
    "- For `channels`, output ONE object per baseline channel using the SAME channel name, with ONLY "
    "`channel`, `summary` (1–2 sentences), and `first_step` (1 sentence). Do NOT include tactics, kpis, "
    "cadence, category, priority, or status — those are kept from the baseline.\n"
    "- `content_pillars`: 5 pillars, allocation_pct integers summing to 100, each with EXACTLY 2 short "
    "`example_hooks` written as real post hooks for this business.\n"
    "- `content_calendar`: EXACTLY 10 entries across days 1–28. `hook` is a real, specific post hook; "
    "`caption_direction` is one short sentence.\n"
    "- Make every hook/caption reference the business's actual offer, audience, and outcomes — no generic "
    "placeholders. Be concrete and concise; do not pad."
)


def _marketing_strategy_via_llm(
    db: Session, *, workspace_id, profile: OnboardingProfile, baseline: dict
) -> dict:
    """Ask the configured LLM to tailor the strategy. Raises on any failure so
    the caller can fall back to the deterministic baseline."""
    import json

    from app.llm.client import (
        LlmError,
        LlmMessage,
        get_llm_client_for_workspace,
    )

    llm = get_llm_client_for_workspace(db, workspace_id)
    if not llm.is_configured():
        raise LlmError("No LLM configured.")
    # Use a faster/cheaper model for this large generation when configured.
    llm = _fast_client_or(llm)

    facts = {
        "business_name": profile.business_name,
        "industry": profile.industry,
        "website_url": profile.website_url,
        "target_audience": profile.target_audience,
        "offer_description": profile.offer_description,
        "pain_points": profile.pain_points,
        "primary_conversion_goal": profile.primary_conversion_goal,
        "geographic_target": profile.geographic_target,
        "monthly_ad_budget_usd": _budget_ceiling(profile) or None,
        "current_ad_platforms": profile.current_ad_platforms,
        "brand_voice": profile.brand_voice,
        "business_model": baseline["overview"]["model"],
    }
    # Send only a SLIM baseline (channel names + pillar names) — the LLM doesn't
    # need the full deterministic tactics/kpis back, and trimming input keeps the
    # call fast and the output focused.
    slim_baseline = {
        "channels": [c["channel"] for c in baseline["channels"]],
        "content_pillar_names": [p["name"] for p in baseline["content_pillars"]],
        "social_platforms": [p["platform"] for p in baseline["platform_strategy"]],
    }
    user = LlmMessage(
        role="user",
        content=(
            "BUSINESS PROFILE (JSON):\n"
            + json.dumps(facts, ensure_ascii=False)
            + "\n\nBASELINE (keep these channel names; tailor everything to the business):\n"
            + json.dumps(slim_baseline, ensure_ascii=False)
            + "\n\nReturn the tailored strategy as JSON only."
        ),
    )
    completion = llm.complete_metered(
        db=db,
        workspace_id=workspace_id,
        messages=[LlmMessage(role="system", content=_MARKETING_SYSTEM_PROMPT), user],
        max_tokens=6000,
        temperature=0.6,
        purpose="growth_dna.marketing_strategy",
    )
    data = _coerce_marketing_json(completion.text)
    merged = _merge_marketing(baseline, data)
    merged["source"] = "ai"
    merged["model_used"] = completion.model
    merged["enrichment"] = "enriched"
    return merged


def _fast_client_or(llm):
    """Return a client pinned to `settings.llm_fast_model` when set, building the
    RIGHT provider client from the model name (gpt*/o*→OpenAI, claude*→Anthropic,
    gemini*→Google) so the fast model can differ from the app's main provider.
    Falls back to the original client when that provider's key isn't configured,
    so a misconfig degrades to the normal model rather than erroring."""
    from app.core.config import settings
    from app.llm.client import AnthropicClient, GoogleAIClient, OpenAIClient

    fast = (settings.llm_fast_model or "").strip()
    if not fast:
        return llm
    name = fast.lower()

    if name.startswith(("gpt", "o1", "o3", "o4", "chatgpt")):
        if settings.openai_api_key:
            return OpenAIClient(api_key=settings.openai_api_key, model=fast)
        return llm  # no OpenAI key → keep the main client
    if name.startswith("claude"):
        key = settings.anthropic_api_key or (
            llm.api_key if isinstance(llm, AnthropicClient) else ""
        )
        return AnthropicClient(api_key=key, model=fast) if key else llm
    if name.startswith("gemini"):
        if settings.google_ai_api_key:
            return GoogleAIClient(api_key=settings.google_ai_api_key, model=fast)
        return llm

    # Unknown prefix: just swap the model on a same-provider client.
    if isinstance(llm, AnthropicClient):
        return AnthropicClient(api_key=llm.api_key, model=fast)
    if isinstance(llm, OpenAIClient):
        return OpenAIClient(api_key=llm.api_key, base_url=llm.base_url, model=fast)
    return llm


def _coerce_marketing_json(text: str) -> dict:
    import json

    body = (text or "").strip()
    if body.startswith("```"):
        lines = body.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        body = "\n".join(lines)
    if not body.startswith("{") and "{" in body:
        body = body[body.index("{"):]
    if body.endswith("```"):
        body = body[: body.rindex("```")]
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("LLM strategy was not a JSON object.")
    return data


def _merge_marketing(baseline: dict, ai: dict) -> dict:
    """Overlay validated AI fields onto the baseline. Anything missing or
    malformed keeps the deterministic value, so partial AI output still helps."""
    out = {k: v for k, v in baseline.items()}

    # Overview
    ov = dict(baseline["overview"])
    ai_ov = ai.get("overview") if isinstance(ai.get("overview"), dict) else {}
    if isinstance(ai_ov.get("thesis"), str) and ai_ov["thesis"].strip():
        ov["thesis"] = ai_ov["thesis"].strip()
    if isinstance(ai_ov.get("priorities"), list) and ai_ov["priorities"]:
        ov["priorities"] = [str(x) for x in ai_ov["priorities"]][:6]
    out["overview"] = ov

    # Channels — match by name, overlay narrative fields only.
    ai_channels = {
        str(c.get("channel", "")).lower(): c
        for c in (ai.get("channels") or [])
        if isinstance(c, dict)
    }
    new_channels = []
    for base_c in baseline["channels"]:
        merged_c = dict(base_c)
        ac = ai_channels.get(base_c["channel"].lower())
        if isinstance(ac, dict):
            for key in ("summary", "cadence", "first_step", "priority", "status"):
                if isinstance(ac.get(key), str) and ac[key].strip():
                    merged_c[key] = ac[key].strip()
            if isinstance(ac.get("tactics"), list) and ac["tactics"]:
                merged_c["tactics"] = [str(t) for t in ac["tactics"]][:6]
            if isinstance(ac.get("kpis"), list) and ac["kpis"]:
                merged_c["kpis"] = [str(k) for k in ac["kpis"]][:8]
        new_channels.append(merged_c)
    out["channels"] = new_channels

    # Content pillars — accept AI version only if it's well-formed and sums ~100.
    ai_pillars = [c for c in (ai.get("content_pillars") or []) if isinstance(c, dict)]
    if ai_pillars:
        cleaned = []
        for c in ai_pillars:
            try:
                pct = int(c.get("allocation_pct", 0))
            except (TypeError, ValueError):
                pct = 0
            hooks = [str(h) for h in (c.get("example_hooks") or []) if str(h).strip()]
            cleaned.append(
                {
                    "name": str(c.get("name", "")).strip() or "Pillar",
                    "allocation_pct": pct,
                    "description": str(c.get("description", "")).strip(),
                    "example_hooks": hooks[:3],
                }
            )
        if cleaned and 90 <= sum(c["allocation_pct"] for c in cleaned) <= 110:
            out["content_pillars"] = cleaned

    # Platform strategy
    ai_platforms = [c for c in (ai.get("platform_strategy") or []) if isinstance(c, dict)]
    if ai_platforms:
        out["platform_strategy"] = [
            {
                "platform": str(c.get("platform", "")).strip() or "Platform",
                "cadence": str(c.get("cadence", "")).strip(),
                "focus": str(c.get("focus", "")).strip(),
                "best_for": str(c.get("best_for") or c.get("focus") or "").strip(),
            }
            for c in ai_platforms
        ]

    # Email strategy
    ai_email = ai.get("email_strategy")
    if isinstance(ai_email, dict):
        em = dict(baseline["email_strategy"])
        if isinstance(ai_email.get("summary"), str) and ai_email["summary"].strip():
            em["summary"] = ai_email["summary"].strip()
        if isinstance(ai_email.get("newsletter_cadence"), str) and ai_email["newsletter_cadence"].strip():
            em["newsletter_cadence"] = ai_email["newsletter_cadence"].strip()
        ai_flows = [f for f in (ai_email.get("flows") or []) if isinstance(f, dict)]
        if ai_flows:
            em["flows"] = [
                {
                    "name": str(f.get("name", "")).strip() or "Flow",
                    "trigger": str(f.get("trigger", "")).strip(),
                    "goal": str(f.get("goal", "")).strip(),
                }
                for f in ai_flows
            ]
        if isinstance(ai_email.get("kpis"), list) and ai_email["kpis"]:
            em["kpis"] = [str(k) for k in ai_email["kpis"]][:8]
        out["email_strategy"] = em

    # Content calendar — purely AI (deterministic baseline is empty).
    ai_cal = [c for c in (ai.get("content_calendar") or []) if isinstance(c, dict)]
    if ai_cal:
        cleaned_cal = []
        for c in ai_cal[:30]:
            try:
                day = int(c.get("day", 0))
            except (TypeError, ValueError):
                day = 0
            cleaned_cal.append(
                {
                    "day": day,
                    "channel": str(c.get("channel", "")).strip(),
                    "format": str(c.get("format", "")).strip(),
                    "pillar": str(c.get("pillar", "")).strip(),
                    "hook": str(c.get("hook", "")).strip(),
                    "caption_direction": str(c.get("caption_direction", "")).strip(),
                }
            )
        out["content_calendar"] = cleaned_cal

    return out


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = (
    "business_name",
    "website_url",
    "target_audience",
    "offer_description",
    "primary_conversion_goal",
)

# Onboarding answers frozen into each generated profile (everything the wizard
# edits, minus wizard bookkeeping). Restoring these makes the profile's product
# the "active" one again.
SNAPSHOT_FIELDS = (
    "business_name",
    "website_url",
    "industry",
    "target_audience",
    "offer_description",
    "pain_points",
    "primary_conversion_goal",
    "monthly_ad_budget_min_usd",
    "monthly_ad_budget_max_usd",
    "geographic_target",
    "current_ad_platforms",
    "landing_page_urls",
    "analytics_status",
    "competitors",
    "brand_voice",
)


def snapshot_onboarding(profile: OnboardingProfile) -> dict:
    return {field: getattr(profile, field) for field in SNAPSHOT_FIELDS}


def _missing_required(p: OnboardingProfile) -> list[str]:
    return [field for field in REQUIRED_FIELDS if not getattr(p, field)]


def generate_growth_dna(
    db: Session, *, profile: OnboardingProfile
) -> GrowthDnaProfile:
    missing = _missing_required(profile)
    if missing:
        raise OnboardingIncompleteError(
            f"Onboarding is missing required fields: {', '.join(missing)}.",
        )

    funnel_score = compute_funnel_readiness(profile)
    paid_score = compute_paid_ads_readiness(profile)

    # Deterministic backbone is built + returned IMMEDIATELY (sub-second). The
    # slow LLM tailoring is NOT done here — it runs in the background (see
    # enrich_growth_dna_background) so the request never blocks ~30-120s on an
    # LLM call. `enrichment` tells the UI whether to expect an AI upgrade.
    marketing_strategy = build_marketing_strategy(
        profile, funnel_score=funnel_score, paid_score=paid_score
    )
    marketing_strategy["enrichment"] = (
        "pending" if _llm_available(db, profile.workspace_id) else "skipped"
    )

    dna = GrowthDnaProfile(
        workspace_id=profile.workspace_id,
        onboarding_profile_id=profile.id,
        # Born named after its product so multi-product histories stay readable;
        # users can rename at any time.
        label=(profile.business_name or "").strip()[:160] or None,
        onboarding_snapshot=snapshot_onboarding(profile),
        business_summary=build_business_summary(profile),
        icp_summary=build_icp_summary(profile),
        offer_positioning=build_offer_positioning(profile),
        funnel_readiness_score=funnel_score,
        paid_ads_readiness_score=paid_score,
        seo_geo_opportunity_summary=build_seo_geo_summary(profile),
        website_conversion_risks=build_website_risks(profile),
        tracking_readiness=build_tracking_readiness(profile),
        recommended_first_campaigns=build_campaign_recommendations(profile),
        thirty_day_growth_plan=build_thirty_day_plan(
            profile, funnel_score=funnel_score, paid_score=paid_score
        ),
        marketing_strategy=marketing_strategy,
        engine_version=ENGINE_VERSION,
    )
    db.add(dna)
    db.commit()
    db.refresh(dna)
    return dna


def _llm_available(db: Session, workspace_id) -> bool:
    from app.llm.client import get_llm_client_for_workspace

    try:
        return get_llm_client_for_workspace(db, workspace_id).is_configured()
    except Exception:  # noqa: BLE001
        return False


def enrich_growth_dna(db: Session, *, dna: GrowthDnaProfile) -> GrowthDnaProfile:
    """Run the LLM tailoring over an already-saved Growth DNA and update it in
    place. Any failure keeps the deterministic strategy and marks enrichment
    'skipped'. Safe to call synchronously (tests) or from a background task."""
    profile = (
        db.query(OnboardingProfile)
        .filter(OnboardingProfile.id == dna.onboarding_profile_id)
        .first()
    )
    if profile is None:
        return dna

    baseline = dict(dna.marketing_strategy or {})
    try:
        enriched = _marketing_strategy_via_llm(
            db, workspace_id=dna.workspace_id, profile=profile, baseline=baseline
        )
        dna.marketing_strategy = enriched
        model_used = enriched.get("model_used") or "llm"
        dna.engine_version = f"ai-{model_used}"[:32]
    except Exception:  # noqa: BLE001 — never let enrichment break; keep deterministic
        ms = dict(dna.marketing_strategy or {})
        ms["enrichment"] = "skipped"
        dna.marketing_strategy = ms
    db.commit()
    db.refresh(dna)
    return dna


def enrich_growth_dna_background(workspace_id, dna_id) -> None:
    """Background entrypoint (FastAPI BackgroundTask). Opens its own session so
    it runs after the response is sent, without a Celery worker."""
    from app.db import session as db_session_module

    db = db_session_module.SessionLocal()
    try:
        dna = (
            db.query(GrowthDnaProfile)
            .filter(
                GrowthDnaProfile.id == dna_id,
                GrowthDnaProfile.workspace_id == workspace_id,
            )
            .first()
        )
        if dna is not None:
            enrich_growth_dna(db, dna=dna)
    finally:
        db.close()


def get_latest_for_workspace(
    db: Session, *, workspace_id
) -> GrowthDnaProfile | None:
    return (
        db.query(GrowthDnaProfile)
        .filter(GrowthDnaProfile.workspace_id == workspace_id)
        .order_by(GrowthDnaProfile.created_at.desc())
        .first()
    )


def list_for_workspace(db: Session, *, workspace_id) -> list[GrowthDnaProfile]:
    """Every saved Growth DNA for the workspace, newest first."""
    return (
        db.query(GrowthDnaProfile)
        .filter(GrowthDnaProfile.workspace_id == workspace_id)
        .order_by(GrowthDnaProfile.created_at.desc())
        .all()
    )


def get_by_id(db: Session, *, workspace_id, dna_id) -> GrowthDnaProfile | None:
    return (
        db.query(GrowthDnaProfile)
        .filter(
            GrowthDnaProfile.id == dna_id,
            GrowthDnaProfile.workspace_id == workspace_id,
        )
        .first()
    )


def set_label(
    db: Session, *, dna: GrowthDnaProfile, label: str | None
) -> GrowthDnaProfile:
    cleaned = (label or "").strip()
    dna.label = cleaned[:160] or None
    db.commit()
    db.refresh(dna)
    return dna


def delete_profile(db: Session, *, workspace_id, dna_id) -> bool:
    dna = get_by_id(db, workspace_id=workspace_id, dna_id=dna_id)
    if dna is None:
        return False
    db.delete(dna)
    db.commit()
    return True


class NoOnboardingSnapshotError(AdVantaError):
    status_code = 409
    code = "no_onboarding_snapshot"


def restore_onboarding_from_profile(
    db: Session, *, dna: GrowthDnaProfile
) -> OnboardingProfile:
    """Write the profile's frozen onboarding answers back into the workspace's
    (single) onboarding profile, making that product the active one for the
    wizard and future generations. The replaced answers are not lost as long as
    they were generated from — every generation freezes its own snapshot."""
    snapshot = dna.onboarding_snapshot
    if not snapshot:
        raise NoOnboardingSnapshotError(
            "This profile predates answer snapshots — its onboarding answers "
            "were not saved and cannot be restored."
        )

    profile = (
        db.query(OnboardingProfile)
        .filter(OnboardingProfile.workspace_id == dna.workspace_id)
        .first()
    )
    if profile is None:
        profile = OnboardingProfile(workspace_id=dna.workspace_id, step_completed=0)
        db.add(profile)

    for field in SNAPSHOT_FIELDS:
        if field in snapshot:
            setattr(profile, field, snapshot[field])

    db.commit()
    db.refresh(profile)
    return profile
