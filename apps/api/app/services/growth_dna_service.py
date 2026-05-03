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

ENGINE_VERSION = "deterministic-v1"


class OnboardingIncompleteError(AdVantaError):
    status_code = 422
    code = "onboarding_incomplete"


# ---------------------------------------------------------------------------
# Score helpers
# ---------------------------------------------------------------------------

def _bool_score(value: bool, weight: float) -> float:
    return weight if value else 0.0


def _has_text(value: str | None, *, min_chars: int = 1) -> bool:
    return bool(value and value.strip() and len(value.strip()) >= min_chars)


def _has_list(value: list | None) -> bool:
    return bool(value)


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


def build_campaign_recommendations(p: OnboardingProfile) -> list[dict]:
    platforms = p.current_ad_platforms or []
    if not platforms:
        # Conservative default: Google + Meta if no platforms picked yet.
        platforms = ["google_ads", "meta_ads"]

    objective = (p.primary_conversion_goal or "Lead generation").strip()
    n = len(platforms)
    base_share = 100 // n if n else 0
    remainder = 100 - base_share * n if n else 0

    suggestions: list[dict] = []
    for idx, platform in enumerate(platforms):
        share = base_share + (1 if idx < remainder else 0)
        suggestions.append(
            {
                "platform": PLATFORM_DISPLAY.get(platform, platform.replace("_", " ").title()),
                "objective": objective,
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
# Top-level orchestration
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = (
    "business_name",
    "website_url",
    "target_audience",
    "offer_description",
    "primary_conversion_goal",
)


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

    dna = GrowthDnaProfile(
        workspace_id=profile.workspace_id,
        onboarding_profile_id=profile.id,
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
        engine_version=ENGINE_VERSION,
    )
    db.add(dna)
    db.commit()
    db.refresh(dna)
    return dna


def get_latest_for_workspace(
    db: Session, *, workspace_id
) -> GrowthDnaProfile | None:
    return (
        db.query(GrowthDnaProfile)
        .filter(GrowthDnaProfile.workspace_id == workspace_id)
        .order_by(GrowthDnaProfile.created_at.desc())
        .first()
    )
