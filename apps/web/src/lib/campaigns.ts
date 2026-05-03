import { apiFetch } from "@/lib/api-client";
import type {
  CampaignDetail,
  CampaignPublic,
  CampaignStatus,
  CampaignSummary,
  CampaignSyncResponse,
} from "@/types/api";

export function listCampaigns(
  workspaceId: string,
  filters?: { provider?: string; status?: CampaignStatus },
) {
  return apiFetch<CampaignPublic[]>(`/workspaces/${workspaceId}/campaigns`, {
    query: filters,
  });
}

export function getCampaign(workspaceId: string, campaignId: string) {
  return apiFetch<CampaignDetail>(`/workspaces/${workspaceId}/campaigns/${campaignId}`);
}

export function campaignsSummary(workspaceId: string) {
  return apiFetch<CampaignSummary>(`/workspaces/${workspaceId}/campaigns/summary`);
}

export function syncCampaigns(workspaceId: string, provider?: string) {
  return apiFetch<CampaignSyncResponse>(`/workspaces/${workspaceId}/campaigns/sync`, {
    method: "POST",
    query: provider ? { provider } : undefined,
  });
}
