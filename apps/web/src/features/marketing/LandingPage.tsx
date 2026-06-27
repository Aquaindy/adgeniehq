import { Link } from "react-router-dom";

import { MarketingLayout } from "@/features/marketing/MarketingLayout";

/**
 * Landing page rhythm modeled on the gomega.ai shape (hero → agent grid →
 * platform overview → social proof → integrations → final CTA), but rewritten
 * with AdGenieHQ's voice ("Premium, Calm, Executive, Intelligent") and the
 * production-honest constraints from CLAUDE.md §1 — no fabricated testimonials,
 * no fake metrics, no demo data.
 *
 * The credibility section uses the platforms we genuinely OAuth into, since
 * partnerships with Google / Meta / LinkedIn are real and shippable.
 */
export function LandingPage() {
  return (
    <MarketingLayout>
      <Hero />
      <TrustBand />
      <AgentGrid />
      <PlatformOverview />
      <SafetyBand />
      <HowItWorks />
      <ProductionGuarantees />
      <FaqSection />
      <FinalCta />
    </MarketingLayout>
  );
}


/* -------------------------------------------------------------------------- */
/* Hero                                                                       */
/* -------------------------------------------------------------------------- */


function Hero() {
  return (
    <section className="relative overflow-hidden bg-grape-gradient text-white">
      {/* Faint grid for executive texture. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.07] [background-image:linear-gradient(to_right,#fff_1px,transparent_1px),linear-gradient(to_bottom,#fff_1px,transparent_1px)] [background-size:44px_44px]"
      />
      {/* Light glows so the saturated panel reads as lit, not flat. */}
      <div
        aria-hidden
        className="pointer-events-none absolute -right-24 -top-24 h-[26rem] w-[26rem] rounded-full bg-violet-electric/40 blur-3xl"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -left-32 bottom-[-12rem] h-[28rem] w-[28rem] rounded-full bg-white/10 blur-3xl"
      />

      <div className="relative mx-auto grid max-w-6xl gap-10 px-4 py-20 sm:px-6 sm:py-28 lg:grid-cols-2 lg:items-center">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs font-medium uppercase tracking-wider text-white backdrop-blur">
            <span className="h-1.5 w-1.5 rounded-full bg-white" />
            AdGenieHQ · AI Ad Creation Platform
          </p>
          <h1 className="mt-5 text-5xl font-semibold leading-[1.05] tracking-tight text-white sm:text-6xl lg:text-7xl">
            Turn ad chaos
            <br />
            into{" "}
            <span className="bg-[linear-gradient(90deg,#ffffff_0%,#D9CFF6_100%)] bg-clip-text text-transparent">
              intelligent growth.
            </span>
          </h1>
          <p className="mt-5 max-w-xl text-xl text-white/80">
            Build campaigns, generate ad copy and creative, and publish to
            Google, Meta &amp; LinkedIn in one click — then let specialized AI
            agents optimize spend, SEO, and conversion against your real data.
            Approval-gated by default; flip on Autopilot when you're ready.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              to="/register"
              className="rounded-xl bg-white px-5 py-3 text-sm font-semibold text-[#3E2F84] shadow-elevate transition hover:bg-white/90"
            >
              Get started
            </Link>
            <Link
              to="/pricing"
              className="rounded-xl border border-white/30 px-5 py-3 text-sm font-semibold text-white transition hover:bg-white/10"
            >
              See pricing
            </Link>
          </div>
          <p className="mt-4 text-xs text-white/60">
            Full platform at every tier — campaign builder, 1-click ad
            publishing, SEO, and outreach. Bring your own LLM keys to keep token
            cost on your own provider bill.
          </p>
        </div>

        <DashboardMock />
      </div>
    </section>
  );
}


/**
 * Stylized product preview. Deliberately uses dashed placeholders + abstract
 * blocks instead of hard-coded numbers — keeps us aligned with the
 * "honest empty states / no fabricated metrics" rule.
 */
function DashboardMock() {
  return (
    <div className="relative">
      <div
        aria-hidden
        className="absolute -inset-4 rounded-[2rem] bg-grape-gradient opacity-10 blur-2xl"
      />
      <div className="relative rounded-2xl border border-slate-200 bg-surface p-4 shadow-elevate sm:p-5">
        <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
          <span className="h-2.5 w-2.5 rounded-full bg-rose-300" />
          <span className="h-2.5 w-2.5 rounded-full bg-amber-300" />
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-300" />
          <span className="ml-3 text-[10px] uppercase tracking-wider text-slate-400">
            command center
          </span>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <KpiTile label="Connected accounts" />
          <KpiTile label="Active campaigns" />
          <KpiTile label="Open recs" tone="grape" />
          <KpiTile label="Spend today" />
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <AgentTile name="Paid Ads" status="auditing" />
          <AgentTile name="SEO & GEO" status="planning" />
          <AgentTile name="Website" status="draft ready" />
        </div>

        <div className="mt-4 rounded-xl border border-slate-100 bg-cloud px-3 py-3">
          <div className="flex items-center justify-between text-xs">
            <span className="font-medium text-slate-700">
              Recommendation · pause stale campaign
            </span>
            <span className="rounded-full bg-grape-100 px-2 py-0.5 font-medium text-grape-700">
              medium risk
            </span>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <span className="rounded-lg bg-grape px-2.5 py-1 text-[11px] font-semibold text-white">
              Approve
            </span>
            <span className="rounded-lg border border-slate-200 px-2.5 py-1 text-[11px] font-medium text-slate-600">
              Reject
            </span>
            <span className="ml-auto text-[10px] uppercase tracking-wider text-slate-400">
              audit-logged
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}


function KpiTile({ label, tone }: { label: string; tone?: "grape" }) {
  return (
    <div className="rounded-xl border border-slate-100 bg-surface px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-wider text-slate-400">
        {label}
      </div>
      <div
        className={
          "mt-1 flex items-baseline gap-1 " +
          (tone === "grape" ? "text-grape-700" : "text-ink")
        }
      >
        <span className="text-xl font-semibold">—</span>
        <span className="text-[10px] text-slate-400">live data</span>
      </div>
    </div>
  );
}


function AgentTile({ name, status }: { name: string; status: string }) {
  return (
    <div className="rounded-xl border border-slate-100 bg-surface px-3 py-2.5">
      <div className="text-xs font-semibold text-ink">{name} agent</div>
      <div className="mt-1 inline-flex items-center gap-1 rounded-full bg-cloud px-2 py-0.5 text-[10px] text-slate-500">
        <span className="h-1.5 w-1.5 rounded-full bg-grape-400" />
        {status}
      </div>
    </div>
  );
}


/* -------------------------------------------------------------------------- */
/* Trust band — real partner platforms                                        */
/* -------------------------------------------------------------------------- */


function TrustBand() {
  const platforms = [
    "Google Ads",
    "Meta Ads",
    "LinkedIn Ads",
    "Google Analytics 4",
    "Search Console",
    "Paddle",
  ];
  return (
    <section className="border-y border-slate-100 bg-surface">
      <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
        <p className="text-center text-xs font-medium uppercase tracking-wider text-slate-400">
          Built on the platforms your team already runs
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-x-8 gap-y-3 text-base font-medium text-slate-500">
          {platforms.map((p) => (
            <span key={p} className="whitespace-nowrap">
              {p}
            </span>
          ))}
        </div>
        <p className="mt-4 text-center text-xs text-slate-400">
          Connected via real OAuth flows. Tokens encrypted at rest. No
          simulated data, ever.
        </p>
      </div>
    </section>
  );
}


/* -------------------------------------------------------------------------- */
/* Agent grid                                                                 */
/* -------------------------------------------------------------------------- */


function AgentGrid() {
  const agents: AgentCard[] = [
    {
      title: "Paid Ads agent",
      role: "Builds, launches & optimizes",
      summary:
        "Build campaigns, generate ad copy and creative concepts, and publish straight to Google, Meta & LinkedIn — then it watches spend, surfaces waste, and proposes pauses, budget changes, or audience tweaks. Every write is approval-gated with prior-state capture, so it's reversible.",
      bullets: [
        "Campaign builder + 1-click ad publishing",
        "AI ad copy + creative concepts",
        "Cross-platform: Google, Meta, LinkedIn",
      ],
    },
    {
      title: "SEO & GEO agent",
      role: "Wins search visibility",
      summary:
        "Pulls Search Console data, crawls your site, and ranks keyword opportunities by impressions × position headroom. Drafts blog posts, refreshes content, and emits JSON-LD schema you can paste straight into your CMS.",
      bullets: [
        "Search Console + crawler grounded",
        "Content drafts + refresh flow",
        "Schema markup generator",
      ],
    },
    {
      title: "Website agent",
      role: "Lifts conversion",
      summary:
        "Audits each landing page for hero clarity, CTA prominence, mobile UX, page speed, and form friction. Generates A/B test ideas with sticky-assigned visitors, real conversion events, and proper two-proportion z-tests for significance.",
      bullets: [
        "Conversion + mobile + speed scores",
        "Real A/B runner with bandit option",
        "GA4 metric auto-collection",
      ],
    },
    {
      title: "Master Orchestrator",
      role: "Coordinates the team",
      summary:
        "Take a high-level goal — \"audit my growth stack\", \"plan a SaaS lead-gen campaign\" — and the orchestrator picks the right specialist agents, runs them in sequence, and assembles a unified plan you can approve as one batch.",
      bullets: [
        "Goal-driven playbooks",
        "Per sub-agent traceability",
        "Review every step before approval",
      ],
    },
  ];

  return (
    <section className="bg-cloud">
      <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-24">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-xs font-medium uppercase tracking-wider text-grape-700">
            The agent system
          </p>
          <h2 className="mt-3 text-4xl font-semibold tracking-tight text-ink sm:text-5xl">
            Specialists, not a single chat box.
          </h2>
          <p className="mt-3 text-lg text-slate-600">
            Each agent owns one part of the growth surface, runs against your
            real data, and writes back through the same approval flow. No
            opaque "do everything" prompt.
          </p>
        </div>

        <div className="mt-12 grid gap-5 lg:grid-cols-2">
          {agents.map((a) => (
            <AgentFeatureCard key={a.title} {...a} />
          ))}
        </div>

        <p className="mt-10 text-center text-base text-slate-500">
          Plus Market Intelligence, ICP / Persona, Creative Strategy,
          Campaign Builder, Tracking & Attribution, Budget Guardian, and
          Reporting agents — all sharing the same audit log.
        </p>
      </div>
    </section>
  );
}


type AgentCard = {
  title: string;
  role: string;
  summary: string;
  bullets: string[];
};


function AgentFeatureCard({ title, role, summary, bullets }: AgentCard) {
  return (
    <article className="group relative overflow-hidden rounded-2xl border border-slate-100 bg-surface p-6 shadow-card transition hover:shadow-elevate">
      <div
        aria-hidden
        className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full bg-grape-gradient opacity-0 blur-2xl transition-opacity group-hover:opacity-15"
      />
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-grape-gradient text-white shadow-sm">
          <AgentGlyph />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-ink">{title}</h3>
          <p className="text-xs uppercase tracking-wider text-slate-400">
            {role}
          </p>
        </div>
      </div>
      <p className="mt-4 text-base text-slate-600">{summary}</p>
      <ul className="mt-4 flex flex-col gap-1.5 text-base text-slate-700">
        {bullets.map((b) => (
          <li key={b} className="flex items-start gap-2">
            <span
              aria-hidden
              className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-grape-700"
            />
            <span>{b}</span>
          </li>
        ))}
      </ul>
    </article>
  );
}


function AgentGlyph() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 18 18"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M9 1.5l1.94 4.51L15.75 7l-3.6 3.04L13.2 16.5 9 13.86 4.8 16.5l1.05-6.46L2.25 7l4.81-.99L9 1.5z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}


/* -------------------------------------------------------------------------- */
/* Platform overview                                                          */
/* -------------------------------------------------------------------------- */


function PlatformOverview() {
  return (
    <section className="bg-surface">
      <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-24">
        <div className="grid gap-12 lg:grid-cols-2 lg:items-center">
          <div className="order-2 lg:order-1">
            <p className="text-xs font-medium uppercase tracking-wider text-grape-700">
              The command center
            </p>
            <h2 className="mt-3 text-4xl font-semibold tracking-tight text-ink sm:text-5xl">
              Every agent, one workspace,
              <br />
              same source of truth.
            </h2>
            <p className="mt-4 text-lg text-slate-600">
              Connect once and every agent reads from the same data. Spend,
              conversions, keywords, audit log, recommendations — all of it
              tied back to the platform that produced it. Workspace
              isolation, RBAC, and a per-event audit trail are baked in.
            </p>

            <div className="mt-8 grid gap-4 sm:grid-cols-2">
              <PlatformBullet
                title="Workspace-scoped"
                body="Every record — campaigns, drafts, recs, audits — belongs to one workspace. Members get role-gated access (Owner / Admin / Marketer / Analyst / Viewer)."
              />
              <PlatformBullet
                title="Audit log on every action"
                body="Approvals, executions, autopilot decisions, webhook events — all tagged with actor type, IP, and user-agent. Reviewable by superusers in the admin console."
              />
              <PlatformBullet
                title="API keys + programmatic access"
                body="Mint workspace-scoped keys with their own role floor. Plaintext returned exactly once; SHA-256 hashed at rest. Authorization: ApiKey ak_…"
              />
              <PlatformBullet
                title="Plan-aware quotas"
                body="Per-workspace 30-day rolling caps on agent runs, content drafts, outreach sends, A/B tests, outbound writes, and LLM tokens — with $ spend surfaced live."
              />
            </div>
          </div>

          <div className="order-1 lg:order-2">
            <CommandCenterMock />
          </div>
        </div>
      </div>
    </section>
  );
}


function PlatformBullet({ title, body }: { title: string; body: string }) {
  return (
    <div>
      <h3 className="text-base font-semibold text-ink">{title}</h3>
      <p className="mt-1 text-base text-slate-600">{body}</p>
    </div>
  );
}


function CommandCenterMock() {
  return (
    <div className="relative">
      <div
        aria-hidden
        className="absolute -inset-6 rounded-[2.25rem] bg-grape-gradient opacity-10 blur-3xl"
      />
      <div className="relative rounded-2xl border border-slate-200 bg-surface p-5 shadow-elevate">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <span className="text-xs font-semibold text-ink">Recommendations</span>
          <span className="text-[10px] uppercase tracking-wider text-slate-400">
            this week
          </span>
        </div>
        <ul className="mt-3 flex flex-col divide-y divide-slate-100 text-sm">
          <RecRow title="Pause past-end-date campaign" risk="high" />
          <RecRow title="Set budget on active group" risk="medium" />
          <RecRow title="Refresh outdated blog post" risk="low" />
          <RecRow title="Add LinkedIn audience exclusion" risk="medium" />
        </ul>
        <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3 text-[11px] text-slate-500">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-success" />
            Autopilot: off — manual approvals
          </span>
          <span className="font-mono text-slate-400">workspace · acme</span>
        </div>
      </div>
    </div>
  );
}


function RecRow({ title, risk }: { title: string; risk: "low" | "medium" | "high" }) {
  const cls =
    risk === "high"
      ? "bg-red-50 text-red-700"
      : risk === "medium"
        ? "bg-amber-50 text-amber-700"
        : "bg-grape-100 text-grape-700";
  return (
    <li className="flex items-center justify-between gap-3 py-2">
      <span className="truncate text-slate-700">{title}</span>
      <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${cls}`}>
        {risk}
      </span>
    </li>
  );
}


/* -------------------------------------------------------------------------- */
/* Safety band — Approval / Autopilot differentiator                          */
/* -------------------------------------------------------------------------- */


function SafetyBand() {
  return (
    <section className="bg-grape-soft">
      <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-24">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-xs font-medium uppercase tracking-wider text-grape-700">
            Spend protection
          </p>
          <h2 className="mt-3 text-4xl font-semibold tracking-tight text-ink sm:text-5xl">
            Three modes. You pick the one you trust.
          </h2>
          <p className="mt-3 text-lg text-slate-600">
            AI is allowed to recommend; humans decide what ships — until you
            decide otherwise. Autopilot Mode requires explicit guardrails
            (daily spend cap, % cap per change, conversion threshold, action
            allowlist, risk ceiling) before it'll auto-approve anything.
          </p>
        </div>

        <div className="mt-12 grid gap-5 lg:grid-cols-3">
          <ModeCard
            title="Advisor"
            tagline="Surface only"
            body="Agents analyze and propose. Nothing reaches a provider. The right starting mode for new workspaces."
            tone="muted"
          />
          <ModeCard
            title="Approval"
            tagline="Default"
            body="Agents propose. A human approves. We write to the platform with prior-state capture so any change is reversible."
            tone="primary"
            badge="Recommended"
          />
          <ModeCard
            title="Autopilot"
            tagline="With explicit caps"
            body="Auto-approves recommendations that pass every guardrail you set. Audit-logged as SYSTEM. One-click stop-loss."
            tone="muted"
          />
        </div>
      </div>
    </section>
  );
}


function ModeCard({
  title,
  tagline,
  body,
  tone,
  badge,
}: {
  title: string;
  tagline: string;
  body: string;
  tone: "primary" | "muted";
  badge?: string;
}) {
  const isPrimary = tone === "primary";
  return (
    <div
      className={
        "relative overflow-hidden rounded-2xl border p-6 shadow-card " +
        (isPrimary
          ? "border-grape bg-grape text-white shadow-elevate"
          : "border-slate-200 bg-surface")
      }
    >
      {badge ? (
        <span className="absolute right-4 top-4 rounded-full bg-white/20 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-white">
          {badge}
        </span>
      ) : null}
      <p
        className={
          "text-xs uppercase tracking-wider " +
          (isPrimary ? "text-white/70" : "text-slate-400")
        }
      >
        {tagline}
      </p>
      <h3
        className={
          "mt-2 text-3xl font-semibold tracking-tight " +
          (isPrimary ? "text-white" : "text-ink")
        }
      >
        {title}
      </h3>
      <p
        className={
          "mt-3 text-base " + (isPrimary ? "text-white/85" : "text-slate-600")
        }
      >
        {body}
      </p>
    </div>
  );
}


/* -------------------------------------------------------------------------- */
/* How it works                                                               */
/* -------------------------------------------------------------------------- */


function HowItWorks() {
  return (
    <section className="bg-surface">
      <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-24">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-xs font-medium uppercase tracking-wider text-grape-700">
            How it works
          </p>
          <h2 className="mt-3 text-4xl font-semibold tracking-tight text-ink sm:text-5xl">
            Connect, plan, approve.
          </h2>
        </div>

        <div className="mt-12 grid gap-6 md:grid-cols-3">
          <Step
            number="01"
            title="Connect"
            body="OAuth into Google Ads, Meta, LinkedIn, GA4, and Search Console. Tokens encrypted at rest with Fernet. Disconnect any time."
          />
          <Step
            number="02"
            title="Plan"
            body="Pick an agent or hand the orchestrator a goal. It runs against your live data, surfaces opportunities, and drafts the changes — never alters anything yet."
          />
          <Step
            number="03"
            title="Approve"
            body="Review the recommendation, edit if needed, and approve. We apply the change on the platform with a snapshot diff so it's reversible. Or flip on Autopilot."
          />
        </div>
      </div>
    </section>
  );
}


function Step({
  number,
  title,
  body,
}: {
  number: string;
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-100 bg-cloud p-6">
      <span className="font-mono text-xs font-semibold text-grape-700">
        {number}
      </span>
      <h3 className="mt-3 text-xl font-semibold text-ink">{title}</h3>
      <p className="mt-2 text-base text-slate-600">{body}</p>
    </div>
  );
}


/* -------------------------------------------------------------------------- */
/* Production guarantees (replaces fake testimonials with honest credibility) */
/* -------------------------------------------------------------------------- */


function ProductionGuarantees() {
  const items = [
    {
      heading: "No demo data, ever",
      body: "If an integration isn't connected, you see a connect button — not a fake chart. Every metric on every screen ties back to a real provider call or a saved agent output.",
    },
    {
      heading: "Approval-gated by default",
      body: "Spend changes never happen silently. High-risk recs require Owner approval. Every action is audit-logged with actor, IP, user-agent, and prior state.",
    },
    {
      heading: "Reversible writes",
      body: "Provider mutations capture prior state on the way out. One click reverts a campaign pause, a budget change, or an audience edit — same idempotency window protects against double-writes.",
    },
    {
      heading: "Plan limits, not surprise bills",
      body: "Per-workspace 30-day caps on agent runs, drafts, sends, tests, outbound writes, and LLM tokens. Live $ spend on every billing surface. Hit a cap and the system refuses the next call instead of charging.",
    },
  ];

  return (
    <section className="bg-cloud">
      <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-24">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-xs font-medium uppercase tracking-wider text-grape-700">
            Production guarantees
          </p>
          <h2 className="mt-3 text-4xl font-semibold tracking-tight text-ink sm:text-5xl">
            Built like a SaaS, not a demo.
          </h2>
          <p className="mt-3 text-lg text-slate-600">
            Four rules we don't break. They're enforced in the codebase, not
            in marketing.
          </p>
        </div>

        <div className="mt-12 grid gap-5 md:grid-cols-2">
          {items.map((it) => (
            <div
              key={it.heading}
              className="rounded-2xl border border-slate-100 bg-surface p-6 shadow-card"
            >
              <h3 className="text-lg font-semibold text-ink">{it.heading}</h3>
              <p className="mt-2 text-base text-slate-600">{it.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}




/* -------------------------------------------------------------------------- */
/* FAQ                                                                        */
/* -------------------------------------------------------------------------- */


function FaqSection() {
  const items = [
    {
      q: "Does AdGenieHQ actually change my campaigns, or just suggest things?",
      a: "Both, on your terms. By default every recommendation is suggestion-only until you approve it. Once approved, we apply the change on the connected platform — with prior-state captured so any single write is reversible. Autopilot Mode auto-approves recommendations that pass every guardrail you set; until you turn it on, nothing ships without a human.",
    },
    {
      q: "What happens if I disconnect a provider?",
      a: "Sync stops, recommendations for that platform freeze, and dashboards fall back to honest empty states with a connect button. We don't fabricate data to fill the gap. Tokens are deleted on disconnect; the audit log of past actions stays.",
    },
    {
      q: "Where do my OAuth tokens live?",
      a: "Encrypted at rest with Fernet, never exposed to the frontend, refreshed automatically when supported. Provider calls happen server-side; your browser never touches a provider access token.",
    },
    {
      q: "Is the AI looking at my private data?",
      a: "Only the workspace data you connect, and only when an agent is running for that workspace. LLM calls are scoped per-prompt with no cross-customer training. We don't sell data.",
    },
    {
      q: "What does the audit log capture?",
      a: "Every approval, rejection, execution, autopilot decision, webhook event, API-key mint or revoke, and 2FA enable / disable — tagged with actor type (User / Agent / System), IP, user-agent, and the diff of what changed. Visible to Owners and Admins.",
    },
    {
      q: "Can I program against AdGenieHQ?",
      a: "Yes. Owner-only API keys: workspace-scoped, role-floored, plaintext returned exactly once, SHA-256 hashed at rest. Authenticate with Authorization: ApiKey ak_<prefix>.<secret> on any endpoint a human session can reach.",
    },
  ];
  return (
    <section className="bg-cloud">
      <div className="mx-auto max-w-3xl px-4 py-20 sm:px-6 sm:py-24">
        <div className="text-center">
          <p className="text-xs font-medium uppercase tracking-wider text-grape-700">
            Common questions
          </p>
          <h2 className="mt-3 text-4xl font-semibold tracking-tight text-ink sm:text-5xl">
            Answers, before you ask.
          </h2>
        </div>
        <div className="mt-10 flex flex-col gap-3">
          {items.map((it) => (
            <details
              key={it.q}
              className="group rounded-2xl border border-slate-100 bg-surface px-5 py-4 shadow-card open:shadow-elevate"
            >
              <summary className="flex cursor-pointer items-center justify-between gap-4 text-base font-semibold text-ink marker:hidden">
                <span>{it.q}</span>
                <span
                  aria-hidden
                  className="ml-auto inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-grape-100 text-grape-700 transition-transform group-open:rotate-45"
                >
                  +
                </span>
              </summary>
              <p className="mt-3 text-base text-slate-600">{it.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}


/* -------------------------------------------------------------------------- */
/* Final CTA                                                                  */
/* -------------------------------------------------------------------------- */


function FinalCta() {
  return (
    <section className="relative overflow-hidden bg-grape-gradient">
      <div
        aria-hidden
        className="pointer-events-none absolute -left-24 -top-24 h-72 w-72 rounded-full bg-white/10 blur-3xl"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -bottom-24 -right-16 h-72 w-72 rounded-full bg-white/10 blur-3xl"
      />

      <div className="relative mx-auto max-w-4xl px-4 py-20 text-center sm:px-6 sm:py-24">
        <p className="text-xs font-medium uppercase tracking-wider text-white/70">
          Ready when you are
        </p>
        <h2 className="mt-3 text-4xl font-semibold tracking-tight text-white sm:text-5xl">
          Put your growth team on a real command center.
        </h2>
        <p className="mt-4 text-lg text-white/85">
          Pick a tier, connect one platform, and you'll have your first
          recommendation queued within minutes.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link
            to="/register"
            className="rounded-xl bg-white px-5 py-3 text-sm font-semibold text-[#3E2F84] shadow-elevate transition hover:bg-white/90"
          >
            Create your workspace
          </Link>
          <Link
            to="/login"
            className="rounded-xl border border-white/30 px-5 py-3 text-sm font-semibold text-white hover:bg-white/10"
          >
            Sign in
          </Link>
        </div>
      </div>
    </section>
  );
}
