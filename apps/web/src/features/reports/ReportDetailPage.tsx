import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import { fetchReportBlob, getReport } from "@/lib/reports";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { ReportPayload } from "@/types/api";


export function ReportDetailPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const { reportId } = useParams<{ reportId: string }>();

  const detail = useQuery({
    queryKey: ["report", workspaceId, reportId],
    queryFn: () => getReport(workspaceId!, reportId!),
    enabled: !!workspaceId && !!reportId,
  });

  const [busy, setBusy] = useState<"pdf" | "csv" | null>(null);

  async function download(format: "pdf" | "csv") {
    if (!workspaceId || !reportId || !detail.data) return;
    setBusy(format);
    try {
      const blob = await fetchReportBlob(workspaceId, reportId, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${detail.data.title.replace(/[^a-z0-9_-]+/gi, "_")}.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } finally {
      setBusy(null);
    }
  }

  if (detail.isLoading) return <div className="text-sm text-slate-400">Loading…</div>;
  if (detail.error) {
    const code = detail.error instanceof ApiError ? detail.error.code : null;
    return (
      <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
        {code === "report_not_found"
          ? "Report not found in this workspace."
          : detail.error instanceof Error
            ? detail.error.message
            : "Could not load."}
      </div>
    );
  }
  if (!detail.data) return null;

  const report = detail.data;
  const payload: ReportPayload = report.payload ?? {};

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-grape-700">Report</p>
          <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">{report.title}</h1>
          <p className="mt-1 text-xs text-slate-400">
            {payload.period?.start
              ? new Date(payload.period.start).toLocaleDateString()
              : "—"}
            {" → "}
            {payload.period?.end ? new Date(payload.period.end).toLocaleDateString() : "—"}{" "}
            · generated {new Date(report.created_at).toLocaleString()}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            onClick={() => download("pdf")}
            disabled={busy !== null}
          >
            {busy === "pdf" ? "Downloading…" : "Download PDF"}
          </Button>
          <Button variant="secondary" onClick={() => download("csv")} disabled={busy !== null}>
            {busy === "csv" ? "Downloading…" : "Download CSV"}
          </Button>
        </div>
      </header>

      {payload.summary ? <SummarySection payload={payload} /> : null}
      {payload.top_recommendations && payload.top_recommendations.length > 0 ? (
        <RecommendationsSection payload={payload} />
      ) : null}
      {payload.agent_runs && payload.agent_runs.length > 0 ? (
        <AgentRunsSection payload={payload} />
      ) : null}
      {payload.campaigns && payload.campaigns.total > 0 ? (
        <CampaignsSection payload={payload} />
      ) : null}
      {payload.seo?.present ? <SeoSection payload={payload} /> : null}
      {payload.landing_pages && payload.landing_pages.length > 0 ? (
        <LandingPagesSection payload={payload} />
      ) : null}
      {payload.executions && payload.executions.total > 0 ? (
        <ExecutionsSection payload={payload} />
      ) : null}
      {payload.content_drafts && payload.content_drafts.total > 0 ? (
        <ContentDraftsSection payload={payload} />
      ) : null}
      {payload.outreach && payload.outreach.emails_total > 0 ? (
        <OutreachSection payload={payload} />
      ) : null}
      {payload.ab_tests && payload.ab_tests.total > 0 ? (
        <AbTestsSection payload={payload} />
      ) : null}
      {payload.growth_dna ? <GrowthDnaSection payload={payload} /> : null}

      <Link to="/reports" className="text-sm font-medium text-grape-700 hover:text-grape-800">
        ← Back to reports
      </Link>
    </div>
  );
}


function SummarySection({ payload }: { payload: ReportPayload }) {
  const s = payload.summary;
  if (!s) return null;
  const tiles: { label: string; value: number | string }[] = [
    { label: "Agent runs", value: s.agent_runs_total },
    { label: "Open recs", value: s.recommendations_by_status.open ?? 0 },
    { label: "Approved", value: s.recommendations_by_status.approved ?? 0 },
    { label: "Rejected", value: s.recommendations_by_status.rejected ?? 0 },
    { label: "High-risk recs", value: s.recommendations_by_risk.high ?? 0 },
    { label: "Campaigns total / active", value: `${s.campaigns_total} / ${s.campaigns_active}` },
    { label: "Landing pages audited", value: s.landing_pages_audited },
    { label: "Keywords tracked", value: s.keywords_tracked },
  ];
  return (
    <Card>
      <CardHeader title="At a glance" />
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {tiles.map((t) => (
          <div key={t.label} className="rounded-xl border border-slate-100 px-3 py-2">
            <div className="text-[11px] uppercase tracking-wider text-slate-400">{t.label}</div>
            <div className="mt-0.5 text-xl font-semibold text-ink">{t.value}</div>
          </div>
        ))}
      </div>
    </Card>
  );
}


function RecommendationsSection({ payload }: { payload: ReportPayload }) {
  const recs = payload.top_recommendations ?? [];
  return (
    <Card>
      <CardHeader title="Top open recommendations" />
      <ul className="mt-3 flex flex-col gap-2">
        {recs.map((r) => (
          <li
            key={r.id}
            className="flex items-start justify-between gap-3 rounded-xl border border-slate-100 px-4 py-3"
          >
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold text-ink">{r.title}</div>
              <div className="mt-1 text-xs text-slate-500">{r.suggested_action}</div>
            </div>
            <RiskPill risk={r.risk_level} />
          </li>
        ))}
      </ul>
    </Card>
  );
}


function AgentRunsSection({ payload }: { payload: ReportPayload }) {
  const runs = payload.agent_runs ?? [];
  return (
    <Card>
      <CardHeader title="Agent activity" />
      <ul className="mt-3 flex flex-col divide-y divide-slate-100 text-sm">
        {runs.map((r) => (
          <li key={r.id} className="flex items-center justify-between gap-3 py-2">
            <Link
              to={`/agents/runs/${r.id}`}
              className="font-mono text-xs text-grape-700 hover:text-grape-800"
            >
              {r.agent_type}
            </Link>
            <span className="text-xs text-slate-400">
              {r.started_at ? new Date(r.started_at).toLocaleString() : "—"}
            </span>
            <span className="pill bg-grape-100 text-grape-700">{r.recommendation_count} recs</span>
            <span
              className={cn(
                "pill",
                r.status === "succeeded" && "pill-success",
                r.status === "failed" && "pill-danger",
                r.status === "running" && "pill-grape",
              )}
            >
              {r.status}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}


function CampaignsSection({ payload }: { payload: ReportPayload }) {
  const c = payload.campaigns;
  if (!c) return null;
  return (
    <Card>
      <CardHeader title="Paid ads" />
      <dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Total" value={c.total} />
        <Stat label="No budget" value={c.active_without_budget} tone={c.active_without_budget > 0 ? "warning" : undefined} />
        <Stat label="Stale active" value={c.stale_active} tone={c.stale_active > 0 ? "danger" : undefined} />
        <div>
          <dt className="text-[11px] uppercase tracking-wider text-slate-400">Per platform</dt>
          <dd className="mt-1 flex flex-wrap gap-2">
            {Object.entries(c.per_provider).map(([p, n]) => (
              <span key={p} className="pill pill-grape">
                {p}: {n}
              </span>
            ))}
          </dd>
        </div>
      </dl>
    </Card>
  );
}


function SeoSection({ payload }: { payload: ReportPayload }) {
  const seo = payload.seo;
  if (!seo) return null;
  const keywords = seo.top_keywords ?? [];
  return (
    <Card>
      <CardHeader
        title="SEO & GEO"
        subtitle={seo.site_url ?? undefined}
        action={
          seo.last_crawled_at ? (
            <span className="text-xs text-slate-400">
              Last crawled {new Date(seo.last_crawled_at).toLocaleString()}
            </span>
          ) : null
        }
      />
      {keywords.length > 0 ? (
        <div className="mt-3 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-xs uppercase tracking-wider text-slate-400">
                <th className="px-3 py-2">Query</th>
                <th className="px-3 py-2 text-right">Impr.</th>
                <th className="px-3 py-2 text-right">Pos.</th>
                <th className="px-3 py-2 text-right">Opportunity</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {keywords.map((kw) => (
                <tr key={kw.query}>
                  <td className="max-w-md truncate px-3 py-2 text-ink" title={kw.query}>
                    {kw.query}
                  </td>
                  <td className="px-3 py-2 text-right text-slate-700">
                    {kw.impressions.toLocaleString()}
                  </td>
                  <td className="px-3 py-2 text-right text-slate-700">
                    {kw.position.toFixed(1)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <span className="pill pill-grape">{kw.opportunity_score}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-500">
          No keyword data yet. Connect Search Console and run a sync from the SEO &amp; GEO page.
        </p>
      )}
    </Card>
  );
}


function LandingPagesSection({ payload }: { payload: ReportPayload }) {
  const pages = payload.landing_pages ?? [];
  return (
    <Card>
      <CardHeader title="Landing pages" />
      <ul className="mt-3 flex flex-col divide-y divide-slate-100 text-sm">
        {pages.map((lp) => (
          <li key={lp.id} className="flex items-center justify-between gap-3 py-2">
            <span className="truncate text-ink">{lp.label ?? new URL(lp.url).pathname}</span>
            <div className="flex items-center gap-2 text-xs">
              <Score label="Conv." value={lp.scores?.conversion ?? null} />
              <Score label="Mobile" value={lp.scores?.mobile_ux ?? null} />
              <Score label="Speed" value={lp.scores?.page_speed ?? null} />
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}


function ExecutionsSection({ payload }: { payload: ReportPayload }) {
  const ex = payload.executions;
  if (!ex) return null;
  return (
    <Card>
      <CardHeader title="Provider writes" subtitle="Recommendation executions during the period." />
      <dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Total" value={ex.total} />
        <Stat
          label="Succeeded"
          value={ex.by_status.succeeded ?? 0}
          tone={(ex.by_status.failed ?? 0) > 0 ? undefined : undefined}
        />
        <Stat
          label="Failed"
          value={ex.by_status.failed ?? 0}
          tone={(ex.by_status.failed ?? 0) > 0 ? "danger" : undefined}
        />
        <div>
          <dt className="text-[11px] uppercase tracking-wider text-slate-400">Per provider</dt>
          <dd className="mt-1 flex flex-wrap gap-2">
            {Object.entries(ex.by_provider).map(([p, n]) => (
              <span key={p} className="pill pill-grape">
                {p}: {n}
              </span>
            ))}
          </dd>
        </div>
      </dl>
    </Card>
  );
}


function ContentDraftsSection({ payload }: { payload: ReportPayload }) {
  const c = payload.content_drafts;
  if (!c) return null;
  return (
    <Card>
      <CardHeader title="Content drafts" subtitle="Generated and published in the period." />
      <dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Total" value={c.total} />
        <Stat label="Published" value={c.by_status.published ?? 0} tone={(c.by_status.published ?? 0) > 0 ? undefined : undefined} />
        <Stat label="Draft" value={c.by_status.draft ?? 0} />
        <div>
          <dt className="text-[11px] uppercase tracking-wider text-slate-400">By type</dt>
          <dd className="mt-1 flex flex-wrap gap-2">
            {Object.entries(c.by_type).map(([t, n]) => (
              <span key={t} className="pill pill-grape">
                {t}: {n}
              </span>
            ))}
          </dd>
        </div>
      </dl>
    </Card>
  );
}


function OutreachSection({ payload }: { payload: ReportPayload }) {
  const o = payload.outreach;
  if (!o) return null;
  return (
    <Card>
      <CardHeader title="Backlink outreach" subtitle="Emails and prospect funnel." />
      <dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Sent" value={o.emails_sent} />
        <Stat label="Replied" value={o.emails_replied} tone={o.emails_replied > 0 ? undefined : undefined} />
        <Stat label="Bounced" value={o.emails_bounced} tone={o.emails_bounced > 0 ? "warning" : undefined} />
        <Stat label="Reply rate" value={`${(o.reply_rate * 100).toFixed(1)}%`} />
        <Stat label="Prospects" value={o.prospects_total} />
        <Stat label="Won" value={o.prospects_won} />
      </dl>
    </Card>
  );
}


function AbTestsSection({ payload }: { payload: ReportPayload }) {
  const a = payload.ab_tests;
  if (!a) return null;
  return (
    <Card>
      <CardHeader title="A/B tests" subtitle="Experiments created in the period." />
      <dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Total" value={a.total} />
        <Stat label="Launched" value={a.by_status.launched ?? 0} />
        <Stat label="Completed" value={a.by_status.completed ?? 0} />
        <Stat label="With winner" value={a.completed_with_winner} tone={a.completed_with_winner > 0 ? undefined : undefined} />
      </dl>
    </Card>
  );
}


function GrowthDnaSection({ payload }: { payload: ReportPayload }) {
  const dna = payload.growth_dna;
  if (!dna) return null;
  return (
    <Card>
      <CardHeader title="Growth DNA" subtitle={`engine ${dna.engine_version}`} />
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Stat label="Funnel readiness" value={`${dna.funnel_readiness_score} / 100`} />
        <Stat label="Paid ads readiness" value={`${dna.paid_ads_readiness_score} / 100`} />
      </div>
    </Card>
  );
}


function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | string;
  tone?: "warning" | "danger";
}) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wider text-slate-400">{label}</dt>
      <dd
        className={cn(
          "mt-0.5 text-xl font-semibold",
          tone === "warning" && "text-warning",
          tone === "danger" && "text-danger",
          !tone && "text-ink",
        )}
      >
        {value}
      </dd>
    </div>
  );
}


function Score({ label, value }: { label: string; value: number | null }) {
  if (value === null) return <span className="text-slate-400">{label} —</span>;
  const tone = value >= 80 ? "text-success" : value >= 50 ? "text-grape-700" : "text-warning";
  return (
    <span className="text-slate-500">
      {label} <span className={cn("font-semibold", tone)}>{value}</span>
    </span>
  );
}


function RiskPill({ risk }: { risk: "low" | "medium" | "high" }) {
  return (
    <span
      className={cn(
        "pill",
        risk === "high" && "pill-danger",
        risk === "medium" && "pill-warning",
        risk === "low" && "pill-grape",
      )}
    >
      {risk}
    </span>
  );
}
