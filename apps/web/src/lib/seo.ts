import { apiFetch } from "@/lib/api-client";
import type {
  KeywordPublic,
  SearchConsoleSyncResponse,
  SeoProjectPublic,
} from "@/types/api";

export function getSeoProject(workspaceId: string) {
  return apiFetch<SeoProjectPublic>(`/workspaces/${workspaceId}/seo/project`);
}

export function listSeoKeywords(workspaceId: string) {
  return apiFetch<KeywordPublic[]>(`/workspaces/${workspaceId}/seo/keywords`);
}

export function syncSearchConsole(workspaceId: string) {
  return apiFetch<SearchConsoleSyncResponse>(`/workspaces/${workspaceId}/seo/sync`, {
    method: "POST",
  });
}
