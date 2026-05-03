import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import { getAgentRun } from "@/lib/agents";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type {
  AgentTaskPublic,
  RecommendationPublic,
  RiskLevel,
  SkillOutputPublic,
} from "@/types/api";

import { StatusPill } from "@/features/agents/AgentsDashboardPage";

export function AgentRunDetailPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const { runId } = useParams<{ runId: string }>();

  const detail = useQuery({
    queryKey: ["agents", "run", workspaceId, runId],
    queryFn: () => getAgentRun(workspaceId!, runId!),
    enabled: !!workspaceId && !!runId,
  });

  if (detail.isLoading) {
    return <div className="text-sm text-slate-400">Loading run…</div>;
  }

  if (detail.error) {
    const code = detail.error instanceof ApiError ? detail.error.code : null;
    return (
      <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
        {code === "agent_run_not_found"
          ? "Agent run not found in this workspace."
          : detail.error instanceof Error
            ? detail.error.message
            : "Could not load run."}
      </div>
    );
  }

  if (!detail.data) return null;
  const run = detail.data;

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <header className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-grape-700">Agent run</p>
          <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">{run.agent_type}</h1>
          <p className="mt-1 text-xs text-slate-400">
            Started {run.started_at ? new Date(run.started_at).toLocaleString() : "—"}
            {run.completed_at
              ? ` · finished ${new Date(run.completed_at).toLocaleString()}`
              : ""}
            {run.model_used ? ` · model ${run.model_used}` : ""}
          </p>
        </div>
        <StatusPill status={run.status} />
      </header>

      {run.error_message ? (
        <Card className="border-red-200 bg-red-50/60">
          <CardHeader title="Error" />
          <pre className="mt-3 whitespace-pre-wrap break-words text-sm text-red-700">
            {run.error_message}
          </pre>
        </Card>
      ) : null}

      <Card>
        <CardHeader title="Output payload" subtitle="Top-level summary returned by the agent." />
        <pre className="mt-3 max-h-72 overflow-auto rounded-xl bg-slate-50 p-3 font-mono text-xs text-slate-700">
{JSON.stringify(run.output_payload ?? {}, null, 2)}
        </pre>
      </Card>

      <Card>
        <CardHeader
          title="Tasks"
          subtitle={`${run.tasks.length} step${run.tasks.length === 1 ? "" : "s"}`}
        />
        {run.tasks.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">No tasks recorded.</p>
        ) : (
          <ul className="mt-3 flex flex-col gap-2">
            {run.tasks.map((t) => (
              <TaskRow key={t.id} task={t} />
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <CardHeader
          title="Recommendations"
          subtitle={`${run.recommendations.length} produced — review/approve flow lands in M5.`}
        />
        {run.recommendations.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">
            No recommendations from this run. That's good — it means no high-priority gaps.
          </p>
        ) : (
          <ul className="mt-3 flex flex-col gap-3">
            {run.recommendations.map((r) => (
              <RecommendationCard key={r.id} rec={r} />
            ))}
          </ul>
        )}
      </Card>

      {run.skill_outputs.length > 0 ? (
        <Card>
          <CardHeader
            title="Skill outputs"
            subtitle="Raw structured outputs persisted from each skill."
          />
          <ul className="mt-3 flex flex-col gap-3">
            {run.skill_outputs.map((o) => (
              <SkillOutputBlock key={o.id} output={o} />
            ))}
          </ul>
        </Card>
      ) : null}

      <div className="flex justify-between">
        <Link to="/agents" className="text-sm font-medium text-grape-700 hover:text-grape-800">
          ← Back to agents
        </Link>
        <Link to="/recommendations" className="text-sm font-medium text-slate-500 hover:text-ink">
          All recommendations →
        </Link>
      </div>
    </div>
  );
}

function TaskRow({ task }: { task: AgentTaskPublic }) {
  return (
    <li className="flex flex-col gap-1 rounded-xl border border-slate-100 px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-slate-400">#{task.task_index}</span>
          <span className="font-mono text-sm text-ink">{task.skill_name}</span>
        </div>
        <span
          className={cn(
            "pill",
            task.status === "succeeded" && "pill-success",
            task.status === "failed" && "pill-danger",
            task.status === "skipped" && "bg-slate-100 text-slate-600",
            task.status === "running" && "pill-grape",
          )}
        >
          {task.status}
        </span>
      </div>
      {task.error_message ? (
        <p className="text-xs text-red-700">{task.error_message}</p>
      ) : null}
      {task.output_payload ? (
        <details className="text-xs text-slate-500">
          <summary className="cursor-pointer select-none">Output</summary>
          <pre className="mt-1 max-h-48 overflow-auto rounded-lg bg-slate-50 p-2 font-mono">
{JSON.stringify(task.output_payload, null, 2)}
          </pre>
        </details>
      ) : null}
    </li>
  );
}

function RecommendationCard({ rec }: { rec: RecommendationPublic }) {
  return (
    <li className="rounded-xl border border-slate-100 px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="text-sm font-semibold text-ink">{rec.title}</div>
          <p className="mt-1 text-sm text-slate-600">{rec.summary}</p>
          <dl className="mt-3 grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
            <div>
              <dt className="text-slate-400">Expected impact</dt>
              <dd className="text-slate-700">{rec.expected_impact}</dd>
            </div>
            <div>
              <dt className="text-slate-400">Suggested action</dt>
              <dd className="text-slate-700">{rec.suggested_action}</dd>
            </div>
          </dl>
        </div>
        <RiskPill level={rec.risk_level} />
      </div>
    </li>
  );
}

export function RiskPill({ level }: { level: RiskLevel }) {
  return (
    <span
      className={cn(
        "pill",
        level === "high" && "pill-danger",
        level === "medium" && "pill-warning",
        level === "low" && "pill-grape",
      )}
    >
      {level} risk
    </span>
  );
}

function SkillOutputBlock({ output }: { output: SkillOutputPublic }) {
  return (
    <li className="rounded-xl border border-slate-100 px-4 py-3 text-sm">
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs text-slate-500">{output.skill_name}</span>
        <span className="text-xs text-slate-400">{output.output_type}</span>
      </div>
      <pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-slate-50 p-2 font-mono text-xs text-slate-700">
{JSON.stringify(output.payload, null, 2)}
      </pre>
    </li>
  );
}
