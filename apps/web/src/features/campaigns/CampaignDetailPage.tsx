import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import { getCampaign } from "@/lib/campaigns";
import { useWorkspaceStore } from "@/stores/workspace-store";

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
