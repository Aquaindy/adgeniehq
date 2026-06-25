import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { UsageMeter } from "@/components/UsageMeter";
import { ApiError } from "@/lib/api-client";
import {
  campaignsSummary,
  listCampaigns,
  syncCampaigns,
} from "@/lib/campaigns";
import { WorkspaceAnalyticsCard } from "@/features/analytics/AnalyticsPanels";
import { NewCampaignPanel } from "@/features/campaigns/NewCampaignPanel";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { CampaignPublic, CampaignStatus, CampaignSummary } from "@/types/api";

const PROVIDER_DISPLAY: Record<string, string> = {
  google_ads: "Google Ads",
  meta_ads: "Meta Ads",
  linkedin_ads: "LinkedIn Ads",
};

const STATUS_OPTIONS: { value: CampaignStatus | "all"; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "active", label: "Active" },
  { value: "paused", label: "Paused" },
  { value: "ended", label: "Ended" },
  { value: "archived", label: "Archived" },
];

export function CampaignsPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();

  const [providerFilter, setProviderFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<CampaignStatus | "all">("all");
  const [error, setError] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);

  const summary = useQuery({
    queryKey: ["campaigns", workspaceId, "summary"],
    queryFn: () => campaignsSummary(workspaceId!),
    enabled: !!workspaceId,
  });

  const campaigns = useQuery({
    queryKey: ["campaigns", workspaceId, providerFilter, statusFilter],
    queryFn: () =>
      listCampaigns(workspaceId!, {
        provider: providerFilter === "all" ? undefined : providerFilter,
        status: statusFilter === "all" ? undefined : (statusFilter as CampaignStatus),
      }),
    enabled: !!workspaceId,
  });

  const sync = useMutation({
    mutationFn: () => syncCampaigns(workspaceId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["campaigns", workspaceId] });
      setError(null);
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "no_connected_ad_accounts") {
        setError(err.message);
      } else {
        setError(err instanceof ApiError ? err.message : "Sync failed.");
      }
    },
  });

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-grape-700">Campaigns</p>
          <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">
            Cross-platform campaigns
          </h1>
          <p className="mt-2 text-sm text-slate-500">
            Synced from Google Ads, Meta Ads, and LinkedIn Ads. Run the Paid Ads Agent for
            optimization recommendations.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => sync.mutate()} disabled={sync.isPending}>
            {sync.isPending ? "Syncing…" : "Sync now"}
          </Button>
          <Button onClick={() => setShowNew((v) => !v)}>
            {showNew ? "Close" : "New campaign"}
          </Button>
        </div>
      </header>

      {showNew && workspaceId ? (
        <NewCampaignPanel
          workspaceId={workspaceId}
          onClose={() => setShowNew(false)}
          onLaunched={() =>
            queryClient.invalidateQueries({ queryKey: ["campaigns", workspaceId] })
          }
        />
      ) : null}

      <UsageMeter resource="outbound_writes" />

      {error ? (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}{" "}
          {error.includes("Connect") ? (
            <Link className="underline" to="/integrations">
              Open Integrations →
            </Link>
          ) : null}
        </div>
      ) : null}

      <WorkspaceAnalyticsCard />

      {summary.data ? <SummaryStrip summary={summary.data} /> : null}

      <div className="flex flex-wrap items-center gap-3">
        <FilterSelect
          label="Platform"
          value={providerFilter}
          onChange={setProviderFilter}
          options={[
            { value: "all", label: "All platforms" },
            { value: "google_ads", label: "Google Ads" },
            { value: "meta_ads", label: "Meta Ads" },
            { value: "linkedin_ads", label: "LinkedIn Ads" },
          ]}
        />
        <FilterSelect
          label="Status"
          value={statusFilter}
          onChange={(v) => setStatusFilter(v as CampaignStatus | "all")}
          options={STATUS_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
        />
      </div>

      {campaigns.isLoading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : campaigns.data && campaigns.data.length > 0 ? (
        <CampaignList campaigns={campaigns.data} />
      ) : (
        <EmptyState
          title="No campaigns yet"
          description={
            summary.data?.total === 0
              ? "Connect an ad platform from the Integrations Center, then click Sync now."
              : "No campaigns match these filters."
          }
          action={
            summary.data?.total === 0 ? (
              <Link to="/integrations">
                <Button variant="primary">Open Integrations</Button>
              </Link>
            ) : undefined
          }
        />
      )}
    </div>
  );
}

function SummaryStrip({ summary }: { summary: CampaignSummary }) {
  const cards: { label: string; value: string | number; tone?: "warning" | "danger" }[] = [
    { label: "Total", value: summary.total },
    { label: "Active", value: summary.active },
    { label: "Paused", value: summary.paused },
    {
      label: "No budget set",
      value: summary.active_without_budget,
      tone: summary.active_without_budget > 0 ? "warning" : undefined,
    },
    {
      label: "Stale active",
      value: summary.stale_active,
      tone: summary.stale_active > 0 ? "danger" : undefined,
    },
  ];

  return (
    <section className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {cards.map((c) => (
        <Card key={c.label} className="p-4">
          <div className="text-xs uppercase tracking-wider text-slate-400">{c.label}</div>
          <div
            className={cn(
              "mt-1 text-2xl font-semibold",
              c.tone === "warning" && "text-warning",
              c.tone === "danger" && "text-danger",
              !c.tone && "text-ink",
            )}
          >
            {c.value}
          </div>
        </Card>
      ))}
    </section>
  );
}

function CampaignList({ campaigns }: { campaigns: CampaignPublic[] }) {
  return (
    <ul className="flex flex-col divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-100 bg-surface shadow-card">
      {campaigns.map((c) => (
        <li key={c.id}>
          <Link
            to={`/campaigns/${c.id}`}
            className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 transition hover:bg-grape-50"
          >
            <div className="flex-1 min-w-0">
              <div className="truncate text-sm font-semibold text-ink">{c.name}</div>
              <div className="mt-0.5 text-xs text-slate-500">
                {PROVIDER_DISPLAY[c.provider] ?? c.provider}
                {c.external_account_id ? ` · ${c.external_account_id}` : ""}
                {c.objective ? ` · ${c.objective}` : ""}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Budget label="Daily" cents={c.daily_budget_cents} currency={c.currency} />
              <StatusPill status={c.status} />
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function Budget({
  label,
  cents,
  currency,
}: {
  label: string;
  cents: number | null;
  currency: string | null;
}) {
  if (cents === null || cents === 0) {
    return <span className="pill bg-slate-100 text-slate-600">No budget</span>;
  }
  const formatted = new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: currency ?? "USD",
    maximumFractionDigits: 2,
  }).format(cents / 100);
  return (
    <span className="pill pill-grape" title={`${label} budget`}>
      {formatted}
    </span>
  );
}

export function StatusPill({ status }: { status: CampaignStatus }) {
  return (
    <span
      className={cn(
        "pill",
        status === "active" && "pill-success",
        status === "paused" && "bg-slate-100 text-slate-600",
        status === "ended" && "pill-danger",
        status === "archived" && "bg-slate-100 text-slate-500",
        status === "unknown" && "pill-warning",
      )}
    >
      {status}
    </span>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-slate-500">{label}:</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-xl border border-slate-200 bg-surface px-3 py-1.5 text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
