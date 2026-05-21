import { apiFetch } from "@/lib/api-client";

export type AppSumoCode = {
  code: string;
  redeemed_at: string | null;
};

export type AppSumoStatus = {
  tier: number;
  codes_redeemed: number;
  max_tier: number;
  can_stack_more: boolean;
  plan_code: string | null;
  plan_display_name: string | null;
  codes: AppSumoCode[];
};

export function getAppSumoStatus(workspaceId: string) {
  return apiFetch<AppSumoStatus>(`/workspaces/${workspaceId}/appsumo/status`);
}

export function redeemAppSumoCode(workspaceId: string, code: string) {
  return apiFetch<AppSumoStatus>(`/workspaces/${workspaceId}/appsumo/redeem`, {
    method: "POST",
    body: { code },
  });
}
