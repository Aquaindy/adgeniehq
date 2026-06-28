import { apiFetch } from "@/lib/api-client";
import type { EmailCampaignPublic } from "@/types/api";

const base = (workspaceId: string) => `/workspaces/${workspaceId}/email-campaigns`;

export function listEmailCampaigns(workspaceId: string) {
  return apiFetch<EmailCampaignPublic[]>(base(workspaceId));
}

export function syncEmailCampaigns(workspaceId: string) {
  return apiFetch<EmailCampaignPublic[]>(`${base(workspaceId)}/sync`, {
    method: "POST",
  });
}

export function associateEmailCampaign(
  workspaceId: string,
  emailCampaignId: string,
  adCampaignId: string | null,
) {
  return apiFetch<EmailCampaignPublic>(
    `${base(workspaceId)}/${emailCampaignId}/associate`,
    { method: "POST", body: { ad_campaign_id: adCampaignId } },
  );
}
