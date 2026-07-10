import { apiFetch } from "@/lib/api-client";
import { API_BASE_URL } from "@/lib/constants";
import type {
  ContentDraftPublic,
  ContentDraftStatus,
  ContentDraftType,
  GenerateContentDraftRequest,
} from "@/types/api";

/** Uploaded/generated images are served from the API HOST at `/uploads/...`
 * (outside `/api/v1`), while the SPA can live on a different origin. Resolve a
 * stored relative image path against the API origin so `<img src>` works. */
export function resolveUploadUrl(path: string | null | undefined): string {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  try {
    return new URL(path, new URL(API_BASE_URL).origin).toString();
  } catch {
    return path;
  }
}

export function listContentDrafts(
  workspaceId: string,
  filters?: { type?: ContentDraftType; status?: ContentDraftStatus },
) {
  const params = new URLSearchParams();
  if (filters?.type) params.set("type", filters.type);
  if (filters?.status) params.set("status", filters.status);
  const qs = params.toString();
  return apiFetch<ContentDraftPublic[]>(
    `/workspaces/${workspaceId}/content-drafts${qs ? `?${qs}` : ""}`,
  );
}

export function getContentDraft(workspaceId: string, draftId: string) {
  return apiFetch<ContentDraftPublic>(
    `/workspaces/${workspaceId}/content-drafts/${draftId}`,
  );
}

export function generateContentDraft(
  workspaceId: string,
  payload: GenerateContentDraftRequest,
) {
  return apiFetch<ContentDraftPublic>(
    `/workspaces/${workspaceId}/content-drafts/generate`,
    { method: "POST", body: payload },
  );
}

export function createContentDraft(
  workspaceId: string,
  payload: {
    type: ContentDraftType;
    title: string;
    body: string;
    target_url?: string | null;
    keywords?: string[];
    seo_metadata?: Record<string, unknown> | null;
    notes?: string | null;
  },
) {
  return apiFetch<ContentDraftPublic>(
    `/workspaces/${workspaceId}/content-drafts`,
    { method: "POST", body: payload },
  );
}

export function updateContentDraft(
  workspaceId: string,
  draftId: string,
  payload: {
    title?: string;
    body?: string;
    target_url?: string | null;
    keywords?: string[];
    seo_metadata?: Record<string, unknown> | null;
    notes?: string | null;
  },
) {
  return apiFetch<ContentDraftPublic>(
    `/workspaces/${workspaceId}/content-drafts/${draftId}`,
    { method: "PATCH", body: payload },
  );
}

export function approveContentDraft(workspaceId: string, draftId: string) {
  return apiFetch<ContentDraftPublic>(
    `/workspaces/${workspaceId}/content-drafts/${draftId}/approve`,
    { method: "POST" },
  );
}

export function rejectContentDraft(
  workspaceId: string,
  draftId: string,
  reason?: string,
) {
  return apiFetch<ContentDraftPublic>(
    `/workspaces/${workspaceId}/content-drafts/${draftId}/reject`,
    { method: "POST", body: reason ? { reason } : undefined },
  );
}

export function publishContentDraft(
  workspaceId: string,
  draftId: string,
  publicationUrl?: string,
) {
  return apiFetch<ContentDraftPublic>(
    `/workspaces/${workspaceId}/content-drafts/${draftId}/publish`,
    {
      method: "POST",
      body: publicationUrl ? { publication_url: publicationUrl } : undefined,
    },
  );
}

export function archiveContentDraft(workspaceId: string, draftId: string) {
  return apiFetch<ContentDraftPublic>(
    `/workspaces/${workspaceId}/content-drafts/${draftId}/archive`,
    { method: "POST" },
  );
}

export function generateContentDraftImage(workspaceId: string, draftId: string) {
  return apiFetch<ContentDraftPublic>(
    `/workspaces/${workspaceId}/content-drafts/${draftId}/image`,
    { method: "POST" },
  );
}
