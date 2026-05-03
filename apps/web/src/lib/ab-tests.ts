import { apiFetch } from "@/lib/api-client";
import type { AbTestPublic, CreateAbTestRequest } from "@/types/api";

export function listAbTests(workspaceId: string) {
  return apiFetch<AbTestPublic[]>(`/workspaces/${workspaceId}/ab-tests`);
}

export function getAbTest(workspaceId: string, testId: string) {
  return apiFetch<AbTestPublic>(`/workspaces/${workspaceId}/ab-tests/${testId}`);
}

export function createAbTest(workspaceId: string, payload: CreateAbTestRequest) {
  return apiFetch<AbTestPublic>(`/workspaces/${workspaceId}/ab-tests`, {
    method: "POST",
    body: payload,
  });
}

export function launchAbTest(workspaceId: string, testId: string) {
  return apiFetch<AbTestPublic>(
    `/workspaces/${workspaceId}/ab-tests/${testId}/launch`,
    { method: "POST" },
  );
}

export function recordVariantMetrics(
  workspaceId: string,
  testId: string,
  variantId: string,
  metrics: Record<string, unknown>,
) {
  return apiFetch<AbTestPublic>(
    `/workspaces/${workspaceId}/ab-tests/${testId}/variants/${variantId}/metrics`,
    { method: "POST", body: { metrics } },
  );
}

export function declareWinner(
  workspaceId: string,
  testId: string,
  variantId: string,
) {
  return apiFetch<AbTestPublic>(
    `/workspaces/${workspaceId}/ab-tests/${testId}/declare-winner`,
    { method: "POST", body: { variant_id: variantId } },
  );
}

export function archiveAbTest(workspaceId: string, testId: string) {
  return apiFetch<AbTestPublic>(
    `/workspaces/${workspaceId}/ab-tests/${testId}/archive`,
    { method: "POST" },
  );
}
