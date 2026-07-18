"""Built-in Help / Knowledge-Base content.

The canonical help articles live here (not in the DB) so the same text drives
both the "Text" tab and the ElevenLabs "Audio" narration — no duplication and no
client-supplied-text abuse vector. Adapted from the public module guides plus
Getting Started + Billing.

Each topic exposes a stable `id` (used in URLs + as the audio cache key), a
`category` for grouping, `body_markdown` for display, and a derived
`narration()` (markdown stripped to clean prose) whose hash keys the cached MP3.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class HelpTopic:
    id: str
    category: str
    title: str
    summary: str
    order: int
    body_markdown: str

    def narration(self) -> str:
        return _to_narration(self.title, self.body_markdown)

    def content_hash(self) -> str:
        return hashlib.sha256(self.narration().encode("utf-8")).hexdigest()[:32]


_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_TOKENS = re.compile(r"[#>*_`]+")


def _to_narration(title: str, md: str) -> str:
    """Strip markdown to plain, speakable prose for TTS. Keeps link text, drops
    heading/bold/list symbols, and reads the title first."""
    lines: list[str] = [title + "."]
    for raw in md.splitlines():
        line = _MD_LINK.sub(r"\1", raw)  # [text](url) -> text
        line = _MD_TOKENS.sub("", line)  # drop #, *, _, `, >
        line = re.sub(r"^\s*[-+]\s+", "", line)  # bullet dashes
        line = line.strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Articles
# ---------------------------------------------------------------------------

HELP_TOPICS: list[HelpTopic] = [
    HelpTopic(
        id="getting-started",
        category="Getting started",
        title="Getting started with AdGenieHQ",
        summary="Connect your accounts, complete onboarding, and meet your AI growth team.",
        order=1,
        body_markdown="""\
AdGenieHQ is your AI Growth Command Center. Instead of one big AI prompt, it runs
a Master Growth Orchestrator that coordinates specialized AI agents — for paid
ads, SEO and AI-search visibility, website conversion, tracking, budget safety,
and reporting.

## Your first 15 minutes

1. **Create your workspace.** A workspace holds your connected accounts, agent
   outputs, and team. You can create more than one (for different brands or
   clients).
2. **Complete onboarding.** Tell us your business, offer, audience, budget, and
   goals. This produces your **Growth DNA** profile, which every agent uses as
   context.
3. **Connect your platforms.** In Settings → Integrations, connect the ad
   accounts, analytics, and search data you use. Everything runs on real OAuth —
   nothing is simulated, and disconnected accounts simply show a clean connect
   prompt.
4. **Run an agent or open a recommendation.** From the Agents dashboard, run a
   skill agent, then review what it produced.

## Safe by default

Anything that can spend money or change a live campaign is **approval-gated** by
default. You review and approve before it happens. Autopilot is opt-in, with
limits you set.
""",
    ),
    HelpTopic(
        id="growth-dna",
        category="Getting started",
        title="Your Growth DNA profile",
        summary="The saved business profile every agent reads before it works.",
        order=2,
        body_markdown="""\
Your **Growth DNA** profile is generated from your onboarding answers and saved
to your workspace. It's the shared context every agent reads before it acts, so
recommendations sound like your business instead of generic advice.

## What it captures

- A business summary and ideal-customer (ICP) snapshot
- Offer positioning and funnel-readiness signals
- Paid-ads readiness and SEO/GEO opportunity notes
- Website conversion risks and tracking readiness
- Recommended first campaigns and a 30-day growth plan

## Keeping it current

You can regenerate your Growth DNA whenever your business changes — a new offer,
a new audience, a new goal. Saved profiles are kept in a library so you can
compare versions or reuse earlier answers for a new product.
""",
    ),
    HelpTopic(
        id="command-center",
        category="Insights",
        title="The Command Center dashboard",
        summary="Your single view of spend, conversions, health scores, and next actions.",
        order=3,
        body_markdown="""\
The **Command Center** is your home screen — a single, honest view of how growth
is trending across everything you've connected.

## What you'll see

- Growth score and connected-account status
- Spend, leads/conversions, CPA, ROAS, and conversion rate
- SEO and GEO visibility, plus website health
- Active agent tasks, critical alerts, and recommended next actions

## Honest empty states

Every number comes from a real database record, a real integration, or a saved
AI output. If a platform isn't connected yet, you'll see a clear empty state with
a connect button instead of a fabricated chart. As you connect more data, the
dashboard fills in.
""",
    ),
    HelpTopic(
        id="campaigns",
        category="Advertising",
        title="Campaigns & the Paid Ads agent",
        summary="Sync real campaigns and get optimization recommendations across platforms.",
        order=4,
        body_markdown="""\
The Campaigns area shows real campaign records synced from the ad platforms you
connect — Google, Meta, and LinkedIn — with the **Paid Ads** agent watching for
opportunities and waste.

## What the agent does

- Analyzes account performance and budget pacing
- Detects overspend, CPA spikes, and ROAS drops
- Suggests budget reallocations, scaling, and pause/boost moves
- Proposes ad structure and creative testing plans

## Three execution modes

1. **Advisor** — analysis and recommendations only.
2. **Approval** — the AI proposes; you approve before anything changes.
3. **Autopilot** — the AI executes within strict limits you set.

The default is Approval or Advisor. Autopilot never turns on by itself, and
budget guardrails apply in every mode.
""",
    ),
    HelpTopic(
        id="traffic-genie",
        category="Advertising",
        title="Traffic Genie",
        summary="Plan traffic sources, build UTMs, and run solo ads and paid email.",
        order=5,
        body_markdown="""\
**Traffic Genie** is your hub for driving traffic beyond the big ad platforms —
solo ads, paid email, and other sources — with AI recommendations and clean
tracking.

## What's inside

- A traffic-sources hub with AI recommendations for where to spend next
- A **UTM builder** so every link is tagged consistently for attribution
- Solo Ads and Paid Email workflows to plan and track buys
- Journey and analytics views to see what's actually converting

Use the UTM builder for every campaign link — consistent tags are what make the
attribution and reports trustworthy later.
""",
    ),
    HelpTopic(
        id="email-marketing",
        category="Advertising",
        title="Email marketing",
        summary="Sync your email platform and get an email performance report.",
        order=6,
        body_markdown="""\
Connect your email marketing platform to bring campaign performance into
AdGenieHQ and let the reporting agent summarize what's working.

## What you get

- Synced email campaign records and key metrics
- An email-marketing report that highlights opens, clicks, and standout sends
- Recommendations you can act on to lift engagement

As with every integration, connect through Settings → Integrations. Until a
provider is connected, the email area shows a connect prompt rather than sample
data.
""",
    ),
    HelpTopic(
        id="seo-geo",
        category="Optimization",
        title="SEO & GEO visibility",
        summary="Improve visibility in search engines and AI answer engines.",
        order=7,
        body_markdown="""\
The **SEO & GEO** agent improves your visibility in two places: traditional
search engines and AI answer engines (GEO — Generative Engine Optimization).

## What it produces

- Keyword and content-gap opportunities
- Technical SEO fixes, metadata, schema, and internal-linking suggestions
- FAQ and entity optimization for AI-search visibility
- A content calendar and a search-visibility score

## Connect for real data

Link Google Search Console and GA4 for opportunity analysis grounded in your own
data, and add your sitemap so the crawler understands your site. Recommendations
flow into the Recommendations Center for review.
""",
    ),
    HelpTopic(
        id="website",
        category="Optimization",
        title="Website intelligence",
        summary="Audit landing pages for conversion, speed, and clarity.",
        order=8,
        body_markdown="""\
The **Website** agent audits your landing pages and site for conversion, clarity,
and speed, then gives you a prioritized improvement roadmap.

## What it checks

- Above-the-fold clarity, CTA strength, and offer clarity
- Mobile responsiveness and page-speed signals
- Trust signals and form friction
- A/B test ideas and a conversion-improvement roadmap

You'll get a website health score, a landing-page conversion score, and specific
copy and layout recommendations you can approve and apply.
""",
    ),
    HelpTopic(
        id="recommendations",
        category="Insights",
        title="Recommendations & approvals",
        summary="Review, approve, reject, or edit every AI suggestion — with an audit trail.",
        order=9,
        body_markdown="""\
Every agent writes its suggestions into the **Recommendations Center**, where you
stay in control of anything meaningful.

## Each recommendation shows

- What the AI found and why it matters
- Expected impact and a risk level
- The related platform and campaign, when applicable
- Approve, Reject, or Edit-before-applying — plus a full audit trail

## Approvals keep you safe

Sensitive actions — launching campaigns, increasing budgets, pausing major
campaigns, changing tracking, or disconnecting integrations — require explicit
approval by default. Turn on Autopilot only when you're ready, and only within
the budget and risk limits you set.
""",
    ),
    HelpTopic(
        id="reports",
        category="Insights",
        title="Reports",
        summary="Generate daily, weekly, and monthly reports from real data.",
        order=10,
        body_markdown="""\
The Reports Center turns your connected data and saved AI outputs into clear,
executive-ready summaries.

## What you can generate

- Daily, weekly, and monthly reports
- Before/after analysis and change logs
- PDF export for sharing, and CSV export where tables apply

Reports are built from real records and completed agent runs — so if a report
looks empty, it's telling you to connect data or run an agent first, not showing
you invented numbers.
""",
    ),
    HelpTopic(
        id="billing",
        category="Account",
        title="Billing & plans",
        summary="How subscriptions, PayPal checkout, plan limits, and platform fees work.",
        order=11,
        body_markdown="""\
AdGenieHQ offers Starter, Pro, and Agency plans, billed monthly or annually
through **PayPal**.

## Subscribing

From Settings → Billing, choose a plan and continue to PayPal to approve the
subscription. When you return, your plan activates as soon as PayPal confirms it
(usually within seconds). To cancel, open **Manage plan**, which takes you to
your PayPal account where you can stop future renewals.

## Plan limits and credits

AI work is metered as a monthly credit pool, and non-AI caps (like tracked
landing pages and team seats) apply per plan. If you hit a limit, you'll see a
clear message with an upgrade path — nothing fails silently.

## Platform fees

Separately from your subscription, usage-based platform fees may apply to ad
activity you manage through the app. These are shown on the billing page and are
billed via PayPal invoice. Cancelling a subscription stops future renewals;
see the Refund & Cancellation policy for details.
""",
    ),
]


HELP_TOPICS_BY_ID: dict[str, HelpTopic] = {t.id: t for t in HELP_TOPICS}


def list_topics() -> list[HelpTopic]:
    return sorted(HELP_TOPICS, key=lambda t: t.order)


def get_topic(topic_id: str) -> HelpTopic | None:
    return HELP_TOPICS_BY_ID.get(topic_id)
