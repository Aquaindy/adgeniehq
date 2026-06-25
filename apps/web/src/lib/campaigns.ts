import { apiFetch } from "@/lib/api-client";
import type {
  CampaignActionResponse,
  CampaignDetail,
  CampaignLaunchRequest,
  CampaignLaunchResponse,
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

export function launchCampaign(workspaceId: string, body: CampaignLaunchRequest) {
  return apiFetch<CampaignLaunchResponse>(`/workspaces/${workspaceId}/campaigns/launch`, {
    method: "POST",
    body,
  });
}

export function pauseCampaign(workspaceId: string, campaignId: string) {
  return apiFetch<CampaignActionResponse>(
    `/workspaces/${workspaceId}/campaigns/${campaignId}/pause`,
    { method: "POST" },
  );
}

export function resumeCampaign(workspaceId: string, campaignId: string) {
  return apiFetch<CampaignActionResponse>(
    `/workspaces/${workspaceId}/campaigns/${campaignId}/resume`,
    { method: "POST" },
  );
}

export function updateCampaignBudget(
  workspaceId: string,
  campaignId: string,
  dailyBudgetCents: number,
) {
  return apiFetch<CampaignActionResponse>(
    `/workspaces/${workspaceId}/campaigns/${campaignId}/budget`,
    { method: "POST", body: { daily_budget_cents: dailyBudgetCents } },
  );
}
