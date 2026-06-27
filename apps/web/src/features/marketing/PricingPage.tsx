import { Link } from "react-router-dom";

import { MarketingLayout } from "@/features/marketing/MarketingLayout";
import { cn } from "@/lib/utils";

type Tier = {
  name: string;
  monthly: number;
  description: string;
  features: string[];
  highlight?: boolean;
};

type ConciergeTier = {
  name: string;
  monthly: number;
  hoursPerMonth: string;
  description: string;
  features: string[];
  highlight?: boolean;
};

const TIERS: Tier[] = [
  {
    name: "Starter",
    monthly: 67,
    description: "Small teams running their first paid + SEO programs.",
    features: [
      "Build & launch ads on Google, Meta & LinkedIn",
      "AI ad copy + creative concepts + campaign builder",
      "Full agent suite (Paid, SEO, Website, Outreach)",
      "3,000 AI credits · 50 landing pages · 15 seats",
      "1,000 provider writes / mo",
    ],
  },
  {
    name: "Pro",
    monthly: 129,
    description: "Build, launch & optimize ads at serious scale.",
    features: [
      "Build, launch & optimize ads at scale",
      "AI ad copy + creative + guarded Autopilot",
      "Budget guardrails + overspend alerts",
      "12,000 AI credits · 200 landing pages · 50 seats",
      "5,000 provider writes / mo",
    ],
    highlight: true,
  },
  {
    name: "Agency",
    monthly: 299,
    description: "Unlimited ad campaigns + multi-team workspaces.",
    features: [
      "Unlimited ad campaigns across all platforms",
      "Multi-team workspaces + priority support",
      "AI ad creative + guarded Autopilot",
      "Unlimited AI credits, landing pages & seats",
      "Unlimited provider writes / mo",
    ],
  },
];

/**
 * Full feature matrix powering the per-tier "See all features" accordion below
 * each plan card. Kept honest to what the product actually ships (campaign
 * build/launch/publish, the agent suite, real OAuth integrations, the audit
 * log). `true` = included, `false` = not in this tier, string = the tier value.
 */
type TierKey = "Starter" | "Pro" | "Agency";
type FeatureValue = boolean | string;
type FeatureRow = { label: string; values: Record<TierKey, FeatureValue> };
type FeatureGroup = { category: string; rows: FeatureRow[] };

const FEATURE_MATRIX: FeatureGroup[] = [
  {
    category: "Ads & Campaigns",
    rows: [
      { label: "Cross-platform campaign builder", values: { Starter: true, Pro: true, Agency: true } },
      { label: "One-click ad publishing (Google, Meta, LinkedIn)", values: { Starter: true, Pro: true, Agency: true } },
      { label: "AI ad copy + creative concept generation", values: { Starter: true, Pro: true, Agency: true } },
      { label: "Campaign launch & management", values: { Starter: true, Pro: true, Agency: true } },
      { label: "Performance analytics & insights", values: { Starter: true, Pro: true, Agency: true } },
      { label: "Budget guardrails + overspend alerts", values: { Starter: true, Pro: true, Agency: true } },
      { label: "Risk-gated approval workflows", values: { Starter: true, Pro: true, Agency: true } },
      { label: "Guarded Autopilot (auto-execute within limits)", values: { Starter: false, Pro: true, Agency: true } },
    ],
  },
  {
    category: "AI agents & content",
    rows: [
      { label: "Full agent suite (Paid, SEO/GEO, Website, ICP, Creative, Reporting)", values: { Starter: true, Pro: true, Agency: true } },
      { label: "Growth DNA profile + 30-day plan", values: { Starter: true, Pro: true, Agency: true } },
      { label: "Suggested Copies — keyword, ad, landing, email & social (.txt/.docx)", values: { Starter: true, Pro: true, Agency: true } },
      { label: "Creative strategy + A/B test generation", values: { Starter: true, Pro: true, Agency: true } },
      { label: "Bring your own LLM keys (OpenAI / Anthropic / Google)", values: { Starter: true, Pro: true, Agency: true } },
      { label: "Monthly AI credits", values: { Starter: "3,000", Pro: "12,000", Agency: "Unlimited" } },
    ],
  },
  {
    category: "Limits & scale",
    rows: [
      { label: "Landing pages", values: { Starter: "50", Pro: "200", Agency: "Unlimited" } },
      { label: "Team members", values: { Starter: "15", Pro: "50", Agency: "Unlimited" } },
      { label: "Provider writes / mo", values: { Starter: "1,000", Pro: "5,000", Agency: "Unlimited" } },
      { label: "Multi-team workspaces", values: { Starter: false, Pro: false, Agency: true } },
    ],
  },
  {
    category: "Platform & security",
    rows: [
      { label: "Real OAuth integrations (Google Ads, Meta, LinkedIn, GA4, Search Console)", values: { Starter: true, Pro: true, Agency: true } },
      { label: "Role-based access control", values: { Starter: true, Pro: true, Agency: true } },
      { label: "Full audit log of every action", values: { Starter: true, Pro: true, Agency: true } },
      { label: "Encrypted token storage", values: { Starter: true, Pro: true, Agency: true } },
    ],
  },
];


/**
 * AdGenieHQ Concierge — managed-service add-on. Sold on top of any SaaS
 * tier for customers who want a documented operational rhythm with a
 * human reviewer in the loop. Hours and scope follow the playbook in
 * docs/human-in-the-loop-playbook.md.
 */
const CONCIERGE_TIERS: ConciergeTier[] = [
  {
    name: "Essentials",
    monthly: 299,
    hoursPerMonth: "5–7 hrs / mo",
    description: "Daily hygiene only. Best for SMBs running their first paid programs.",
    features: [
      "Daily recommendation triage (24-hr response SLA)",
      "Weekly A/B winner ship + reject backlog",
      "Weekly written briefing note to the owner",
      "Provider sync + integration health checks",
    ],
  },
  {
    name: "Standard",
    monthly: 799,
    hoursPerMonth: "10–14 hrs / mo",
    description: "Full operational rhythm + monthly strategic review.",
    features: [
      "Everything in Essentials",
      "Monthly strategic alignment review",
      "ICP + competitor refresh, monthly",
      "Autopilot rule recalibration",
      "Monthly readout call with the owner",
    ],
    highlight: true,
  },
  {
    name: "Premium",
    monthly: 1499,
    hoursPerMonth: "16–25 hrs / mo",
    description: "End-to-end coverage including quarterly strategic reset.",
    features: [
      "Everything in Standard",
      "Quarterly Growth DNA refresh + 90-day plan",
      "Channel-mix review and scaling recommendations",
      "Creative brief generation (60-day fatigue cadence)",
      "Tracking + attribution audit, quarterly",
      "QBR with the owner",
    ],
  },
];

export function PricingPage() {
  return (
    <MarketingLayout>
      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <header className="mx-auto max-w-2xl text-center">
          <p className="text-xs font-semibold uppercase tracking-wider text-grape-700">
            AI Ad Creation &amp; Campaign Platform
          </p>
          <h1 className="mt-3 text-3xl font-semibold text-ink sm:text-4xl">
            Pricing that grows with your spend.
          </h1>
          <p className="mt-3 text-slate-600">
            AdGenieHQ is your AI ad-creation platform: build campaigns, generate
            ad copy and creative, and publish to Google, Meta &amp; LinkedIn in
            one click — then let the agents optimize spend, SEO, and conversion.
            Every tier ships the full agent suite, risk-gated approvals, and the
            audit log; AI work runs on monthly credits (an agent run is 10
            credits, a content draft 5) so your bill stays predictable. Expand{" "}
            <span className="font-medium text-slate-700">See all features</span>{" "}
            on any plan for the full comparison.
          </p>
        </header>

        <ul className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {TIERS.map((tier) => (
            <li
              key={tier.name}
              className={cn(
                "card flex flex-col gap-4 p-6",
                tier.highlight && "border-grape-200 ring-1 ring-grape-200",
              )}
            >
              <div>
                <h3 className="text-sm font-semibold uppercase tracking-wider text-grape-700">
                  {tier.name}
                </h3>
                <p className="mt-2 text-3xl font-semibold text-ink">
                  ${tier.monthly}
                  <span className="ml-1 text-sm font-normal text-slate-400">/mo</span>
                </p>
                <p className="mt-2 text-sm text-slate-500">{tier.description}</p>
              </div>
              <ul className="flex flex-1 flex-col gap-1.5 text-sm text-slate-600">
                {tier.features.map((f) => (
                  <li key={f} className="flex gap-2">
                    <span aria-hidden className="mt-1 size-1.5 rounded-full bg-grape" />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              <Link
                to="/register"
                className={cn(
                  "rounded-xl px-4 py-2 text-center text-sm font-semibold transition",
                  tier.highlight
                    ? "bg-grape text-white hover:bg-grape-800"
                    : "border border-slate-200 bg-surface text-slate-700 hover:bg-slate-50",
                )}
              >
                Choose plan
              </Link>
              <TierFeatureAccordion tier={tier.name as TierKey} />
            </li>
          ))}
        </ul>

        <p className="mt-8 text-center text-xs text-slate-400">
          Need higher limits or annual billing? Email{" "}
          <a className="text-grape-700" href="mailto:support@aimarketinghub.io">
            support@aimarketinghub.io
          </a>
          .
        </p>
      </section>

      <ConciergeSection />
    </MarketingLayout>
  );
}


/**
 * Per-tier "See all features" accordion shown under each plan card. Native
 * <details> so it's accessible + zero-JS, no extra deps. Renders the full
 * feature matrix from the selected tier's perspective: included rows get a
 * check, tier-specific values are shown inline, and rows the tier doesn't
 * include are dimmed with a dash — so opening each plan reads as a comparison.
 */
function TierFeatureAccordion({ tier }: { tier: TierKey }) {
  return (
    <details className="group mt-1 rounded-xl border border-slate-200 bg-surface">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-2.5 text-sm font-medium text-grape-700 [&::-webkit-details-marker]:hidden">
        <span>See all features</span>
        <svg
          viewBox="0 0 20 20"
          aria-hidden
          className="size-4 shrink-0 text-slate-400 transition group-open:rotate-180"
        >
          <path fill="currentColor" d="M5.5 7.5 10 12l4.5-4.5z" />
        </svg>
      </summary>
      <div className="flex flex-col gap-4 border-t border-slate-100 px-4 py-4">
        {FEATURE_MATRIX.map((group) => (
          <div key={group.category}>
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              {group.category}
            </p>
            <ul className="mt-2 flex flex-col gap-1.5 text-sm">
              {group.rows.map((row) => {
                const value = row.values[tier];
                const included = value !== false;
                return (
                  <li key={row.label} className="flex items-start gap-2">
                    {included ? (
                      <svg
                        viewBox="0 0 20 20"
                        aria-hidden
                        className="mt-0.5 size-4 shrink-0 text-grape"
                      >
                        <path
                          fill="currentColor"
                          d="M7.6 13.6 4 10l-1.3 1.3 4.9 4.9L17.3 6.5 16 5.2z"
                        />
                      </svg>
                    ) : (
                      <span
                        aria-hidden
                        className="mt-0.5 w-4 shrink-0 text-center text-slate-300"
                      >
                        —
                      </span>
                    )}
                    <span className={cn("flex-1", included ? "text-slate-600" : "text-slate-400")}>
                      {row.label}
                      {typeof value === "string" ? (
                        <span className="font-semibold text-ink"> · {value}</span>
                      ) : null}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </details>
  );
}


/**
 * Optional managed-service add-on. Lives below the SaaS tiers so it
 * reads as "if you want a human in the loop, add this on top." Same
 * card shape as the SaaS tiers, slightly different palette so the
 * visual hierarchy makes clear it's an add-on, not a separate product.
 */
function ConciergeSection() {
  return (
    <section className="border-t border-slate-200 bg-grape-soft/40">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <header className="mx-auto max-w-2xl text-center">
          <p className="text-xs font-semibold uppercase tracking-wider text-grape-700">
            AdGenieHQ Concierge · Optional add-on
          </p>
          <h2 className="mt-3 text-3xl font-semibold text-ink sm:text-4xl">
            When you want a human in the loop.
          </h2>
          <p className="mt-3 text-slate-600">
            A managed-service layer for customers who want the agents plus
            a human reviewer following our documented operational
            playbook. Pair Concierge with any SaaS tier above.
          </p>
        </header>

        <ul className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {CONCIERGE_TIERS.map((tier) => {
            const annual = Math.round(tier.monthly * 12 * 0.85);
            return (
              <li
                key={tier.name}
                className={cn(
                  "card flex flex-col gap-4 bg-surface p-6",
                  tier.highlight && "border-grape-300 ring-2 ring-grape-200 shadow-elevate",
                )}
              >
                <div>
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-grape-700">
                    {tier.name}
                  </h3>
                  <p className="mt-2 text-3xl font-semibold text-ink">
                    ${tier.monthly}
                    <span className="ml-1 text-sm font-normal text-slate-400">/mo</span>
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    or ${annual.toLocaleString()}/year billed annually (–15%)
                  </p>
                  <p className="mt-2 inline-flex items-center gap-2 rounded-full bg-grape-50 px-2.5 py-0.5 text-xs font-medium text-grape-700">
                    {tier.hoursPerMonth}
                  </p>
                  <p className="mt-3 text-sm text-slate-500">{tier.description}</p>
                </div>
                <ul className="flex flex-1 flex-col gap-1.5 text-sm text-slate-600">
                  {tier.features.map((f) => (
                    <li key={f} className="flex gap-2">
                      <span
                        aria-hidden
                        className="mt-1 size-1.5 shrink-0 rounded-full bg-grape"
                      />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
                <a
                  href="mailto:support@aimarketinghub.io?subject=AdGenieHQ%20Concierge%20%E2%80%94%20interest"
                  className={cn(
                    "rounded-xl px-4 py-2 text-center text-sm font-semibold transition",
                    tier.highlight
                      ? "bg-grape text-white hover:bg-grape-800"
                      : "border border-slate-200 bg-surface text-slate-700 hover:bg-slate-50",
                  )}
                >
                  Talk to us
                </a>
              </li>
            );
          })}
        </ul>

        <div className="mx-auto mt-10 max-w-3xl rounded-2xl border border-slate-200 bg-surface px-6 py-6 text-center">
          <p className="text-xs font-semibold uppercase tracking-wider text-grape-700">
            Custom · Enterprise
          </p>
          <p className="mt-2 text-base text-slate-600">
            Accounts above $100k/mo ad spend, agencies running multiple client
            workspaces, or scopes outside the playbook —{" "}
            <a
              className="text-grape-700 underline"
              href="mailto:support@aimarketinghub.io?subject=AdGenieHQ%20Concierge%20%E2%80%94%20enterprise"
            >
              email us
            </a>{" "}
            for a tailored quote.
          </p>
        </div>

        <p className="mt-8 text-center text-xs text-slate-400">
          Concierge is a separate engagement, billed alongside your AdGenieHQ SaaS
          subscription. 12-month minimum on Standard and Premium tiers.
        </p>
      </div>
    </section>
  );
}
