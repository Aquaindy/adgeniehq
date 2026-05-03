import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";


import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import {
  executeRecommendation,
  listExecutions,
  revertExecution,
} from "@/lib/agents";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type {
  ExecutionPublic,
  ExecutionStatus,
  RecommendationPublic,
} from "@/types/api";

const STATUS_PILL: Record<ExecutionStatus, string> = {
  pending: "bg-slate-100 text-slate-600",
  running: "bg-amber-100 text-amber-700",
  succeeded: "pill-success",
  failed: "pill-danger",
  reverted: "bg-slate-100 text-slate-500",
};

export function ExecutionsPanel({ rec }: { rec: RecommendationPublic }) {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const executions = useQuery({
    queryKey: ["executions", workspaceId, rec.id],
    queryFn: () => listExecutions(workspaceId!, rec.id),
    enabled: !!workspaceId && !!rec.id,
    initialData: rec.executions,
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["executions", workspaceId, rec.id] });
    queryClient.invalidateQueries({ queryKey: ["recommendation", workspaceId, rec.id] });
    queryClient.invalidateQueries({ queryKey: ["audit-log", workspaceId, rec.id] });
    queryClient.invalidateQueries({ queryKey: ["recommendations", workspaceId] });
  }

  // Stable per-mutation key so a double-click on the retry button doesn't
  // dispatch two writes — the second tap returns the original row.
  const [retryKey, setRetryKey] = useState<string | null>(null);
  const execute = useMutation({
    mutationFn: () => {
      const key =
        retryKey ??
        (typeof crypto !== "undefined" && "randomUUID" in crypto
          ? `retry:${crypto.randomUUID()}`
          : `retry:${Date.now()}-${Math.random().toString(36).slice(2)}`);
      if (retryKey === null) setRetryKey(key);
      return executeRecommendation(workspaceId!, rec.id, key);
    },
    onSuccess: () => {
      invalidate();
      setRetryKey(null);
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not execute."),
  });

  const revert = useMutation({
    mutationFn: (executionId: string) => revertExecution(workspaceId!, executionId),
    onSuccess: () => invalidate(),
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not revert."),
  });

  if (!rec.has_executable_action) {
    return null;
  }

  const rows = executions.data ?? [];
  const lastSuccess = [...rows]
    .reverse()
    .find((row) => row.status === "succeeded" && !row.is_revert);
  const showRetry =
    rec.approval?.status === "approved" &&
    rows.some((row) => row.status === "failed" && !row.is_revert);

  return (
    <Card>
      <CardHeader
        title="Provider execution"
        subtitle="What was sent to the connected ad platform — with prior state captured for revert."
        action={
          showRetry ? (
            <Button
              variant="primary"
              onClick={() => {
                setError(null);
                execute.mutate();
              }}
              disabled={execute.isPending}
            >
              {execute.isPending ? "Retrying…" : "Retry execution"}
            </Button>
          ) : null
        }
      />

      {error ? (
        <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      {rows.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">
          Approve this recommendation to apply the change to{" "}
          {rec.platform ?? "the connected provider"}.
        </p>
      ) : (
        <ol className="mt-3 flex flex-col gap-2 text-sm">
          {rows.map((row) => (
            <ExecutionRow
              key={row.id}
              row={row}
              canRevert={
                !row.is_revert &&
                row.status === "succeeded" &&
                lastSuccess?.id === row.id
              }
              onRevert={() => {
                setError(null);
                revert.mutate(row.id);
              }}
              isReverting={revert.isPending}
            />
          ))}
        </ol>
      )}
    </Card>
  );
}

function ExecutionRow({
  row,
  canRevert,
  onRevert,
  isReverting,
}: {
  row: ExecutionPublic;
  canRevert: boolean;
  onRevert: () => void;
  isReverting: boolean;
}) {
  return (
    <li className="flex flex-col gap-2 rounded-xl border border-slate-100 px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className={cn("pill", STATUS_PILL[row.status])}>{row.status}</span>
          <span className="font-mono text-xs text-grape-700">{row.action_type}</span>
          {row.is_revert ? (
            <span className="pill bg-slate-100 text-slate-500">revert</span>
          ) : null}
        </div>
        <span className="text-xs text-slate-400">
          {row.executed_at
            ? new Date(row.executed_at).toLocaleString()
            : new Date(row.created_at).toLocaleString()}
        </span>
      </div>
      <div className="text-xs text-slate-500">
        {row.provider}
        {row.target_external_account_id ? ` · acct ${row.target_external_account_id}` : ""}
        {row.target_external_id ? ` · campaign ${row.target_external_id}` : ""}
      </div>

      {row.error_message ? (
        <pre className="mt-1 max-h-32 overflow-auto rounded-lg bg-red-50 p-2 text-xs text-red-700">
{row.error_message}
        </pre>
      ) : null}

      {row.prior_state || row.payload ? (
        <details className="text-xs text-slate-500">
          <summary className="cursor-pointer select-none">Payload + prior state</summary>
          <pre className="mt-1 max-h-48 overflow-auto rounded-lg bg-slate-50 p-2 font-mono">
{JSON.stringify({ payload: row.payload, prior_state: row.prior_state }, null, 2)}
          </pre>
        </details>
      ) : null}

      {canRevert ? (
        <div>
          <Button
            variant="ghost"
            onClick={onRevert}
            disabled={isReverting}
          >
            {isReverting ? "Reverting…" : "Revert this change"}
          </Button>
          <p className="mt-1 text-[11px] text-slate-400">
            Restores prior state on the provider. Admin or higher.
          </p>
        </div>
      ) : null}
    </li>
  );
}
