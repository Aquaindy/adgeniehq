import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { MetaPills, formatBudget } from "@/features/traffic/TrafficBits";
import { ApiError } from "@/lib/api-client";
import { mapCampaign } from "@/lib/omnisend";
import {
  deleteTrafficCampaign,
  generateTrafficAssets,
  getTrafficCampaign,
  getTrafficCatalog,
} from "@/lib/traffic";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { CampaignMapping, TrafficCampaignAsset } from "@/types/api";

export function TrafficCampaignDetailPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const { campaignId } = useParams<{ campaignId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const campaign = useQuery({
    queryKey: ["traffic", "campaign", workspaceId, campaignId],
    queryFn: () => getTrafficCampaign(workspaceId!, campaignId!),
    enabled: !!workspaceId && !!campaignId,
  });

  const catalog = useQuery({
    queryKey: ["traffic", "catalog", workspaceId],
    queryFn: () => getTrafficCatalog(workspaceId!),
    enabled: !!workspaceId,
  });

  const source = useMemo(
    () => catalog.data?.sources.find((s) => s.slug === campaign.data?.source_slug),
    [catalog.data, campaign.data],
  );

  const generate = useMutation({
    mutationFn: () => generateTrafficAssets(workspaceId!, campaignId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["traffic", "campaign", workspaceId, campaignId] });
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Asset generation failed."),
  });

  const remove = useMutation({
    mutationFn: () => deleteTrafficCampaign(workspaceId!, campaignId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["traffic", "campaigns", workspaceId] });
      navigate("/traffic/campaigns");
    },
  });

  if (campaign.isLoading) return <p className="text-sm text-slate-400">Loading campaign…</p>;
  if (campaign.error) {
    const code = campaign.error instanceof ApiError ? campaign.error.code : null;
    return (
      <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
        {code === "traffic_campaign_not_found" ? "Campaign not found in this workspace." : "Could not load campaign."}
      </div>
    );
  }
  if (!campaign.data) return null;
  const c = campaign.data;
  const assets = c.assets ?? [];

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-grape-700">
            {source?.name ?? c.source_slug}
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">{c.name}</h1>
          <p className="mt-1 text-sm text-slate-500">
            {[c.goal, c.offer_name, c.budget_cents ? formatBudget(c.budget_cents, c.currency) : null]
              .filter(Boolean)
              .join(" · ") || "No details yet"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link to={`/traffic/utm-builder?campaign=${c.id}`}>
            <Button variant="secondary">Build UTM link</Button>
          </Link>
          <Button onClick={() => generate.mutate()} disabled={generate.isPending}>
            {generate.isPending ? "Generating…" : assets.length ? "Regenerate assets" : "Generate assets"}
          </Button>
        </div>
      </header>

      {error ? <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{error}</div> : null}

      {source ? (
        <Card>
          <CardHeader title="Source playbook" subtitle={source.content_required} />
          <div className="mt-3 flex flex-wrap items-center gap-4">
            <MetaPills source={source} />
          </div>
          <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
            <Meta label="Best for" value={source.best_for.join(", ")} />
            <Meta label="Recommended goal" value={source.recommended_goal} />
            <Meta label="Tracking" value={source.tracking} />
            <Meta label="Recommended follow-up" value={source.recommended_followup} />
          </dl>
          {c.ai_summary ? (
            <p className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">{c.ai_summary}</p>
          ) : null}
        </Card>
      ) : null}

      <OmnisendFollowupCard
        workspaceId={workspaceId!}
        campaignId={c.id}
        segment={c.omnisend_segment}
        flow={c.omnisend_flow}
      />

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold text-ink">Generated assets</h2>
        {assets.length === 0 ? (
          <EmptyState
            title="No assets yet"
            description={`Generate ready-to-edit ${source?.name ?? "campaign"} assets — ${(source?.asset_types ?? []).slice(0, 4).join(", ")}${(source?.asset_types?.length ?? 0) > 4 ? "…" : ""}. Connect an LLM key for full AI copy; otherwise you'll get structured scaffolding.`}
            action={<Button onClick={() => generate.mutate()} disabled={generate.isPending}>{generate.isPending ? "Generating…" : "Generate assets"}</Button>}
          />
        ) : (
          <div className="flex flex-col gap-3">
            {assets.map((a) => (
              <AssetCard key={a.id} asset={a} />
            ))}
          </div>
        )}
      </section>

      <div className="flex justify-between border-t border-slate-100 pt-4">
        <Link to="/traffic/campaigns" className="text-sm font-medium text-grape-700 hover:text-grape-800">
          ← All campaigns
        </Link>
        <button
          type="button"
          onClick={() => {
            if (window.confirm("Delete this campaign and its assets?")) remove.mutate();
          }}
          className="text-sm font-medium text-danger hover:underline"
          disabled={remove.isPending}
        >
          Delete campaign
        </button>
      </div>
    </div>
  );
}

function AssetCard({ asset }: { asset: TrafficCampaignAsset }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(asset.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-ink">{asset.title ?? asset.asset_type}</h3>
          <span className="text-[11px] uppercase tracking-wider text-slate-400">{asset.asset_type}</span>
        </div>
        <Button variant="ghost" onClick={copy} className="text-xs">{copied ? "Copied!" : "Copy"}</Button>
      </div>
      <pre className="mt-3 whitespace-pre-wrap break-words rounded-xl bg-slate-50 p-3 text-sm leading-relaxed text-slate-700">
        {asset.content}
      </pre>
    </Card>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-400">{label}</dt>
      <dd className="text-slate-700">{value}</dd>
    </div>
  );
}

function OmnisendFollowupCard({
  workspaceId,
  campaignId,
  segment,
  flow,
}: {
  workspaceId: string;
  campaignId: string;
  segment: string | null;
  flow: string | null;
}) {
  const queryClient = useQueryClient();
  const [mapping, setMapping] = useState<CampaignMapping | null>(null);
  const map = useMutation({
    mutationFn: () => mapCampaign(workspaceId, { traffic_campaign_id: campaignId }),
    onSuccess: (data) => {
      setMapping(data);
      queryClient.invalidateQueries({ queryKey: ["traffic", "campaign", workspaceId, campaignId] });
    },
  });

  const segmentName = mapping?.segment_name ?? segment;
  const flowName = mapping?.flow_name ?? flow;

  return (
    <Card>
      <CardHeader
        title="Omnisend follow-up"
        subtitle="Map this campaign to an Omnisend segment + automation so its leads get nurtured."
        action={
          <Button variant="secondary" className="text-xs" onClick={() => map.mutate()} disabled={map.isPending}>
            {map.isPending ? "Setting up…" : segmentName ? "Re-generate mapping" : "Set up mapping"}
          </Button>
        }
      />
      {segmentName ? (
        <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
          <Meta label="Segment / tag" value={segmentName} />
          <Meta label="Automation (flow)" value={flowName ?? "—"} />
          {mapping?.tag ? <Meta label="Trigger tag" value={mapping.tag} /> : null}
          {mapping?.lead_source_field ? <Meta label="Lead source" value={mapping.lead_source_field} /> : null}
        </dl>
      ) : (
        <p className="mt-3 text-sm text-slate-500">
          No Omnisend mapping yet. Generate one to get a consistent segment name, trigger tag, and a
          recommended journey.
        </p>
      )}
      {mapping?.how_to ? (
        <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">{mapping.how_to}</p>
      ) : null}
      {mapping ? (
        <div className="mt-3">
          <Link
            to={`/traffic/omnisend?type=${mapping.recommended_journey_type}&tag=${encodeURIComponent(mapping.tag)}`}
            className="text-sm font-medium text-grape-700 hover:text-grape-800"
          >
            Generate the {mapping.recommended_journey_type.replace(/_/g, " ")} journey →
          </Link>
        </div>
      ) : null}
    </Card>
  );
}
