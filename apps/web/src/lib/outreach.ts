import { apiFetch } from "@/lib/api-client";
import type {
  BacklinkProspectPublic,
  OutreachEmailPublic,
  ProspectStatus,
} from "@/types/api";

export function listProspects(workspaceId: string) {
  return apiFetch<BacklinkProspectPublic[]>(
    `/workspaces/${workspaceId}/backlink-prospects`,
  );
}

export function getProspect(workspaceId: string, prospectId: string) {
  return apiFetch<BacklinkProspectPublic>(
    `/workspaces/${workspaceId}/backlink-prospects/${prospectId}`,
  );
}

export function createProspect(
  workspaceId: string,
  payload: {
    domain: string;
    page_url?: string | null;
    contact_name?: string | null;
    contact_email?: string | null;
    contact_role?: string | null;
    relevance_score?: number | null;
    domain_authority?: number | null;
    notes?: string | null;
  },
) {
  return apiFetch<BacklinkProspectPublic>(
    `/workspaces/${workspaceId}/backlink-prospects`,
    { method: "POST", body: payload },
  );
}

export function updateProspect(
  workspaceId: string,
  prospectId: string,
  payload: Partial<{
    page_url: string | null;
    contact_name: string | null;
    contact_email: string | null;
    contact_role: string | null;
    relevance_score: number | null;
    domain_authority: number | null;
    notes: string | null;
    status: ProspectStatus;
    backlink_url: string | null;
  }>,
) {
  return apiFetch<BacklinkProspectPublic>(
    `/workspaces/${workspaceId}/backlink-prospects/${prospectId}`,
    { method: "PATCH", body: payload },
  );
}

export function listEmailsForProspect(workspaceId: string, prospectId: string) {
  return apiFetch<OutreachEmailPublic[]>(
    `/workspaces/${workspaceId}/backlink-prospects/${prospectId}/emails`,
  );
}

export function draftEmail(
  workspaceId: string,
  prospectId: string,
  payload?: { angle?: string | null; sender_name?: string | null },
) {
  return apiFetch<OutreachEmailPublic>(
    `/workspaces/${workspaceId}/backlink-prospects/${prospectId}/draft-email`,
    { method: "POST", body: payload },
  );
}

export function getEmail(workspaceId: string, emailId: string) {
  return apiFetch<OutreachEmailPublic>(
    `/workspaces/${workspaceId}/outreach-emails/${emailId}`,
  );
}

export function updateEmail(
  workspaceId: string,
  emailId: string,
  payload: { subject?: string; body?: string },
) {
  return apiFetch<OutreachEmailPublic>(
    `/workspaces/${workspaceId}/outreach-emails/${emailId}`,
    { method: "PATCH", body: payload },
  );
}

export function approveEmail(workspaceId: string, emailId: string) {
  return apiFetch<OutreachEmailPublic>(
    `/workspaces/${workspaceId}/outreach-emails/${emailId}/approve`,
    { method: "POST" },
  );
}

export function sendEmail(workspaceId: string, emailId: string) {
  return apiFetch<OutreachEmailPublic>(
    `/workspaces/${workspaceId}/outreach-emails/${emailId}/send`,
    { method: "POST" },
  );
}

export function markEmailReplied(
  workspaceId: string,
  emailId: string,
  payload?: { won?: boolean; backlink_url?: string | null },
) {
  return apiFetch<OutreachEmailPublic>(
    `/workspaces/${workspaceId}/outreach-emails/${emailId}/replied`,
    { method: "POST", body: payload },
  );
}
