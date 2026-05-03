import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError } from "@/lib/api-client";
import { getGrowthDna } from "@/lib/onboarding";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { GrowthDna } from "@/types/api";

export function GrowthDnaPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);

  const dna = useQuery({
    queryKey: ["growth-dna", workspaceId],
    queryFn: () => getGrowthDna(workspaceId!),
    enabled: !!workspaceId,
    retry: false,
  });

  if (dna.isLoading) {
    return <div className="text-sm text-slate-400">Loading…</div>;
  }

  if (dna.error) {
    const code = dna.error instanceof ApiError ? dna.error.code : null;
    if (code === "growth_dna_not_found") {
      return (
        <div className="mx-auto max-w-3xl">
          <EmptyState
            title="No Growth DNA Profile yet"
            description="Complete onboarding to generate your readiness scores, recommended first campaigns, and 30-day growth plan."
            action={
              <Link to="/onboarding">
                <Button>Start onboarding</Button>
              </Link>
            }
          />
        </div>
      );
    }
    return (
      <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
        {dna.error instanceof Error ? dna.error.message : "Could not load Growth DNA Profile."}
      </div>
    );
  }

  if (!dna.data) return null;

  return <GrowthDnaView dna={dna.data} />;
}

export function GrowthDnaView({ dna }: { dna: GrowthDna }) {
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header>
        <p className="text-xs uppercase tracking-wider text-grape-700">Growth DNA Profile</p>
        <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">{dna.business_summary}</h1>
        <p className="mt-1 text-xs text-slate-400">
          Generated {new Date(dna.created_at).toLocaleString()} · engine {dna.engine_version}
        </p>
      </header>

      <section className="grid gap-4 sm:grid-cols-2">
        <ScoreCard
          title="Funnel readiness"
          score={dna.funnel_readiness_score}
          subtitle="Audience clarity, offer clarity, landing pages, brand voice, analytics."
        />
        <ScoreCard
          title="Paid ads readiness"
          score={dna.paid_ads_readiness_score}
          subtitle="Budget, conversion goal, audience, geo, platforms, analytics."
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="ICP summary" />
          <p className="mt-3 text-sm leading-relaxed text-slate-700">{dna.icp_summary}</p>
        </Card>
        <Card>
          <CardHeader title="Offer positioning" />
          <p className="mt-3 text-sm leading-relaxed text-slate-700">{dna.offer_positioning}</p>
        </Card>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="SEO & GEO opportunity" />
          <p className="mt-3 text-sm leading-relaxed text-slate-700">
            {dna.seo_geo_opportunity_summary}
          </p>
        </Card>
        <Card>
          <CardHeader title="Tracking readiness" />
          <p className="mt-3 text-sm leading-relaxed text-slate-700">{dna.tracking_readiness}</p>
        </Card>
      </section>

      <Card>
        <CardHeader
          title="Website conversion risks"
          subtitle="Things to fix before scaling spend."
        />
        {dna.website_conversion_risks.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">No critical risks detected from your inputs.</p>
        ) : (
          <ul className="mt-3 flex flex-col gap-2 text-sm text-slate-700">
            {dna.website_conversion_risks.map((r) => (
              <li key={r} className="flex gap-2">
                <span aria-hidden className="mt-1 size-1.5 shrink-0 rounded-full bg-warning" />
                {r}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <CardHeader
          title="Recommended first campaigns"
          subtitle="A starting allocation across the platforms you selected."
        />
        <ul className="mt-3 flex flex-col gap-3">
          {dna.recommended_first_campaigns.map((c) => (
            <li
              key={c.platform}
              className="flex flex-col gap-1 rounded-xl border border-slate-100 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div>
                <div className="text-sm font-semibold text-ink">{c.platform}</div>
                <div className="text-xs text-slate-500">{c.objective}</div>
                <div className="mt-1 text-xs text-slate-500">{c.rationale}</div>
              </div>
              <span className="pill pill-grape self-start sm:self-auto">
                {c.budget_share_pct}% of budget
              </span>
            </li>
          ))}
        </ul>
      </Card>

      <Card>
        <CardHeader
          title="30-day growth plan"
          subtitle="Adapts based on your readiness scores. Each week's deliverables are derived from the gaps in your onboarding answers."
        />
        <ol className="mt-3 grid gap-3 lg:grid-cols-2">
          {dna.thirty_day_growth_plan.map((week) => (
            <li
              key={week.week}
              className="rounded-xl border border-slate-100 bg-grape-soft/40 px-4 py-3"
            >
              <div className="flex items-center gap-2">
                <span className="pill pill-grape">Week {week.week}</span>
                <span className="text-sm font-semibold text-ink">{week.focus}</span>
              </div>
              <ul className="mt-2 flex flex-col gap-1.5 text-sm text-slate-700">
                {week.deliverables.map((d) => (
                  <li key={d} className="flex gap-2">
                    <span aria-hidden className="mt-1 size-1.5 shrink-0 rounded-full bg-grape" />
                    {d}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      </Card>

      <div className="flex items-center justify-between">
        <Link
          to="/onboarding"
          className="text-sm font-medium text-grape-700 hover:text-grape-800"
        >
          Refine onboarding answers →
        </Link>
        <Link
          to="/"
          className="text-sm font-medium text-slate-500 hover:text-ink"
        >
          Back to Command Center
        </Link>
      </div>
    </div>
  );
}

function ScoreCard({
  title,
  score,
  subtitle,
}: {
  title: string;
  score: number;
  subtitle: string;
}) {
  const tone =
    score >= 80
      ? "text-success"
      : score >= 50
        ? "text-grape-700"
        : "text-warning";
  return (
    <Card>
      <CardHeader title={title} subtitle={subtitle} />
      <div className="mt-3 flex items-baseline gap-2">
        <span className={cn("text-4xl font-semibold tracking-tight", tone)}>{score}</span>
        <span className="text-sm text-slate-400">/ 100</span>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className={cn(
            "h-full rounded-full transition-all",
            score >= 80
              ? "bg-success"
              : score >= 50
                ? "bg-grape"
                : "bg-warning",
          )}
          style={{ width: `${Math.max(2, Math.min(100, score))}%` }}
        />
      </div>
    </Card>
  );
}
