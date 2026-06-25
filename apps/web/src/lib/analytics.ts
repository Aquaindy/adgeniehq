import { apiFetch } from "@/lib/api-client";
import type {
  CampaignMetricsSeries,
  MetricsSyncResult,
  WorkspaceAnalytics,
} from "@/types/api";

export function getAnalyticsSummary(workspaceId: string, days = 30) {
  return apiFetch<WorkspaceAnalytics>(`/workspaces/${workspaceId}/analytics/summary`, {
    query: { days },
  });
}

export function getCampaignMetrics(workspaceId: string, campaignId: string, days = 30) {
  return apiFetch<CampaignMetricsSeries>(
    `/workspaces/${workspaceId}/campaigns/${campaignId}/metrics`,
    { query: { days } },
  );
}

export function syncAnalytics(workspaceId: string, days = 30) {
  return apiFetch<MetricsSyncResult>(`/workspaces/${workspaceId}/analytics/sync`, {
    method: "POST",
    query: { days },
  });
}
