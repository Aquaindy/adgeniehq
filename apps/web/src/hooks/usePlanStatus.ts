import { useQuery } from "@tanstack/react-query";

import { getBillingStatus } from "@/lib/billing";
import { useWorkspaceStore } from "@/stores/workspace-store";

/**
 * Single hook every plan-aware UI uses. Caches the billing status for
 * 30 seconds so the topbar Plan badge and the per-page usage meters
 * share one network round-trip on most navigations.
 */
export function usePlanStatus() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  return useQuery({
    queryKey: ["billing", workspaceId],
    queryFn: () => getBillingStatus(workspaceId!),
    enabled: !!workspaceId,
    staleTime: 30_000,
  });
}
