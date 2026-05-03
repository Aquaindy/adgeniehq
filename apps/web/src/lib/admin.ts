import { apiFetch } from "@/lib/api-client";
import type { AdminOverview, AdminUserRow, AdminWorkspaceRow } from "@/types/api";

export function getAdminOverview() {
  return apiFetch<AdminOverview>("/admin/overview");
}

export function listAdminWorkspaces() {
  return apiFetch<AdminWorkspaceRow[]>("/admin/workspaces");
}

export function listAdminUsers() {
  return apiFetch<AdminUserRow[]>("/admin/users");
}
