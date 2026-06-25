import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import { getAnalyticsSummary, getCampaignMetrics, syncAnalytics } from "@/lib/analytics";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { Kpi } from "@/types/api";

const money = (cents: number) =>
  new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(
    cents / 100,
  );
const money2 = (cents: number) =>
  new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(cents / 100);
const num = (n: number) => new Intl.NumberFormat().format(n);
const pct = (x: number) => `${(x * 100).toFixed(2)}%`;

function KpiTiles({ k }: { k: Kpi }) {
  const tiles: { label: string; value: string }[] = [
    { label: "Spend", value: money(k.spend_cents) },
    { label: "Impressions", value: num(k.impressions) },
    { label: "Clicks", value: num(k.clicks) },
    { label: "Conversions", value: num(k.conversions) },
    { label: "CTR", value: pct(k.ctr) },
    { label: "CPA", value: k.conversions ? money2(k.cpa_cents) : "—" },
    { label: "ROAS", value: k.spend_cents ? `${k.roas.toFixed(2)}×` : "—" },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
      {tiles.map((t) => (
        <div key={t.label} className="rounded-xl border border-slate-100 bg-surface px-3 py-2 shadow-sm">
          <div className="text-[10px] uppercase tracking-wider text-slate-400">{t.label}</div>
          <div className="mt-0.5 text-lg font-semibold text-ink">{t.value}</div>
        </div>
      ))}
    </div>
  );
}

function Bars({ data }: { data: { label: string; value: number }[] }) {
  if (data.length === 0) return null;
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <div className="mt-3 flex h-24 items-end gap-1">
      {data.map((d, i) => (
        <div key={`${d.label}-${i}`} className="group relative flex-1" title={`${d.label}: ${money2(d.value)}`}>
          <div
            className="w-full rounded-t bg-grape/70 transition-all group-hover:bg-grape"
            style={{ height: `${Math.max(2, (d.value / max) * 100)}%` }}
          />
        </div>
      ))}
    </div>
  );
}

export function CampaignMetricsPanel({ campaignId }: { campaignId: string }) {
  const ws = useWorkspaceStore((s) => s.currentWorkspaceId)!;
  const q = useQuery({
    queryKey: ["campaign-metrics", ws, campaignId],
    queryFn: () => getCampaignMetrics(ws, campaignId, 30),
    enabled: !!ws,
    retry: false,
  });

  if (q.isLoading || q.error || !q.data) return null;
  const { totals, points } = q.data;
  const hasData = points.length > 0;

  return (
    <Card>
      <CardHeader title="Performance" subtitle="Last 30 days, from synced platform insights." />
      {hasData ? (
        <>
          <div className="mt-3">
            <KpiTiles k={totals} />
          </div>
          <Bars data={points.map((p) => ({ label: p.date, value: p.spend_cents }))} />
          <p className="mt-1 text-[11px] text-slate-400">Daily spend</p>
        </>
      ) : (
        <p className="mt-3 text-sm text-slate-500">
          No performance data yet. Click <span className="font-medium">Sync analytics</span> on the
          Campaigns page once this platform is connected.
        </p>
      )}
    </Card>
  );
}

export function WorkspaceAnalyticsCard() {
  const ws = useWorkspaceStore((s) => s.currentWorkspaceId)!;
  const qc = useQueryClient();
  const [msg, setMsg] = useState<string | null>(null);

  const q = useQuery({
    queryKey: ["analytics-summary", ws],
    queryFn: () => getAnalyticsSummary(ws, 30),
    enabled: !!ws,
  });

  const sync = useMutation({
    mutationFn: () => syncAnalytics(ws, 30),
    onSuccess: (r) => {
      setMsg(
        r.upserted > 0
          ? `Synced ${r.upserted} day-rows of performance data.`
          : "No new performance data returned (platform may not be wired or has no data yet).",
      );
      qc.invalidateQueries({ queryKey: ["analytics-summary", ws] });
    },
    onError: (e) => setMsg(e instanceof ApiError ? e.message : "Sync failed."),
  });

  const data = q.data;

  return (
    <Card>
      <CardHeader
        title="Ad performance"
        subtitle="Aggregated across connected platforms, last 30 days."
        action={
          <Button variant="secondary" onClick={() => sync.mutate()} disabled={sync.isPending}>
            {sync.isPending ? "Syncing…" : "Sync analytics"}
          </Button>
        }
      />
      {msg ? <div className="mt-2 text-xs text-slate-500">{msg}</div> : null}

      {data && data.has_data ? (
        <div className="mt-3 flex flex-col gap-4">
          <KpiTiles k={data.totals} />
          <div>
            <Bars data={data.daily.map((d) => ({ label: d.date, value: d.spend_cents }))} />
            <p className="mt-1 text-[11px] text-slate-400">Daily spend</p>
          </div>
          {data.top_campaigns.length > 0 ? (
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Top campaigns by spend
              </div>
              <ul className="mt-2 flex flex-col gap-1 text-sm">
                {data.top_campaigns.slice(0, 5).map((c) => (
                  <li key={c.campaign_id} className="flex items-center justify-between">
                    <span className="truncate text-slate-700">{c.name}</span>
                    <span className="text-slate-500">
                      {money2(c.spend_cents)} · {num(c.conversions)} conv ·{" "}
                      {c.spend_cents ? `${c.roas.toFixed(2)}× ROAS` : "—"}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-500">
          No performance data yet. Connect an ad platform and click{" "}
          <span className="font-medium">Sync analytics</span> to pull impressions, clicks, spend,
          and conversions.
        </p>
      )}
    </Card>
  );
}
