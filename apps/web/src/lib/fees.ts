import { apiFetch } from "@/lib/api-client";
import type {
  AdminRevenueSummary,
  FeeInvoice,
  FeeQuote,
  FeeRule,
  FeeRuleUpsert,
  PaymentProviderInfo,
  WorkspaceFeeSummary,
} from "@/types/api";

// --- Member-facing ---

export function getCampaignFeeQuote(workspaceId: string, campaignId: string) {
  return apiFetch<FeeQuote>(
    `/workspaces/${workspaceId}/campaigns/${campaignId}/fee-quote`,
  );
}

export function getPrelaunchFeeQuote(
  workspaceId: string,
  params: { provider: string; campaign_type: string; daily_budget_cents: number },
) {
  return apiFetch<FeeQuote>(`/workspaces/${workspaceId}/billing/fee-quote`, {
    query: params,
  });
}

export function getWorkspaceFees(workspaceId: string, period?: string) {
  return apiFetch<WorkspaceFeeSummary>(`/workspaces/${workspaceId}/billing/fees`, {
    query: period ? { period } : undefined,
  });
}

// --- Admin (superuser) ---

export function listFeeRules() {
  return apiFetch<FeeRule[]>(`/admin/fee-rules`);
}

export function upsertFeeRule(rule: FeeRuleUpsert) {
  return apiFetch<FeeRule>(`/admin/fee-rules`, { method: "POST", body: rule });
}

export function updateFeeRule(
  ruleId: string,
  updates: Partial<Omit<FeeRuleUpsert, "provider" | "campaign_type">> & {
    is_active?: boolean;
  },
) {
  return apiFetch<FeeRule>(`/admin/fee-rules/${ruleId}`, {
    method: "PATCH",
    body: updates,
  });
}

export function deleteFeeRule(ruleId: string) {
  return apiFetch<void>(`/admin/fee-rules/${ruleId}`, { method: "DELETE" });
}

export function getFeeRevenue(period?: string) {
  return apiFetch<AdminRevenueSummary>(`/admin/fees/revenue`, {
    query: period ? { period } : undefined,
  });
}

// --- Collection layer (admin) ---

export function listPaymentProviders() {
  return apiFetch<PaymentProviderInfo[]>(`/admin/fees/payment-providers`);
}

export function listFeeInvoices(workspaceId?: string) {
  return apiFetch<FeeInvoice[]>(`/admin/fees/invoices`, {
    query: workspaceId ? { workspace_id: workspaceId } : undefined,
  });
}

export function generateFeeInvoice(body: {
  workspace_id: string;
  provider: string;
  period?: string | null;
}) {
  return apiFetch<FeeInvoice>(`/admin/fees/invoices`, { method: "POST", body });
}

export function markFeeInvoicePaid(invoiceId: string) {
  return apiFetch<FeeInvoice>(`/admin/fees/invoices/${invoiceId}/mark-paid`, {
    method: "POST",
  });
}

export function voidFeeInvoice(invoiceId: string) {
  return apiFetch<FeeInvoice>(`/admin/fees/invoices/${invoiceId}/void`, {
    method: "POST",
  });
}

// --- Member-facing invoices ---

export function getWorkspaceInvoices(workspaceId: string) {
  return apiFetch<FeeInvoice[]>(`/workspaces/${workspaceId}/billing/invoices`);
}
