"""Built-in Help / Knowledge-Base content.

The canonical help articles live here (not in the DB) so the same text drives
both the "Text" tab and the ElevenLabs "Audio" narration — no duplication and no
client-supplied-text abuse vector. Adapted from the public module guides plus
Getting Started + Billing.

Each topic exposes a stable `id` (used in URLs + as the audio cache key), a
`category` for grouping, `body_markdown` for display, and a derived
`narration()` (markdown stripped to clean prose) whose hash keys the cached MP3.

Categories mirror the app sidebar groups so the Help center maps 1:1 to the
product. `order` drives both the list sequence and the category grouping order
(the first topic in each category fixes where that category appears).
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
        id="agents",
        category="Agents & Automation",
        title="Your AI agent team",
        summary="Meet the Master Orchestrator and the specialist skill agents that do the work.",
        order=3,
        body_markdown="""\
AdGenieHQ works like a team, not a single chatbot. A **Master Growth
Orchestrator** reads your goal, breaks it into tasks, and hands each one to the
specialist agent best suited to it — then saves every result to your workspace.

## The specialists

- **Market Intelligence** and **ICP & Persona** — understand your market and buyers
- **Creative Strategy** and **Campaign Builder** — turn strategy into ads and structure
- **Paid Ads** and **Budget Guardian** — monitor spend and protect against waste
- **SEO & GEO**, **Website**, and **Tracking & Attribution** — grow and measure
- **Reporting** — turn everything into clear summaries

## Running an agent

From the Agents dashboard you can run a skill agent and watch its status. Each run
is saved with its inputs, outputs, the model used, and the estimated cost, so
nothing is a black box. Whatever an agent proposes lands in the Recommendations
Center for you to review — it never changes a live account without going through
approvals.
""",
    ),
    HelpTopic(
        id="recommendations",
        category="Agents & Automation",
        title="Recommendations & approvals",
        summary="Review, approve, reject, or edit every AI suggestion — with an audit trail.",
        order=4,
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
        id="autopilot",
        category="Agents & Automation",
        title="Autopilot & safety modes",
        summary="Advisor, Approval, and Autopilot — plus the guardrails that keep spend safe.",
        order=5,
        body_markdown="""\
Every agent runs in one of three modes, and you decide how much freedom to give
it. This is the core of how AdGenieHQ stays safe.

## The three modes

1. **Advisor** — the AI only analyzes and recommends; it never touches a live account.
2. **Approval** — the AI proposes actions and waits for your explicit approval.
3. **Autopilot** — the AI executes approved *categories* of actions on its own,
   inside strict limits you set.

Advisor or Approval is the default. Autopilot never turns on by itself.

## Autopilot guardrails

When you opt in to Autopilot, you set the boundaries it must stay within:

- A maximum daily budget and a maximum percentage budget increase
- A minimum conversion threshold and stop-loss rules
- An overall risk limit

Everything Autopilot does is written to the audit log, and you can switch it off
instantly. Launching campaigns, large budget increases, and tracking changes
always respect these limits.
""",
    ),
    HelpTopic(
        id="campaigns",
        category="Advertising",
        title="Campaigns & the Paid Ads agent",
        summary="Sync real campaigns and get optimization recommendations across platforms.",
        order=6,
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
        id="creatives",
        category="Advertising",
        title="Creatives & the Creative Strategy agent",
        summary="Generate hooks, ad angles, scripts, and a creative testing plan.",
        order=7,
        body_markdown="""\
The **Creative Strategy** agent turns your positioning into ready-to-test
creative — angles, copy, and scripts grounded in your Growth DNA.

## What it generates

- Ad hooks and story-based angles, including founder-led and UGC-style scripts
- Static and carousel ad concepts
- Short-form video scripts for Reels, Shorts, and TikTok
- A creative testing matrix so you always know what to try next

## Fatigue and iteration

When performance data is connected, the agent can flag creative fatigue and
suggest fresh variations before results decline. Copy and concepts are saved to
your workspace and can flow into campaigns and A/B tests.
""",
    ),
    HelpTopic(
        id="email-marketing",
        category="Advertising",
        title="Email marketing",
        summary="Sync your email platform and get an email performance report.",
        order=8,
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
        id="autoresponders",
        category="Advertising",
        title="Autoresponders",
        summary="Connect Omnisend, GetResponse, or a custom webhook to sync your audiences.",
        order=9,
        body_markdown="""\
Autoresponders connect your email automation platform so your lists and
subscribers are available inside AdGenieHQ for targeting and reporting.

## Supported providers

- **Omnisend**
- **GetResponse**
- A **custom webhook**, so a platform that isn't listed can still connect

## How it works

Connect a provider from the Autoresponders area and AdGenieHQ syncs your
audiences, recording each sync attempt — including any errors — so you can see
connection health at a glance. Credentials are encrypted at rest, and nothing is
sent to a provider without a real, authorized connection.
""",
    ),
    HelpTopic(
        id="traffic-genie",
        category="Traffic Genie",
        title="Traffic Genie",
        summary="Plan traffic sources, build UTMs, and run solo ads and paid email.",
        order=10,
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
        id="seo-geo",
        category="SEO & Content",
        title="SEO & GEO visibility",
        summary="Improve visibility in search engines and AI answer engines.",
        order=11,
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
        id="content",
        category="SEO & Content",
        title="Content studio",
        summary="Generate on-brand drafts — blog posts, ad copy, emails, and more.",
        order=12,
        body_markdown="""\
The **Content studio** drafts marketing copy that sounds like your business,
using your Growth DNA as context.

## What you can draft

- Blog posts and landing-page copy
- Ad copy and meta descriptions
- Emails and social posts
- Short video scripts

## Drafts, not auto-posts

Every piece starts as a **draft** you can edit, approve, reject, or archive —
nothing publishes on its own. Where an image helps, the studio can generate one to
match the draft. Approved content can move on to your blog, campaigns, or the
social studio.
""",
    ),
    HelpTopic(
        id="social",
        category="SEO & Content",
        title="Social studio",
        summary="Create platform-ready posts and Reels/Shorts scripts from one idea.",
        order=13,
        body_markdown="""\
The **Social studio** turns a single idea into content shaped for each platform —
written posts and short-form video scripts.

## What it produces

- Platform-specific posts, with tone and length tuned per network
- Reels, Shorts, and TikTok video scripts with hooks and scene beats
- A matching image generated from the post when you want one

## Your workflow

Generate, review, and edit each draft before you use it — the studio prepares the
content, you stay the editor. Approved posts save to your workspace so you can
reuse or schedule them through your own channels.
""",
    ),
    HelpTopic(
        id="blog",
        category="SEO & Content",
        title="Blog",
        summary="Draft, edit, and publish SEO-ready blog posts.",
        order=14,
        body_markdown="""\
The **Blog** area is where long-form content becomes published pages, with SEO
structure built in.

## Writing and editing

- Draft posts from scratch or from a Content studio draft
- Edit the title, slug, excerpt, and body
- Keep everything organized by status — draft, approved, published, or archived

## Publishing

When a post is ready, publish it to make it live. If you've set a publish webhook
in your workspace, AdGenieHQ can notify your own site so the post appears where
your readers are. Posts stay grounded in your Growth DNA so the topics and voice
fit your brand.
""",
    ),
    HelpTopic(
        id="outreach",
        category="SEO & Content",
        title="Outreach",
        summary="Find backlink prospects and send approved outreach emails.",
        order=15,
        body_markdown="""\
**Outreach** helps you build authority and links by finding relevant prospects
and handling the email conversation — with you in control of every send.

## What it does

- Discovers and scores backlink and partnership prospects
- Drafts a personalized outreach email for each prospect
- Drafts follow-ups automatically when a thread goes quiet

## Approval before send

Outreach emails are **drafts** until an Admin approves them — nothing goes out on
its own. Sending runs safely in the background, and each email's status updates to
sent or failed, so you always know where a conversation stands.
""",
    ),
    HelpTopic(
        id="command-center",
        category="Conversion & Insights",
        title="The Command Center dashboard",
        summary="Your single view of spend, conversions, health scores, and next actions.",
        order=16,
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
        id="website",
        category="Conversion & Insights",
        title="Website intelligence",
        summary="Audit landing pages for conversion, speed, and clarity.",
        order=17,
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
        id="ab-tests",
        category="Conversion & Insights",
        title="A/B tests",
        summary="Generate variants, launch tests, and let the winner earn more traffic.",
        order=18,
        body_markdown="""\
**A/B tests** let you compare versions of an ad or page and learn what actually
converts — without guessing.

## Setting up a test

- Generate variant ideas automatically, or add your own
- Launch the test across the connected target
- Track exposures and conversions per variant in real records

## Smart traffic allocation

Tests can use a bandit strategy that gradually shifts traffic toward the
better-performing variant, so you waste less spend on losers. Launching a test is
an approval-gated action, and all results come from real tracked events — never
simulated numbers.
""",
    ),
    HelpTopic(
        id="reports",
        category="Conversion & Insights",
        title="Reports",
        summary="Generate daily, weekly, and monthly reports from real data.",
        order=19,
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
        id="settings",
        category="Workspace",
        title="Workspace, team & integrations",
        summary="Manage members and roles, connect platforms, and issue API keys.",
        order=20,
        body_markdown="""\
**Settings** is where you run the workspace itself — who's on it, what's
connected, and how you access the API.

## Team and roles

Invite teammates and assign a role — Owner, Admin, Marketer, Analyst, or Viewer.
Roles control who can connect integrations, run agents, approve recommendations,
change campaigns, and manage billing, so people only get the access they need.

## Integrations

Connect your ad accounts, analytics, and search data through real OAuth. Tokens
are encrypted at rest and never exposed to the browser, and a disconnected
provider shows a clean connect prompt instead of fake data. You can also bring
your own AI provider keys here.

## API keys

Issue API keys to integrate AdGenieHQ with your own systems. Keys are scoped to
the workspace and can be revoked at any time.
""",
    ),
    HelpTopic(
        id="billing",
        category="Workspace",
        title="Billing & plans",
        summary="How subscriptions, PayPal checkout, plan limits, and platform fees work.",
        order=21,
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
