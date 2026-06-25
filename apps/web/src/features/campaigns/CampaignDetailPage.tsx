import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import {
  getCampaign,
  pauseCampaign,
  resumeCampaign,
  updateCampaignBudget,
} from "@/lib/campaigns";
import { CampaignMetricsPanel } from "@/features/analytics/AnalyticsPanels";
import { AdStructureBuilder } from "@/features/campaigns/AdStructureBuilder";
import { getCampaignFeeQuote } from "@/lib/fees";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { CampaignActionResponse, CampaignDetail } from "@/types/api";

import { StatusPill } from "@/features/campaigns/CampaignsPage";

const PROVIDER_DISPLAY: Record<string, string> = {
  google_ads: "Google Ads",
  meta_ads: "Meta Ads",
  linkedin_ads: "LinkedIn Ads",
};

export function CampaignDetailPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const { campaignId } = useParams<{ campaignId: string }>();

  const detail = useQuery({
    queryKey: ["campaign", workspaceId, campaignId],
    queryFn: () => getCampaign(workspaceId!, campaignId!),
    enabled: !!workspaceId && !!campaignId,
  });

  if (detail.isLoading) return <div className="text-sm text-slate-400">Loading…</div>;

  if (detail.error) {
    const code = detail.error instanceof ApiError ? detail.error.code : null;
    return (
      <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
        {code === "campaign_not_found"
          ? "Campaign not found in this workspace."
          : detail.error instanceof Error
            ? detail.error.message
            : "Could not load campaign."}
      </div>
    );
  }

  if (!detail.data) return null;
  const c = detail.data;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <header className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-grape-700">Campaign</p>
          <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">{c.name}</h1>
          <p className="mt-1 text-xs text-slate-400">
            {PROVIDER_DISPLAY[c.provider] ?? c.provider}
            {c.external_account_id ? ` · ${c.external_account_id}` : ""}
            {c.objective ? ` · ${c.objective}` : ""} · last synced{" "}
            {new Date(c.last_synced_at).toLocaleString()}
          </p>
        </div>
        <StatusPill status={c.status} />
      </header>

      <CampaignActions campaign={c} />

      <CampaignMetricsPanel campaignId={c.id} />

      <FeeQuoteCard campaignId={c.id} />

      <AdStructureBuilder campaignId={c.id} />

      <Card>
        <CardHeader title="Budget" subtitle="As reported by the platform on last sync." />
        <dl className="mt-3 grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-slate-400">Daily</dt>
            <dd className="mt-0.5 font-medium text-ink">
              {formatCents(c.daily_budget_cents, c.currency)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-400">Lifetime</dt>
            <dd className="mt-0.5 font-medium text-ink">
              {formatCents(c.lifetime_budget_cents, c.currency)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-400">Currency</dt>
            <dd className="mt-0.5 font-medium text-ink">{c.currency ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-400">Schedule</dt>
            <dd className="mt-0.5 font-medium text-ink">
              {c.start_date ?? "—"} → {c.end_date ?? "—"}
            </dd>
          </div>
        </dl>
      </Card>

      <Card>
        <CardHeader title="Identifiers" />
        <dl className="mt-3 grid grid-cols-1 gap-3 text-xs sm:grid-cols-2">
          <div>
            <dt className="text-slate-400">Provider campaign ID</dt>
            <dd className="mt-0.5 font-mono text-slate-700">{c.external_id}</dd>
          </div>
          <div>
            <dt className="text-slate-400">Provider account ID</dt>
            <dd className="mt-0.5 font-mono text-slate-700">{c.external_account_id ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-400">AdVanta ID</dt>
            <dd className="mt-0.5 break-all font-mono text-slate-700">{c.id}</dd>
          </div>
        </dl>
      </Card>

      {c.raw_payload ? (
        <Card>
          <CardHeader
            title="Raw provider payload"
            subtitle="The unnormalized response stored on last sync."
          />
          <pre className="mt-3 max-h-96 overflow-auto rounded-xl bg-slate-50 p-3 font-mono text-xs text-slate-700">
{JSON.stringify(c.raw_payload, null, 2)}
          </pre>
        </Card>
      ) : null}

      <div className="flex justify-between">
        <Link to="/campaigns" className="text-sm font-medium text-grape-700 hover:text-grape-800">
          ← All campaigns
        </Link>
      </div>
    </div>
  );
}

function formatCents(cents: number | null, currency: string | null): string {
  if (cents === null) return "—";
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: currency ?? "USD",
    maximumFractionDigits: 2,
  }).format(cents / 100);
}

function CampaignActions({ campaign }: { campaign: CampaignDetail }) {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId)!;
  const queryClient = useQueryClient();
  const [result, setResult] = useState<CampaignActionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editingBudget, setEditingBudget] = useState(false);
  const [budgetDollars, setBudgetDollars] = useState(
    campaign.daily_budget_cents != null ? String(campaign.daily_budget_cents / 100) : "",
  );

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["campaign", workspaceId, campaign.id] });
    queryClient.invalidateQueries({ queryKey: ["campaigns", workspaceId] });
  };
  const onSuccess = (data: CampaignActionResponse) => {
    setError(null);
    setResult(data);
    setEditingBudget(false);
    refresh();
  };
  const onError = (err: unknown) => {
    setResult(null);
    setError(err instanceof ApiError ? err.message : "Action failed.");
  };

  const pauseMut = useMutation({
    mutationFn: () => pauseCampaign(workspaceId, campaign.id),
    onSuccess,
    onError,
  });
  const resumeMut = useMutation({
    mutationFn: () => resumeCampaign(workspaceId, campaign.id),
    onSuccess,
    onError,
  });
  const budgetMut = useMutation({
    mutationFn: () =>
      updateCampaignBudget(
        workspaceId,
        campaign.id,
        Math.round(parseFloat(budgetDollars) * 100),
      ),
    onSuccess,
    onError,
  });

  const busy = pauseMut.isPending || resumeMut.isPending || budgetMut.isPending;
  const manageable = !!campaign.external_account_id;
  const canPause = campaign.status === "active" || campaign.status === "unknown";
  const canResume = campaign.status === "paused" || campaign.status === "unknown";
  const dollars = parseFloat(budgetDollars);
  const budgetValid = budgetDollars !== "" && !Number.isNaN(dollars) && dollars > 0;

  if (!manageable) {
    return (
      <Card>
        <CardHeader title="Manage campaign" />
        <p className="mt-2 text-sm text-slate-500">
          This campaign is missing its ad-account reference. Re-sync the account from the
          Campaigns page to manage it here.
        </p>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title="Manage campaign"
        subtitle="Changes route through approval — you'll be told if a higher role must sign off."
      />
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {canPause ? (
          <Button variant="secondary" onClick={() => pauseMut.mutate()} disabled={busy}>
            {pauseMut.isPending ? "Pausing…" : "Pause"}
          </Button>
        ) : null}
        {canResume ? (
          <Button variant="secondary" onClick={() => resumeMut.mutate()} disabled={busy}>
            {resumeMut.isPending ? "Resuming…" : "Resume"}
          </Button>
        ) : null}
        <Button
          variant="ghost"
          onClick={() => {
            setEditingBudget((v) => !v);
            setResult(null);
            setError(null);
          }}
          disabled={busy}
        >
          Edit budget
        </Button>
      </div>

      {editingBudget ? (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-slate-500">
              New daily budget ({campaign.currency ?? "USD"})
            </span>
            <div className="flex items-center gap-1">
              <span className="text-slate-400">$</span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={budgetDollars}
                onChange={(e) => setBudgetDollars(e.target.value)}
                className="w-32 rounded-xl border border-slate-200 bg-surface px-3 py-1.5 text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
              />
            </div>
          </label>
          <Button onClick={() => budgetMut.mutate()} disabled={busy || !budgetValid}>
            {budgetMut.isPending ? "Saving…" : "Save budget"}
          </Button>
        </div>
      ) : null}

      {error ? (
        <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </div>
      ) : null}
      {result ? <ActionResultBanner result={result} /> : null}
    </Card>
  );
}

function FeeQuoteCard({ campaignId }: { campaignId: string }) {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId)!;
  const quote = useQuery({
    queryKey: ["campaign-fee-quote", workspaceId, campaignId],
    queryFn: () => getCampaignFeeQuote(workspaceId, campaignId),
    enabled: !!workspaceId,
    retry: false,
  });

  if (quote.isLoading || quote.error || !quote.data) return null;
  const q = quote.data;
  const money = (cents: number) =>
    new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(
      cents / 100,
    );

  return (
    <Card className="border-grape-100 bg-grape-soft/30">
      <CardHeader
        title="Platform fees for running this"
        subtitle="What AdVanta charges to run this campaign. Billed monthly — ad spend is paid directly to the platform."
      />
      <dl className="mt-3 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-slate-400">Listing fee</dt>
          <dd className="mt-0.5 font-semibold text-ink">{money(q.listing_fee_cents)}</dd>
          <dd className="text-[11px] text-slate-400">one-time at launch</dd>
        </div>
        <div>
          <dt className="text-slate-400">Run fee</dt>
          <dd className="mt-0.5 font-semibold text-ink">
            {money(q.run_flat_fee_cents)}
            {q.run_pct_basis_points > 0
              ? ` + ${(q.run_pct_basis_points / 100).toFixed(1)}%`
              : ""}
          </dd>
          <dd className="text-[11px] text-slate-400">flat + % of spend / mo</dd>
        </div>
        <div>
          <dt className="text-slate-400">Est. monthly run fee</dt>
          <dd className="mt-0.5 font-semibold text-ink">
            {money(q.est_monthly_run_fee_cents)}
          </dd>
          <dd className="text-[11px] text-slate-400">
            at {money(q.est_monthly_spend_cents)} spend
          </dd>
        </div>
        <div>
          <dt className="text-slate-400">Est. first month</dt>
          <dd className="mt-0.5 font-semibold text-grape-700">
            {money(q.est_first_month_total_cents)}
          </dd>
          <dd className="text-[11px] text-slate-400">listing + run</dd>
        </div>
      </dl>
      <p className="mt-3 text-[11px] text-slate-400">
        {q.source === "default"
          ? "Using default platform rates."
          : "Using your configured fee schedule."}{" "}
        Estimates assume current daily budget over ~30 days.
      </p>
    </Card>
  );
}

function ActionResultBanner({ result }: { result: CampaignActionResponse }) {
  const tone =
    result.status === "executed"
      ? "bg-success/10 text-success"
      : result.status === "queued"
        ? "bg-grape-soft/60 text-grape-800"
        : "bg-red-50 text-red-700";
  return (
    <div className={cn("mt-3 rounded-lg px-3 py-2 text-sm", tone)} role="status">
      {result.message}
      {result.status === "queued" ? (
        <>
          {" "}
          <Link to="/recommendations" className="font-medium underline">
            View in Recommendations →
          </Link>
        </>
      ) : null}
    </div>
  );
}
