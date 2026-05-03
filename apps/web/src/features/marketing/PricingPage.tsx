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
    monthly: 99,
    description: "Small teams running their first paid + SEO programs.",
    features: [
      "100 agent runs / 30 days",
      "10 landing pages",
      "50 content drafts / 30 days",
      "200 outreach emails / 30 days",
      "200 provider writes / 30 days",
      "200K LLM tokens / 30 days",
    ],
  },
  {
    name: "Pro",
    monthly: 299,
    description: "Full agent suite for serious operators.",
    features: [
      "500 agent runs / 30 days",
      "50 landing pages",
      "300 content drafts / 30 days",
      "2,000 outreach emails / 30 days",
      "1,000 provider writes / 30 days",
      "1.5M LLM tokens / 30 days",
    ],
    highlight: true,
  },
  {
    name: "Agency",
    monthly: 899,
    description: "Unlimited usage + multi-team workspaces.",
    features: [
      "Unlimited agent runs",
      "Unlimited landing pages",
      "Unlimited content drafts",
      "Unlimited outreach emails",
      "Unlimited provider writes",
      "Unlimited LLM tokens",
    ],
  },
];


/**
 * AdVanta Concierge — managed-service add-on. Sold on top of any SaaS
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
          <h1 className="text-3xl font-semibold text-ink sm:text-4xl">
            Pricing that grows with your spend.
          </h1>
          <p className="mt-3 text-slate-600">
            Every tier includes the full agent suite, real provider writes,
            risk-gated approvals, and the audit log. Quotas keep your bill
            predictable as usage scales.
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
                    : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50",
                )}
              >
                Choose plan
              </Link>
            </li>
          ))}
        </ul>

        <p className="mt-8 text-center text-xs text-slate-400">
          Need higher limits or annual billing? Email{" "}
          <a className="text-grape-700" href="mailto:hello@advantaai.com">
            hello@advantaai.com
          </a>
          .
        </p>
      </section>

      <ConciergeSection />
    </MarketingLayout>
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
            AdVanta Concierge · Optional add-on
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
                  "card flex flex-col gap-4 bg-white p-6",
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
                  href="mailto:hello@advantaai.com?subject=AdVanta%20Concierge%20%E2%80%94%20interest"
                  className={cn(
                    "rounded-xl px-4 py-2 text-center text-sm font-semibold transition",
                    tier.highlight
                      ? "bg-grape text-white hover:bg-grape-800"
                      : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50",
                  )}
                >
                  Talk to us
                </a>
              </li>
            );
          })}
        </ul>

        <div className="mx-auto mt-10 max-w-3xl rounded-2xl border border-slate-200 bg-white px-6 py-6 text-center">
          <p className="text-xs font-semibold uppercase tracking-wider text-grape-700">
            Custom · Enterprise
          </p>
          <p className="mt-2 text-base text-slate-600">
            Accounts above $100k/mo ad spend, agencies running multiple client
            workspaces, or scopes outside the playbook —{" "}
            <a
              className="text-grape-700 underline"
              href="mailto:hello@advantaai.com?subject=AdVanta%20Concierge%20%E2%80%94%20enterprise"
            >
              email us
            </a>{" "}
            for a tailored quote.
          </p>
        </div>

        <p className="mt-8 text-center text-xs text-slate-400">
          Concierge is a separate engagement, billed alongside your AdVanta SaaS
          subscription. 12-month minimum on Standard and Premium tiers.
        </p>
      </div>
    </section>
  );
}
