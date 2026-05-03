import { apiFetch } from "@/lib/api-client";
import type { AgentRunDetail, LandingPagePublic } from "@/types/api";

export function listLandingPages(workspaceId: string) {
  return apiFetch<LandingPagePublic[]>(`/workspaces/${workspaceId}/landing-pages`);
}

export function createLandingPage(
  workspaceId: string,
  payload: { url: string; label?: string; is_primary?: boolean },
) {
  return apiFetch<LandingPagePublic>(`/workspaces/${workspaceId}/landing-pages`, {
    method: "POST",
    body: payload,
  });
}

export function importFromOnboarding(workspaceId: string) {
  return apiFetch<{ created: number }>(
    `/workspaces/${workspaceId}/landing-pages/import`,
    { method: "POST" },
  );
}

export function deleteLandingPage(workspaceId: string, landingPageId: string) {
  return apiFetch<void>(
    `/workspaces/${workspaceId}/landing-pages/${landingPageId}`,
    { method: "DELETE" },
  );
}

export function auditLandingPage(workspaceId: string, landingPageId: string) {
  return apiFetch<AgentRunDetail>(
    `/workspaces/${workspaceId}/landing-pages/${landingPageId}/audit`,
    { method: "POST" },
  );
}
