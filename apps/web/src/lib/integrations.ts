import { apiFetch } from "@/lib/api-client";
import type {
  ConnectUrlResponse,
  IntegrationStatus,
  SyncLogPublic,
} from "@/types/api";

export function listIntegrations(workspaceId: string) {
  return apiFetch<IntegrationStatus[]>(`/workspaces/${workspaceId}/integrations`);
}

export function getConnectUrl(
  workspaceId: string,
  providerId: string,
  scopeMode: "read" | "write" = "write",
) {
  return apiFetch<ConnectUrlResponse>(
    `/workspaces/${workspaceId}/integrations/${providerId}/connect-url`,
    { query: { scope_mode: scopeMode } },
  );
}

export function disconnectIntegration(workspaceId: string, providerId: string) {
  return apiFetch<IntegrationStatus>(
    `/workspaces/${workspaceId}/integrations/${providerId}/disconnect`,
    { method: "POST" },
  );
}

export function syncIntegration(workspaceId: string, providerId: string) {
  return apiFetch<SyncLogPublic>(
    `/workspaces/${workspaceId}/integrations/${providerId}/sync`,
    { method: "POST" },
  );
}
