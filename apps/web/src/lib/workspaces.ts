import { apiFetch } from "@/lib/api-client";
import type { Member, Workspace, WorkspaceMembership } from "@/types/api";

export function listWorkspaces() {
  return apiFetch<WorkspaceMembership[]>("/workspaces");
}

export function createWorkspace(payload: { name: string }) {
  return apiFetch<WorkspaceMembership>("/workspaces", {
    method: "POST",
    body: payload,
  });
}

export function getWorkspace(workspaceId: string) {
  return apiFetch<WorkspaceMembership>(`/workspaces/${workspaceId}`);
}

export function updateWorkspace(workspaceId: string, payload: { name?: string }) {
  return apiFetch<Workspace>(`/workspaces/${workspaceId}`, {
    method: "PATCH",
    body: payload,
  });
}

export function listMembers(workspaceId: string) {
  return apiFetch<Member[]>(`/workspaces/${workspaceId}/members`);
}
