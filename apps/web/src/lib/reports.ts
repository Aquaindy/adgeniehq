import { API_BASE_URL } from "@/lib/constants";
import { apiFetch } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import type { ReportDetail, ReportPeriod, ReportSummaryRow } from "@/types/api";

export function listReports(workspaceId: string) {
  return apiFetch<ReportSummaryRow[]>(`/workspaces/${workspaceId}/reports`);
}

export function generateReport(
  workspaceId: string,
  payload: { period: ReportPeriod; email_to?: string },
) {
  return apiFetch<ReportDetail>(`/workspaces/${workspaceId}/reports/generate`, {
    method: "POST",
    body: payload,
  });
}

export function getReport(workspaceId: string, reportId: string) {
  return apiFetch<ReportDetail>(`/workspaces/${workspaceId}/reports/${reportId}`);
}

export async function fetchReportBlob(
  workspaceId: string,
  reportId: string,
  format: "pdf" | "csv",
): Promise<Blob> {
  const token = useAuthStore.getState().accessToken;
  const url = new URL(
    `workspaces/${workspaceId}/reports/${reportId}/download`,
    API_BASE_URL.replace(/\/$/, "") + "/",
  );
  url.searchParams.set("format", format);
  const response = await fetch(url.toString(), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Download failed (${response.status}).`);
  }
  return response.blob();
}
