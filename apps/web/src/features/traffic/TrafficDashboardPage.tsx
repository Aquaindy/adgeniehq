import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { UsageMeter } from "@/components/UsageMeter";
import { SOURCE_TYPE_LABEL } from "@/features/traffic/TrafficBits";
import { ApiError } from "@/lib/api-client";
import {
  getTrafficAnalyticsOverview,
  getTrafficCatalog,
  logTrafficMetric,
  optimizeTraffic,
} from "@/lib/traffic";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type {
  CampaignRollup,
  SourceRollup,
  TrafficAction,
  TrafficOptimization,
  TrafficRollup,
} from "@/types/api";

function money(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return "—";
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}
const roas = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${v.toFixed(1)}x`);

function qualityTone(v?: string | null): string {
  switch (v) {
    case "Excellent":
    case "Strong":
      return "pill-success";
    case "Promising":
      return "pill-grape";
    case "Weak":
      return "pill-warning";
    case "Risky":
    case "Poor":
      return "pill-danger";
    default:
      return "bg-slate-100 text-slate-500";
  }
}

export function TrafficDashboardPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const [showLog, setShowLog] = useState(false);
  const [optimization, setOptimization] = useState<TrafficOptimization | null>(null);
  const [error, setError] = useState<string | null>(null);

  const overview = useQuery({
    queryKey: ["traffic", "analytics", workspaceId],
    queryFn: () => getTrafficAnalyticsOverview(workspaceId!),
    enabled: !!workspaceId,
  });

  const optimize = useMutation({
    mutationFn: () => optimizeTraffic(workspaceId!),
    onSuccess: (data) => {
      setOptimization(data);
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["recommendations", workspaceId] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Optimization failed."),
  });

  const data = overview.data;
  const hasData = data?.has_data;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-grape-700">Traffic Genie</p>
          <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">Traffic dashboard</h1>
          <p className="mt-2 text-sm text-slate-500">
            Real source performance — profitability, ROAS and quality — across paid, organic and
            paid-email. Solo-ad orders roll in automatically.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => setShowLog((v) => !v)}>
            {showLog ? "Close" : "Log results"}
          </Button>
          <Button onClick={() => optimize.mutate()} disabled={optimize.isPending || !hasData}>
            {optimize.isPending ? "Analyzing…" : "Run AI optimization"}
          </Button>
        </div>
      </header>

      <UsageMeter resource="agent_runs" />

      {error ? <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{error}</div> : null}

      {showLog && workspaceId ? (
        <LogResultsForm
          workspaceId={workspaceId}
          onClose={() => setShowLog(false)}
          onLogged={() => {
            queryClient.invalidateQueries({ queryKey: ["traffic", "analytics", workspaceId] });
            setShowLog(false);
          }}
        />
      ) : null}

      {overview.isLoading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : !hasData ? (
        <EmptyState
          title="No traffic results yet"
          description="Log a source's results (clicks, cost, leads, sales, revenue) — or record a Solo Ads order — and this dashboard will compare profitability, ROAS and quality across every source."
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Button onClick={() => setShowLog(true)}>Log results</Button>
              <Link to="/traffic/solo-ads"><Button variant="secondary">Solo Ads</Button></Link>
            </div>
          }
        />
      ) : (
        <>
          <TotalsStrip totals={data!.totals} />
          <TypeSplit byType={data!.by_type} />
          <SourceTable sources={data!.sources} />
          {data!.campaigns.length > 0 ? <CampaignList campaigns={data!.campaigns} /> : null}
        </>
      )}

      {optimization ? <OptimizationView opt={optimization} /> : null}
    </div>
  );
}

function TotalsStrip({ totals }: { totals: TrafficRollup }) {
  const profit = totals.profit_cents ?? 0;
  const cards = [
    { label: "Spend", value: money(totals.cost_cents) },
    { label: "Revenue", value: money(totals.revenue_cents) },
    { label: "Profit", value: money(profit), tone: profit < 0 ? "danger" : "success" },
    { label: "ROAS", value: roas(totals.roas) },
    { label: "Leads", value: String(totals.leads) },
    { label: "Sales", value: String(totals.sales) },
  ];
  return (
    <section className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
      {cards.map((c) => (
        <Card key={c.label} className="p-4">
          <div className="text-xs uppercase tracking-wider text-slate-400">{c.label}</div>
          <div className={cn("mt-1 text-xl font-semibold", c.tone === "danger" ? "text-danger" : c.tone === "success" ? "text-success" : "text-ink")}>
            {c.value}
          </div>
        </Card>
      ))}
    </section>
  );
}

function TypeSplit({ byType }: { byType: Record<string, TrafficRollup> }) {
  const types = ["paid", "organic", "paid_email", "other"].filter((t) => byType[t]);
  if (types.length === 0) return null;
  return (
    <section className="grid gap-3 sm:grid-cols-3">
      {types.map((t) => {
        const b = byType[t];
        if (!b) return null;
        const profit = b.profit_cents ?? 0;
        return (
          <Card key={t} className="p-4">
            <div className="text-sm font-semibold text-ink">{SOURCE_TYPE_LABEL[t] ?? t}</div>
            <dl className="mt-2 grid grid-cols-2 gap-2 text-xs">
              <Mini label="Spend" value={money(b.cost_cents)} />
              <Mini label="Revenue" value={money(b.revenue_cents)} />
              <Mini label="Profit" value={money(profit)} tone={profit < 0 ? "danger" : undefined} />
              <Mini label="ROAS" value={roas(b.roas)} />
            </dl>
          </Card>
        );
      })}
    </section>
  );
}

function SourceTable({ sources }: { sources: SourceRollup[] }) {
  return (
    <Card>
      <CardHeader title="Source comparison" subtitle="Sorted by profit. Quality is scored 0-100 from your real engagement, conversion and ROI." />
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wider text-slate-400">
              <th className="pb-2 font-medium">Source</th>
              <th className="pb-2 text-right font-medium">Spend</th>
              <th className="pb-2 text-right font-medium">Revenue</th>
              <th className="pb-2 text-right font-medium">Profit</th>
              <th className="pb-2 text-right font-medium">ROAS</th>
              <th className="pb-2 text-right font-medium">CPL</th>
              <th className="pb-2 text-right font-medium">Quality</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {sources.map((s) => {
              const profit = s.profit_cents ?? 0;
              return (
                <tr key={s.source_slug}>
                  <td className="py-2">
                    <div className="font-medium text-ink">{s.source_name}</div>
                    <div className="text-[11px] text-slate-400">{SOURCE_TYPE_LABEL[s.source_type] ?? s.source_type}</div>
                  </td>
                  <td className="py-2 text-right tabular-nums text-slate-600">{money(s.cost_cents)}</td>
                  <td className="py-2 text-right tabular-nums text-slate-600">{money(s.revenue_cents)}</td>
                  <td className={cn("py-2 text-right tabular-nums font-semibold", profit < 0 ? "text-danger" : "text-success")}>{money(profit)}</td>
                  <td className="py-2 text-right tabular-nums text-ink">{roas(s.roas)}</td>
                  <td className="py-2 text-right tabular-nums text-slate-600">{money(s.cpl_cents)}</td>
                  <td className="py-2 text-right">
                    {s.quality_score != null ? (
                      <span className={cn("pill", qualityTone(s.quality_verdict))}>{s.quality_score}</span>
                    ) : <span className="text-slate-300">—</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function CampaignList({ campaigns }: { campaigns: CampaignRollup[] }) {
  return (
    <Card>
      <CardHeader title="Campaign comparison" subtitle="Your traffic campaigns by profit." />
      <ul className="mt-3 flex flex-col divide-y divide-slate-100">
        {campaigns.slice(0, 8).map((c) => {
          const profit = c.profit_cents ?? 0;
          return (
            <li key={c.campaign_id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
              <Link to={`/traffic/campaigns/${c.campaign_id}`} className="min-w-0 flex-1 truncate font-medium text-ink hover:text-grape-700">
                {c.name}
              </Link>
              <span className="text-xs text-slate-400">{roas(c.roas)} ROAS</span>
              <span className={cn("w-20 text-right tabular-nums font-semibold", profit < 0 ? "text-danger" : "text-success")}>{money(profit)}</span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function OptimizationView({ opt }: { opt: TrafficOptimization }) {
  if (opt.has_data === false) {
    return (
      <Card>
        <CardHeader title="AI optimization" subtitle="No results to analyze yet — log some traffic first." />
      </Card>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {opt.executive_summary ? (
        <Card className="border-grape-200 bg-grape-50/40">
          <CardHeader title="AI next best action" />
          <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-700">{opt.executive_summary}</p>
        </Card>
      ) : null}
      {opt.next_best_actions && opt.next_best_actions.length > 0 ? (
        <div className="flex flex-col gap-2">
          {opt.next_best_actions.map((a, i) => <ActionCard key={i} action={a} />)}
        </div>
      ) : (
        <Card><p className="text-sm text-slate-500">No actions right now — your sources look balanced.</p></Card>
      )}
    </div>
  );
}

function ActionCard({ action }: { action: TrafficAction }) {
  const tone = action.priority === "high" ? "pill-danger" : action.priority === "medium" ? "pill-warning" : "pill-grape";
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-ink">{action.title}</div>
          <p className="mt-1 text-sm text-slate-600">{action.detail}</p>
        </div>
        <span className={cn("pill shrink-0", tone)}>{action.priority}</span>
      </div>
    </Card>
  );
}

function LogResultsForm({
  workspaceId,
  onClose,
  onLogged,
}: {
  workspaceId: string;
  onClose: () => void;
  onLogged: () => void;
}) {
  const catalog = useQuery({
    queryKey: ["traffic", "catalog", workspaceId],
    queryFn: () => getTrafficCatalog(workspaceId),
  });
  const [sourceSlug, setSourceSlug] = useState("");
  const [f, setF] = useState({ clicks: "", leads: "", sales: "", cost: "", revenue: "", refunds: "" });
  const [error, setError] = useState<string | null>(null);
  const num = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF((s) => ({ ...s, [k]: e.target.value }));
  const toInt = (v: string) => (v ? Math.round(Number(v)) : 0);
  const toCents = (v: string) => (v ? Math.round(Number(v) * 100) : 0);

  const log = useMutation({
    mutationFn: () =>
      logTrafficMetric(workspaceId, {
        source_slug: sourceSlug,
        clicks: toInt(f.clicks),
        leads: toInt(f.leads),
        sales: toInt(f.sales),
        cost_cents: toCents(f.cost),
        revenue_cents: toCents(f.revenue),
        refunds: toInt(f.refunds),
        currency: "USD",
      }),
    onSuccess: onLogged,
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not log results."),
  });

  return (
    <Card>
      <CardHeader title="Log traffic results" subtitle="Enter a source's real numbers — economics + quality are computed from them." />
      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <label className="flex flex-col gap-1 text-sm lg:col-span-2">
          <span className="text-slate-500">Source *</span>
          <select
            value={sourceSlug}
            onChange={(e) => setSourceSlug(e.target.value)}
            className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
          >
            <option value="">Select a source…</option>
            {catalog.data?.sources.map((s) => <option key={s.slug} value={s.slug}>{s.name}</option>)}
          </select>
        </label>
        <NumInput label="Clicks" value={f.clicks} onChange={num("clicks")} />
        <NumInput label="Leads / opt-ins" value={f.leads} onChange={num("leads")} />
        <NumInput label="Sales" value={f.sales} onChange={num("sales")} />
        <NumInput label="Cost (USD)" value={f.cost} onChange={num("cost")} />
        <NumInput label="Revenue (USD)" value={f.revenue} onChange={num("revenue")} />
        <NumInput label="Refunds" value={f.refunds} onChange={num("refunds")} />
      </div>
      {error ? <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{error}</div> : null}
      <div className="mt-5 flex items-center gap-2">
        <Button onClick={() => log.mutate()} disabled={log.isPending || !sourceSlug}>{log.isPending ? "Saving…" : "Save results"}</Button>
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
      </div>
    </Card>
  );
}

function Mini({ label, value, tone }: { label: string; value: string; tone?: "danger" }) {
  return (
    <div>
      <dt className="text-slate-400">{label}</dt>
      <dd className={cn("font-medium", tone === "danger" ? "text-danger" : "text-ink")}>{value}</dd>
    </div>
  );
}

function NumInput({ label, value, onChange }: { label: string; value: string; onChange: (e: React.ChangeEvent<HTMLInputElement>) => void }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-slate-500">{label}</span>
      <input
        type="number"
        value={value}
        onChange={onChange}
        className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
      />
    </label>
  );
}
