import { apiFetch } from "@/lib/api-client";
import type {
  CampaignMapping,
  GenerateJourneyRequest,
  JourneyType,
  OmnisendJourney,
  SyncLeadSourceResult,
} from "@/types/api";

const base = (workspaceId: string) => `/workspaces/${workspaceId}/omnisend`;

export function listJourneyTypes(workspaceId: string) {
  return apiFetch<JourneyType[]>(`${base(workspaceId)}/journey-types`);
}

export function generateJourney(workspaceId: string, body: GenerateJourneyRequest) {
  return apiFetch<OmnisendJourney>(`${base(workspaceId)}/journeys/generate`, {
    method: "POST",
    body,
  });
}

export function mapCampaign(
  workspaceId: string,
  body: { traffic_campaign_id: string; vendor_name?: string | null; journey_type?: string | null },
) {
  return apiFetch<CampaignMapping>(`${base(workspaceId)}/campaign-mapping`, {
    method: "POST",
    body,
  });
}

export function syncLeadSource(
  workspaceId: string,
  body: { tag: string; source?: string; contacts: { email: string }[] },
) {
  return apiFetch<SyncLeadSourceResult>(`${base(workspaceId)}/sync-lead-source`, {
    method: "POST",
    body,
  });
}
