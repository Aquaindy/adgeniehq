import { apiFetch } from "@/lib/api-client";
import type {
  Ad,
  AdGroup,
  AdGroupTargeting,
  AdPublishResponse,
  Creative,
} from "@/types/api";

export function listAdGroups(workspaceId: string, campaignId: string) {
  return apiFetch<AdGroup[]>(`/workspaces/${workspaceId}/ad-groups`, {
    query: { campaign_id: campaignId },
  });
}

export function listAds(workspaceId: string, campaignId: string) {
  return apiFetch<Ad[]>(`/workspaces/${workspaceId}/ads`, {
    query: { campaign_id: campaignId },
  });
}

export function listCreatives(workspaceId: string) {
  return apiFetch<Creative[]>(`/workspaces/${workspaceId}/creatives`);
}

export function createAdGroup(
  workspaceId: string,
  campaignId: string,
  body: { name: string; daily_budget_cents: number | null; targeting: AdGroupTargeting },
) {
  return apiFetch<AdGroup>(
    `/workspaces/${workspaceId}/campaigns/${campaignId}/ad-groups`,
    { method: "POST", body },
  );
}

export function deleteAdGroup(workspaceId: string, adGroupId: string) {
  return apiFetch<void>(`/workspaces/${workspaceId}/ad-groups/${adGroupId}`, {
    method: "DELETE",
  });
}

export function createAd(
  workspaceId: string,
  adGroupId: string,
  body: { name: string; landing_page_url: string | null; creative_id: string | null },
) {
  return apiFetch<Ad>(`/workspaces/${workspaceId}/ad-groups/${adGroupId}/ads`, {
    method: "POST",
    body,
  });
}

export function deleteAd(workspaceId: string, adId: string) {
  return apiFetch<void>(`/workspaces/${workspaceId}/ads/${adId}`, { method: "DELETE" });
}

export function publishAdGroup(workspaceId: string, adGroupId: string) {
  return apiFetch<AdPublishResponse>(
    `/workspaces/${workspaceId}/ad-groups/${adGroupId}/publish`,
    { method: "POST" },
  );
}

export function publishAd(workspaceId: string, adId: string) {
  return apiFetch<AdPublishResponse>(
    `/workspaces/${workspaceId}/ads/${adId}/publish`,
    { method: "POST" },
  );
}

export function createCreative(
  workspaceId: string,
  body: {
    type: string;
    headline: string | null;
    primary_text: string | null;
    cta: string | null;
    image_url: string | null;
  },
) {
  return apiFetch<Creative>(`/workspaces/${workspaceId}/creatives`, {
    method: "POST",
    body,
  });
}
