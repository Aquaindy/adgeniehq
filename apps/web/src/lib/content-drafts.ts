import { apiFetch } from "@/lib/api-client";
import { API_BASE_URL } from "@/lib/constants";
import { useAuthStore } from "@/stores/auth-store";
import type {
  ContentDraftPublic,
  ContentDraftStatus,
  ContentDraftType,
  GenerateContentDraftRequest,
} from "@/types/api";

export type ExportFormat = "txt" | "docx";

async function fetchBlob(path: string): Promise<Blob> {
  const token = useAuthStore.getState().accessToken;
  const url = new URL(path, API_BASE_URL.replace(/\/$/, "") + "/");
  const response = await fetch(url.toString(), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: "include",
  });
  if (!response.ok) throw new Error(`Download failed (${response.status}).`);
  return response.blob();
}

/** Trigger a browser download for a blob fetched from the API. */
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function fetchContentDraftBlob(
  workspaceId: string,
  draftId: string,
  format: ExportFormat,
): Promise<Blob> {
  return fetchBlob(
    `workspaces/${workspaceId}/content-drafts/${draftId}/download?format=${format}`,
  );
}

/** Download several drafts (e.g. a social pack) as one .txt or .docx. */
export function fetchContentDraftsBundleBlob(
  workspaceId: string,
  format: ExportFormat,
  ids: string[],
): Promise<Blob> {
  const qs = new URLSearchParams({ format });
  if (ids.length) qs.set("ids", ids.join(","));
  return fetchBlob(
    `workspaces/${workspaceId}/content-drafts/download?${qs.toString()}`,
  );
}

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

export type ContentImageStyle = "concept" | "product";

export function generateContentDraftImage(
  workspaceId: string,
  draftId: string,
  style: ContentImageStyle = "concept",
) {
  const qs = style === "product" ? "?style=product" : "";
  return apiFetch<ContentDraftPublic>(
    `/workspaces/${workspaceId}/content-drafts/${draftId}/image${qs}`,
    { method: "POST" },
  );
}
