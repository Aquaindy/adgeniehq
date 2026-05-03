import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { UsageMeter } from "@/components/UsageMeter";
import { ApiError } from "@/lib/api-client";
import { listAgentRuns, listAgents, runAgent } from "@/lib/agents";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type {
  AgentCatalogEntry,
  AgentRunStatus,
  AgentRunSummary,
} from "@/types/api";

export function AgentsDashboardPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();

  const catalog = useQuery({
    queryKey: ["agents", "catalog", workspaceId],
    queryFn: () => listAgents(workspaceId!),
    enabled: !!workspaceId,
  });

  const runs = useQuery({
    queryKey: ["agents", "runs", workspaceId],
    queryFn: () => listAgentRuns(workspaceId!),
    enabled: !!workspaceId,
  });

  const [runningType, setRunningType] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  const trigger = useMutation({
    mutationFn: (agentType: string) =>
      runAgent(workspaceId!, { agent_type: agentType }),
    onMutate: (agentType) => {
      setRunningType(agentType);
      setRunError(null);
    },
    onSettled: () => {
      setRunningType(null);
      queryClient.invalidateQueries({ queryKey: ["agents", "catalog", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["agents", "runs", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["recommendations", workspaceId] });
    },
    onError: (err) => {
      setRunError(err instanceof ApiError ? err.message : "Could not run agent.");
    },
  });

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header>
        <p className="text-xs uppercase tracking-wider text-grape-700">Agents</p>
        <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">Your AI growth team</h1>
        <p className="mt-2 text-sm text-slate-500">
          Each agent runs against your real workspace data, saves its outputs and tasks, and emits
          recommendations you can review. M4 ships two agents; the rest land in M5+ alongside
          integrations.
        </p>
      </header>

      <UsageMeter resource="agent_runs" />

      {runError ? (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {runError}
        </div>
      ) : null}

      <section className="grid gap-4 lg:grid-cols-2">
        {catalog.data?.map((agent) => (
          <AgentCard
            key={agent.type}
            agent={agent}
            onRun={() => trigger.mutate(agent.type)}
            running={runningType === agent.type}
          />
        ))}
      </section>

      <Card>
        <CardHeader title="Recent runs" subtitle="All agent invocations for this workspace." />
        {runs.data && runs.data.length > 0 ? (
          <ul className="mt-3 flex flex-col divide-y divide-slate-100">
            {runs.data.map((r) => (
              <RunRow key={r.id} run={r} />
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-slate-500">No runs yet — trigger an agent above.</p>
        )}
      </Card>
    </div>
  );
}

function AgentCard({
  agent,
  onRun,
  running,
}: {
  agent: AgentCatalogEntry;
  onRun: () => void;
  running: boolean;
}) {
  return (
    <Card>
      <CardHeader
        title={agent.title}
        subtitle={agent.description}
        action={<StatusPill status={agent.last_run?.status ?? null} />}
      />
      <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-slate-400">Agent</dt>
          <dd className="font-mono text-xs text-slate-600">{agent.type}</dd>
        </div>
        <div>
          <dt className="text-slate-400">Last run</dt>
          <dd className="font-medium text-ink">
            {agent.last_run?.completed_at
              ? new Date(agent.last_run.completed_at).toLocaleString()
              : "—"}
          </dd>
        </div>
      </dl>
      <div className="mt-4 flex items-center justify-between gap-3">
        {agent.last_run ? (
          <Link
            to={`/agents/runs/${agent.last_run.id}`}
            className="text-sm font-medium text-grape-700 hover:text-grape-800"
          >
            View last run →
          </Link>
        ) : (
          <span className="text-xs text-slate-400">No runs yet</span>
        )}
        <Button onClick={onRun} disabled={running}>
          {running ? "Running…" : "Run now"}
        </Button>
      </div>
    </Card>
  );
}

function RunRow({ run }: { run: AgentRunSummary }) {
  return (
    <li className="flex items-center justify-between gap-3 py-3">
      <Link
        to={`/agents/runs/${run.id}`}
        className="flex-1 text-sm font-medium text-ink hover:text-grape-700"
      >
        {run.agent_type}
      </Link>
      <span className="text-xs text-slate-400">
        {run.completed_at
          ? new Date(run.completed_at).toLocaleString()
          : run.started_at
            ? new Date(run.started_at).toLocaleString()
            : "—"}
      </span>
      <StatusPill status={run.status} />
    </li>
  );
}

export function StatusPill({ status }: { status: AgentRunStatus | null }) {
  if (!status) return <span className="pill bg-slate-100 text-slate-600">No runs</span>;
  return (
    <span
      className={cn(
        "pill",
        status === "succeeded" && "pill-success",
        status === "failed" && "pill-danger",
        status === "running" && "pill-grape",
        status === "queued" && "bg-slate-100 text-slate-600",
      )}
    >
      {status}
    </span>
  );
}
