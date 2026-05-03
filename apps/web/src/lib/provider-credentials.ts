import { apiFetch } from "@/lib/api-client";

export type ProviderId = "openai" | "anthropic" | "google_ai";

export type ProviderSpec = {
  provider_id: ProviderId;
  display_name: string;
  docs_url: string;
  secret_hint: string;
};

export type ProviderCredential = {
  id: string;
  provider: ProviderId;
  label: string | null;
  last_four: string;
  last_tested_at: string | null;
  last_test_status: "ok" | "failed" | null;
  last_test_error: string | null;
  revoked_at: string | null;
  created_at: string;
};

export function listProviderSpecs(workspaceId: string) {
  return apiFetch<ProviderSpec[]>(
    `/workspaces/${workspaceId}/provider-credentials/specs`,
  );
}

export function listProviderCredentials(workspaceId: string) {
  return apiFetch<ProviderCredential[]>(
    `/workspaces/${workspaceId}/provider-credentials`,
  );
}

export function addProviderCredential(
  workspaceId: string,
  payload: { provider: ProviderId; secret: string; label?: string | null },
) {
  return apiFetch<ProviderCredential>(
    `/workspaces/${workspaceId}/provider-credentials`,
    { method: "POST", body: payload },
  );
}

export function testProviderCredential(workspaceId: string, credentialId: string) {
  return apiFetch<ProviderCredential>(
    `/workspaces/${workspaceId}/provider-credentials/${credentialId}/test`,
    { method: "POST" },
  );
}

export function revokeProviderCredential(
  workspaceId: string,
  credentialId: string,
) {
  return apiFetch<ProviderCredential>(
    `/workspaces/${workspaceId}/provider-credentials/${credentialId}`,
    { method: "DELETE" },
  );
}
