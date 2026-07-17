import { Link } from "react-router-dom";

import { MarketingLayout } from "@/features/marketing/MarketingLayout";
import { APP_NAME } from "@/lib/constants";

/**
 * Public "About Us" page. Two sections per the founder's brief:
 *   1. Top   — what AdGenieHQ is and who it's for.
 *   2. Bottom — "Pete Nyandeh & AI Marketing Hub" with the founder profile.
 *
 * Copy stays production-honest (CLAUDE.md §1): describes the real platform —
 * connected accounts, specialized agents, approval-gated actions — with no
 * fabricated metrics or testimonials.
 */
export function AboutPage() {
  return (
    <MarketingLayout>
      <AboutHero />
      <WhatWeDo />
      <FounderSection />
    </MarketingLayout>
  );
}


/* -------------------------------------------------------------------------- */
/* Top section — About AdGenieHQ                                              */
/* -------------------------------------------------------------------------- */


function AboutHero() {
  return (
    <section className="relative overflow-hidden bg-grape-gradient text-white">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.07] [background-image:linear-gradient(to_right,#fff_1px,transparent_1px),linear-gradient(to_bottom,#fff_1px,transparent_1px)] [background-size:44px_44px]"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -right-24 -top-24 h-[26rem] w-[26rem] rounded-full bg-violet-electric/40 blur-3xl"
      />

      <div className="relative mx-auto max-w-3xl px-4 py-20 text-center sm:px-6 sm:py-24">
        <p className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs font-medium uppercase tracking-wider text-white backdrop-blur">
          <span className="h-1.5 w-1.5 rounded-full bg-white" />
          About Us
        </p>
        <h1 className="mt-5 text-4xl font-semibold leading-[1.1] tracking-tight text-white sm:text-5xl">
          An always-awake growth team,
          <br className="hidden sm:block" /> not just another dashboard.
        </h1>
        <p className="mt-5 text-lg text-white/80">
          {APP_NAME} is an AI Growth Command Center where businesses connect
          their real ad accounts, analytics platforms, websites, and search
          data — then let specialized AI agents turn that raw signal into
          intelligent, safe, and profitable growth.
        </p>
      </div>
    </section>
  );
}


function WhatWeDo() {
  return (
    <section className="mx-auto max-w-3xl px-4 py-16 sm:px-6">
      <div className="flex flex-col gap-4 text-base leading-relaxed text-slate-600">
        <p>
          Marketing today is scattered across a dozen tools, tabs, and
          platforms. Spend leaks quietly, opportunities go unnoticed, and the
          data needed to make good decisions is buried where no one has time to
          look. {APP_NAME} was built to fix that — to turn ad chaos into
          intelligent growth.
        </p>
        <p>
          Instead of one giant prompt, {APP_NAME} runs on a{" "}
          <span className="font-medium text-ink">
            Master Growth Orchestrator
          </span>{" "}
          coordinating a team of specialized AI Skill Agents. Each agent owns a
          real job: uncovering wasted spend, planning and optimizing campaigns
          across Google, Meta &amp; LinkedIn, strengthening SEO and AI-search
          (GEO) visibility, auditing landing pages for conversion, validating
          tracking, and turning your data into executive-ready reports.
        </p>
        <p>
          Every insight is grounded in your real data and saved to your
          workspace — no demo campaigns, no fake metrics. Sensitive moves like
          launching campaigns or changing budgets stay{" "}
          <span className="font-medium text-ink">approval-gated by default</span>
          , with guarded Autopilot available only when you explicitly turn it on.
          Your OAuth tokens are encrypted at rest, and every external action is
          logged in an audit trail you own.
        </p>
      </div>

      <ul className="mt-10 grid gap-4 sm:grid-cols-2">
        <ValueCard title="Real data only">
          Dashboards, recommendations, and reports are built from your connected
          accounts and saved AI outputs — never placeholder numbers.
        </ValueCard>
        <ValueCard title="Agents with a job">
          A coordinated team for paid ads, SEO/GEO, website conversion,
          tracking, budget safety, and reporting — working around the clock.
        </ValueCard>
        <ValueCard title="Safe by default">
          Approval workflows, budget guardrails, and opt-in Autopilot keep you
          in control of anything that can spend money or change a campaign.
        </ValueCard>
        <ValueCard title="Secure &amp; yours">
          Workspace isolation, role-based access, encrypted tokens, and full
          audit logging. Your data and outputs belong to you.
        </ValueCard>
      </ul>

      <div className="mt-12 flex flex-wrap items-center gap-3">
        <Link
          to="/register"
          className="rounded-xl bg-grape px-5 py-3 text-sm font-semibold text-white shadow-elevate transition hover:bg-grape-800"
        >
          Get started
        </Link>
        <Link
          to="/pricing"
          className="rounded-xl border border-slate-200 px-5 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
        >
          See pricing
        </Link>
      </div>
    </section>
  );
}


function ValueCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <li className="rounded-2xl border border-slate-200 bg-surface p-5 shadow-card">
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-slate-600">{children}</p>
    </li>
  );
}


/* -------------------------------------------------------------------------- */
/* Bottom section — Pete Nyandeh & AI Marketing Hub                           */
/* -------------------------------------------------------------------------- */


function FounderSection() {
  return (
    <section className="border-t border-slate-200 bg-surface-muted">
      <div className="mx-auto max-w-4xl px-4 py-16 sm:px-6 sm:py-20">
        <div className="grid items-start gap-10 sm:grid-cols-[auto,1fr]">
          <div className="mx-auto sm:mx-0">
            <div className="relative">
              <div
                aria-hidden
                className="absolute -inset-3 rounded-3xl bg-grape-gradient opacity-10 blur-2xl"
              />
              {/* Square headshot crop: object-cover fills the frame and the
                  center-20% focal point keeps the face/shoulders in view while
                  trimming the empty headroom on top and the clasped hands at
                  the bottom — a tighter portrait than showing the whole photo. */}
              <img
                src="/pete-nyandeh.png"
                alt="Pete Nyandeh, founder of AI Marketing Hub"
                width={208}
                height={208}
                loading="lazy"
                className="relative h-52 w-52 rounded-3xl border border-white bg-surface object-cover object-[center_20%] shadow-elevate"
              />
            </div>
          </div>

          <div>
            <h2 className="text-2xl font-semibold text-ink sm:text-3xl">
              Pete Nyandeh &amp; AI Marketing Hub
            </h2>
            <div className="mt-4 flex flex-col gap-4 text-base leading-relaxed text-slate-600">
              <p>
                {APP_NAME} is part of the{" "}
                <span className="font-medium text-ink">AI Marketing Hub</span>{" "}
                ecosystem, created by Pete Nyandeh.
              </p>
              <p>
                AI Marketing Hub is a technology and marketing innovation
                platform focused on building practical, powerful, and
                purpose-driven SaaS applications powered by artificial
                intelligence, automation, and modern web technologies.
              </p>
              <p>
                Founded by Pete Nyandeh, AI Marketing Hub develops platforms
                that help businesses, professionals, creators, and organizations
                save time, automate workflows, improve customer experience,
                generate leads, increase productivity, and make better decisions
                using AI.
              </p>
              <p>
                Every app in the AI Marketing Hub ecosystem is built around
                simplicity, automation, growth, and innovation — making advanced
                AI tools easier, more useful, and more accessible for real
                people and real businesses.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
