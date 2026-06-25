import { apiFetch } from "@/lib/api-client";
import type {
  AudienceListResponse,
  AutoresponderConnection,
  AutoresponderProviderInfo,
  ContactInput,
  ContactSync,
  PullContactsResponse,
} from "@/types/api";

const base = (workspaceId: string) => `/workspaces/${workspaceId}/autoresponders`;

export function getAutoresponderCatalog(workspaceId: string) {
  return apiFetch<AutoresponderProviderInfo[]>(`${base(workspaceId)}/catalog`);
}

export function listAutoresponders(workspaceId: string) {
  return apiFetch<AutoresponderConnection[]>(base(workspaceId));
}

export function connectAutoresponder(
  workspaceId: string,
  provider: string,
  body: { api_key?: string | null; config?: Record<string, unknown> },
) {
  return apiFetch<AutoresponderConnection>(
    `${base(workspaceId)}/${provider}/connect`,
    { method: "POST", body },
  );
}

export function disconnectAutoresponder(workspaceId: string, provider: string) {
  return apiFetch<AutoresponderConnection>(
    `${base(workspaceId)}/${provider}/disconnect`,
    { method: "POST" },
  );
}

export function listAudiences(workspaceId: string, provider: string) {
  return apiFetch<AudienceListResponse>(
    `${base(workspaceId)}/${provider}/audiences`,
  );
}

export function pushContacts(
  workspaceId: string,
  provider: string,
  body: {
    audience_id?: string | null;
    audience_name?: string | null;
    source?: string;
    contacts: ContactInput[];
  },
) {
  return apiFetch<ContactSync>(`${base(workspaceId)}/${provider}/push`, {
    method: "POST",
    body,
  });
}

export function pullContacts(
  workspaceId: string,
  provider: string,
  body: { audience_id?: string | null; limit?: number },
) {
  return apiFetch<PullContactsResponse>(`${base(workspaceId)}/${provider}/pull`, {
    method: "POST",
    body,
  });
}

export function listAutoresponderActivity(
  workspaceId: string,
  provider?: string,
) {
  return apiFetch<ContactSync[]>(`${base(workspaceId)}/activity`, {
    query: provider ? { provider } : undefined,
  });
}
