import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { UsageMeter } from "@/components/UsageMeter";
import { EmailReportView } from "@/features/email/EmailReportView";
import { ApiError } from "@/lib/api-client";
import { getAgentRun, listAgentRuns, runAgent } from "@/lib/agents";
import { listCampaigns } from "@/lib/campaigns";
import {
  associateEmailCampaign,
  listEmailCampaigns,
  syncEmailCampaigns,
} from "@/lib/email-campaigns";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { EmailCampaignPublic, EmailMarketingReport } from "@/types/api";

const AGENT_TYPE = "email_marketing";

function pct(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

export function EmailCampaignsPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();

  const [error, setError] = useState<string | null>(null);
  const [notConnected, setNotConnected] = useState(false);
  const [freshReport, setFreshReport] = useState<EmailMarketingReport | null>(null);

  const campaigns = useQuery({
    queryKey: ["email-campaigns", workspaceId],
    queryFn: () => listEmailCampaigns(workspaceId!),
    enabled: !!workspaceId,
  });

  const adCampaigns = useQuery({
    queryKey: ["campaigns", workspaceId, "all", "all"],
    queryFn: () => listCampaigns(workspaceId!),
    enabled: !!workspaceId,
  });

  const runs = useQuery({
    queryKey: ["agents", "runs", workspaceId],
    queryFn: () => listAgentRuns(workspaceId!),
    enabled: !!workspaceId,
  });

  const latestRunId = useMemo(() => {
    const list = (runs.data ?? []).filter((r) => r.agent_type === AGENT_TYPE);
    list.sort(
      (a, b) =>
        new Date(b.started_at ?? 0).getTime() - new Date(a.started_at ?? 0).getTime(),
    );
    return list[0]?.id ?? null;
  }, [runs.data]);

  const lastReport = useQuery({
    queryKey: ["agents", "run", workspaceId, latestRunId],
    queryFn: () => getAgentRun(workspaceId!, latestRunId!),
    enabled: !!workspaceId && !!latestRunId,
  });

  const report: EmailMarketingReport | undefined =
    freshReport ??
    (lastReport.data?.output_payload as EmailMarketingReport | undefined);

  const sync = useMutation({
    mutationFn: () => syncEmailCampaigns(workspaceId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["email-campaigns", workspaceId] });
      setError(null);
      setNotConnected(false);
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "autoresponder_not_connected") {
        setNotConnected(true);
        setError(err.message);
      } else {
        setError(err instanceof ApiError ? err.message : "Sync failed.");
      }
    },
  });

  const audit = useMutation({
    mutationFn: () => runAgent(workspaceId!, { agent_type: AGENT_TYPE }),
    onSuccess: (detail) => {
      setFreshReport((detail.output_payload ?? null) as EmailMarketingReport | null);
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["agents", "runs", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["recommendations", workspaceId] });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Could not run the audit.");
    },
  });

  const adNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const c of adCampaigns.data ?? []) map.set(c.id, c.name);
    return map;
  }, [adCampaigns.data]);

  const hasCampaigns = (campaigns.data?.length ?? 0) > 0;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-grape-700">Email</p>
          <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">Email campaigns</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-500">
            Synced from Omnisend with engagement + deliverability metrics. Link a campaign to a
            paid-ads campaign, then run the Email Marketing audit for a scored report — segments,
            send-time, subject-line patterns, deliverability and a Black Friday draft.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => sync.mutate()} disabled={sync.isPending}>
            {sync.isPending ? "Syncing…" : "Sync now"}
          </Button>
          <Button onClick={() => audit.mutate()} disabled={audit.isPending || !hasCampaigns}>
            {audit.isPending ? "Auditing…" : "Run audit"}
          </Button>
        </div>
      </header>

      <UsageMeter resource="agent_runs" />

      {error ? (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}{" "}
          {notConnected ? (
            <Link className="underline" to="/autoresponders">
              Connect Omnisend →
            </Link>
          ) : null}
        </div>
      ) : null}

      {/* Audit report — the primary view */}
      {report ? (
        <section className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-ink">Audit report</h2>
            {lastReport.data?.completed_at && !freshReport ? (
              <span className="text-xs text-slate-400">
                Generated {new Date(lastReport.data.completed_at).toLocaleString()}
              </span>
            ) : null}
          </div>
          <EmailReportView report={report} />
        </section>
      ) : hasCampaigns ? (
        <Card>
          <CardHeader
            title="Run your first audit"
            subtitle="You have synced campaigns — generate the scored 7-section report."
          />
          <div className="mt-4">
            <Button onClick={() => audit.mutate()} disabled={audit.isPending}>
              {audit.isPending ? "Auditing…" : "Run audit"}
            </Button>
          </div>
        </Card>
      ) : null}

      {/* Campaign list + ad-campaign association */}
      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold text-ink">Campaigns</h2>
        {campaigns.isLoading ? (
          <p className="text-sm text-slate-400">Loading…</p>
        ) : hasCampaigns ? (
          <EmailCampaignTable
            campaigns={campaigns.data!}
            adOptions={adCampaigns.data ?? []}
            adNameById={adNameById}
            onAssociate={(emailId, adId) =>
              associateEmailCampaign(workspaceId!, emailId, adId)
            }
            onChanged={() =>
              queryClient.invalidateQueries({ queryKey: ["email-campaigns", workspaceId] })
            }
          />
        ) : (
          <EmptyState
            title="No email campaigns yet"
            description="Connect Omnisend under Autoresponders, then click Sync now to pull your campaigns with engagement and deliverability metrics."
            action={
              <div className="flex flex-wrap justify-center gap-2">
                <Link to="/autoresponders">
                  <Button variant="primary">Connect Omnisend</Button>
                </Link>
                <Button
                  variant="secondary"
                  onClick={() => sync.mutate()}
                  disabled={sync.isPending}
                >
                  {sync.isPending ? "Syncing…" : "Sync now"}
                </Button>
              </div>
            }
          />
        )}
      </section>
    </div>
  );
}

function EmailCampaignTable({
  campaigns,
  adOptions,
  adNameById,
  onAssociate,
  onChanged,
}: {
  campaigns: EmailCampaignPublic[];
  adOptions: { id: string; name: string }[];
  adNameById: Map<string, string>;
  onAssociate: (emailId: string, adId: string | null) => Promise<unknown>;
  onChanged: () => void;
}) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-100 bg-surface shadow-card">
      <table className="w-full min-w-[760px] text-sm">
        <thead>
          <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wider text-slate-400">
            <th className="px-4 py-3 font-medium">Campaign</th>
            <th className="px-4 py-3 text-right font-medium">Sent</th>
            <th className="px-4 py-3 text-right font-medium">Open</th>
            <th className="px-4 py-3 text-right font-medium">Click</th>
            <th className="px-4 py-3 text-right font-medium">Bounce</th>
            <th className="px-4 py-3 font-medium">Linked ad campaign</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {campaigns.map((c) => (
            <EmailCampaignRow
              key={c.id}
              campaign={c}
              adOptions={adOptions}
              adNameById={adNameById}
              onAssociate={onAssociate}
              onChanged={onChanged}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EmailCampaignRow({
  campaign,
  adOptions,
  adNameById,
  onAssociate,
  onChanged,
}: {
  campaign: EmailCampaignPublic;
  adOptions: { id: string; name: string }[];
  adNameById: Map<string, string>;
  onAssociate: (emailId: string, adId: string | null) => Promise<unknown>;
  onChanged: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const linkedName = campaign.ad_campaign_id
    ? adNameById.get(campaign.ad_campaign_id)
    : null;

  async function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const value = e.target.value || null;
    setSaving(true);
    try {
      await onAssociate(campaign.id, value);
      onChanged();
    } finally {
      setSaving(false);
    }
  }

  return (
    <tr className="hover:bg-grape-50/40">
      <td className="px-4 py-3">
        <div className="font-medium text-ink">{campaign.name ?? "(untitled)"}</div>
        <div className="mt-0.5 max-w-sm truncate text-xs text-slate-500">
          {campaign.subject ?? "No subject"}
        </div>
        <div className="mt-0.5 text-[11px] text-slate-400">
          {campaign.sent_at ? new Date(campaign.sent_at).toLocaleDateString() : "Not sent"}
          {campaign.status ? ` · ${campaign.status}` : ""}
        </div>
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
        {campaign.sent_count.toLocaleString()}
      </td>
      <td className="px-4 py-3 text-right tabular-nums font-medium text-ink">
        {pct(campaign.open_rate)}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
        {pct(campaign.click_rate)}
      </td>
      <td
        className={cn(
          "px-4 py-3 text-right tabular-nums",
          (campaign.bounce_rate ?? 0) > 0.02 ? "text-danger" : "text-slate-500",
        )}
      >
        {pct(campaign.bounce_rate)}
      </td>
      <td className="px-4 py-3">
        <select
          value={campaign.ad_campaign_id ?? ""}
          onChange={handleChange}
          disabled={saving}
          aria-label={`Link ${campaign.name ?? "campaign"} to an ad campaign`}
          className="w-full max-w-[200px] rounded-xl border border-slate-200 bg-surface px-3 py-1.5 text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
        >
          <option value="">Not linked</option>
          {/* Keep the current link selectable even if it's not in the list */}
          {campaign.ad_campaign_id && !adOptions.some((a) => a.id === campaign.ad_campaign_id) ? (
            <option value={campaign.ad_campaign_id}>{linkedName ?? "Linked campaign"}</option>
          ) : null}
          {adOptions.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      </td>
    </tr>
  );
}
