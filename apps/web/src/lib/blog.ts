import { API_BASE_URL } from "@/lib/constants";
import { apiFetch } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import type {
  AiAssistAction,
  AiAssistResponse,
  ContentDraftPublic,
  ImageUploadResponse,
} from "@/types/api";


export function listBlogPosts(workspaceId: string) {
  return apiFetch<ContentDraftPublic[]>(
    `/workspaces/${workspaceId}/content-drafts?type=blog_post`,
  );
}


export function createBlogPost(workspaceId: string, title: string) {
  return apiFetch<ContentDraftPublic>(
    `/workspaces/${workspaceId}/content-drafts`,
    {
      method: "POST",
      body: {
        type: "blog_post",
        title: title || "Untitled post",
        body: "Start writing here…",
      },
    },
  );
}


export function getBlogPost(workspaceId: string, draftId: string) {
  return apiFetch<ContentDraftPublic>(
    `/workspaces/${workspaceId}/content-drafts/${draftId}`,
  );
}


export function updateBlogPost(
  workspaceId: string,
  draftId: string,
  patch: Partial<ContentDraftPublic>,
) {
  return apiFetch<ContentDraftPublic>(
    `/workspaces/${workspaceId}/content-drafts/${draftId}`,
    { method: "PATCH", body: patch },
  );
}


export function approveBlogPost(workspaceId: string, draftId: string) {
  return apiFetch<ContentDraftPublic>(
    `/workspaces/${workspaceId}/content-drafts/${draftId}/approve`,
    { method: "POST" },
  );
}


export function publishBlogPost(workspaceId: string, draftId: string) {
  return apiFetch<ContentDraftPublic>(
    `/workspaces/${workspaceId}/content-drafts/${draftId}/publish`,
    { method: "POST", body: {} },
  );
}


export function archiveBlogPost(workspaceId: string, draftId: string) {
  return apiFetch<ContentDraftPublic>(
    `/workspaces/${workspaceId}/content-drafts/${draftId}/archive`,
    { method: "POST" },
  );
}


export function aiAssist(
  workspaceId: string,
  draftId: string,
  action: AiAssistAction,
  selection?: string | null,
  instructions?: string | null,
) {
  return apiFetch<AiAssistResponse>(
    `/workspaces/${workspaceId}/content-drafts/${draftId}/ai-assist`,
    {
      method: "POST",
      body: { action, selection, instructions },
    },
  );
}


/**
 * Multipart image upload. apiFetch is JSON-only, so we hit fetch() directly
 * here, attach the bearer token if we have one, and let the server validate
 * content-type / size.
 */
export async function uploadBlogImage(
  workspaceId: string,
  file: File,
): Promise<ImageUploadResponse> {
  const url = `${API_BASE_URL.replace(/\/$/, "")}/workspaces/${workspaceId}/content-drafts/images`;
  const formData = new FormData();
  formData.append("file", file);

  const headers: Record<string, string> = {};
  const token = useAuthStore.getState().accessToken;
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(url, {
    method: "POST",
    body: formData,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    let message = `Upload failed (HTTP ${response.status})`;
    try {
      const parsed = JSON.parse(text);
      message = parsed?.error?.message ?? message;
    } catch {
      /* fall through */
    }
    throw new Error(message);
  }
  return (await response.json()) as ImageUploadResponse;
}
