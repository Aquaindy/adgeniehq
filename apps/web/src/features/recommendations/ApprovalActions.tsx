import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api-client";
import {
  approveRecommendation,
  rejectRecommendation,
} from "@/lib/agents";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type {
  ApprovalStatus,
  ApproveRecommendationResponse,
  RecommendationPublic,
} from "@/types/api";

export function ApprovalStatusPill({ status }: { status: ApprovalStatus | null }) {
  if (!status) return <span className="pill bg-slate-100 text-slate-600">No approval</span>;
  return (
    <span
      className={cn(
        "pill",
        status === "approved" && "pill-success",
        status === "rejected" && "pill-danger",
        status === "pending" && "bg-slate-100 text-slate-600",
        status === "executed" && "pill-grape",
        status === "canceled" && "bg-slate-100 text-slate-500",
      )}
    >
      {status}
    </span>
  );
}

export function ApprovalActions({
  rec,
  onChanged,
}: {
  rec: RecommendationPublic;
  onChanged?: (updated: RecommendationPublic) => void;
}) {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [autoExecute, setAutoExecute] = useState(true);

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["recommendations", workspaceId] });
    queryClient.invalidateQueries({ queryKey: ["recommendation", workspaceId, rec.id] });
    queryClient.invalidateQueries({ queryKey: ["audit-log", workspaceId, rec.id] });
    queryClient.invalidateQueries({ queryKey: ["executions", workspaceId, rec.id] });
    queryClient.invalidateQueries({ queryKey: ["agents", "run", workspaceId, rec.agent_run_id] });
  }

  const approve = useMutation({
    mutationFn: () =>
      approveRecommendation(workspaceId!, rec.id, { autoExecute }),
    onSuccess: (response: ApproveRecommendationResponse) => {
      onChanged?.(response.recommendation);
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not approve."),
  });

  const reject = useMutation({
    mutationFn: () => rejectRecommendation(workspaceId!, rec.id),
    onSuccess: (updated) => {
      onChanged?.(updated);
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not reject."),
  });

  const status = rec.approval?.status ?? null;
  const busy = approve.isPending || reject.isPending;

  return (
    <div className="flex flex-col items-end gap-2">
      <ApprovalStatusPill status={status} />
      <div className="flex flex-wrap items-center justify-end gap-2">
        {status !== "approved" && status !== "executed" && (
          <Button
            variant="primary"
            onClick={() => {
              setError(null);
              approve.mutate();
            }}
            disabled={busy}
          >
            {approve.isPending
              ? "Approving…"
              : rec.has_executable_action && autoExecute
                ? "Approve & apply"
                : "Approve"}
          </Button>
        )}
        {status !== "rejected" && status !== "executed" && (
          <Button
            variant="ghost"
            onClick={() => {
              setError(null);
              reject.mutate();
            }}
            disabled={busy}
          >
            {reject.isPending ? "Rejecting…" : "Reject"}
          </Button>
        )}
      </div>
      {rec.has_executable_action && status !== "executed" && status !== "rejected" ? (
        <label className="flex items-center gap-1.5 text-xs text-slate-500">
          <input
            type="checkbox"
            checked={autoExecute}
            onChange={(e) => setAutoExecute(e.target.checked)}
            className="size-3.5 rounded border-slate-300 text-grape focus:ring-grape-300"
          />
          Apply to {rec.platform ?? "provider"} on approve
        </label>
      ) : null}
      {error ? <p className="text-xs text-red-700">{error}</p> : null}
    </div>
  );
}
