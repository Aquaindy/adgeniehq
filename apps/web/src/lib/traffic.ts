import { apiFetch } from "@/lib/api-client";
import type {
  CreateTrafficCampaignRequest,
  CreateUtmLinkRequest,
  LogMetricRequest,
  TrafficAnalyticsOverview,
  TrafficCampaign,
  TrafficCampaignAsset,
  TrafficCampaignDetail,
  TrafficCatalog,
  TrafficOptimization,
  TrafficRecommendation,
  TrafficRecommendationRequest,
  UtmLink,
} from "@/types/api";

const base = (workspaceId: string) => `/workspaces/${workspaceId}/traffic`;

export function getTrafficCatalog(workspaceId: string) {
  return apiFetch<TrafficCatalog>(`${base(workspaceId)}/catalog`);
}

export function listTrafficCampaigns(
  workspaceId: string,
  filters?: { source_slug?: string; status_filter?: string },
) {
  return apiFetch<TrafficCampaign[]>(`${base(workspaceId)}/campaigns`, {
    query: filters,
  });
}

export function getTrafficCampaign(workspaceId: string, campaignId: string) {
  return apiFetch<TrafficCampaignDetail>(
    `${base(workspaceId)}/campaigns/${campaignId}`,
  );
}

export function createTrafficCampaign(
  workspaceId: string,
  body: CreateTrafficCampaignRequest,
) {
  return apiFetch<TrafficCampaignDetail>(`${base(workspaceId)}/campaigns`, {
    method: "POST",
    body,
  });
}

export function updateTrafficCampaign(
  workspaceId: string,
  campaignId: string,
  body: Partial<CreateTrafficCampaignRequest> & { status?: string },
) {
  return apiFetch<TrafficCampaignDetail>(
    `${base(workspaceId)}/campaigns/${campaignId}`,
    { method: "PATCH", body },
  );
}

export function deleteTrafficCampaign(workspaceId: string, campaignId: string) {
  return apiFetch<void>(`${base(workspaceId)}/campaigns/${campaignId}`, {
    method: "DELETE",
  });
}

export function generateTrafficAssets(
  workspaceId: string,
  campaignId: string,
  assetTypes?: string[],
) {
  return apiFetch<TrafficCampaignAsset[]>(
    `${base(workspaceId)}/campaigns/${campaignId}/generate-assets`,
    { method: "POST", body: { asset_types: assetTypes ?? null } },
  );
}

export function recommendTraffic(
  workspaceId: string,
  body: TrafficRecommendationRequest,
) {
  return apiFetch<TrafficRecommendation>(`${base(workspaceId)}/recommend`, {
    method: "POST",
    body,
  });
}

export function listUtmLinks(workspaceId: string, campaignId?: string) {
  return apiFetch<UtmLink[]>(`${base(workspaceId)}/utm-links`, {
    query: campaignId ? { campaign_id: campaignId } : undefined,
  });
}

export function createUtmLink(workspaceId: string, body: CreateUtmLinkRequest) {
  return apiFetch<UtmLink>(`${base(workspaceId)}/utm-links`, {
    method: "POST",
    body,
  });
}

export function deleteUtmLink(workspaceId: string, linkId: string) {
  return apiFetch<void>(`${base(workspaceId)}/utm-links/${linkId}`, {
    method: "DELETE",
  });
}

// --- Analytics (Phase 6) ---

export function getTrafficAnalyticsOverview(workspaceId: string) {
  return apiFetch<TrafficAnalyticsOverview>(`${base(workspaceId)}/analytics/overview`);
}

export function logTrafficMetric(workspaceId: string, body: LogMetricRequest) {
  return apiFetch(`${base(workspaceId)}/metrics`, { method: "POST", body });
}

export function optimizeTraffic(workspaceId: string) {
  return apiFetch<TrafficOptimization>(`${base(workspaceId)}/analytics/optimize`, {
    method: "POST",
  });
}
