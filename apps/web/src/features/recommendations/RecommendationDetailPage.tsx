import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import {
  getRecommendation,
  listRecommendationAuditLogs,
  updateRecommendation,
} from "@/lib/agents";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { AuditLogPublic, RecommendationPublic, RiskLevel } from "@/types/api";

import { ApprovalActions } from "@/features/recommendations/ApprovalActions";
import { ExecutionsPanel } from "@/features/recommendations/ExecutionsPanel";

export function RecommendationDetailPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const { recommendationId } = useParams<{ recommendationId: string }>();

  const rec = useQuery({
    queryKey: ["recommendation", workspaceId, recommendationId],
    queryFn: () => getRecommendation(workspaceId!, recommendationId!),
    enabled: !!workspaceId && !!recommendationId,
  });

  const auditLog = useQuery({
    queryKey: ["audit-log", workspaceId, recommendationId],
    queryFn: () => listRecommendationAuditLogs(workspaceId!, recommendationId!),
    enabled: !!workspaceId && !!recommendationId,
  });

  if (rec.isLoading) return <div className="text-sm text-slate-400">Loading…</div>;

  if (rec.error) {
    const code = rec.error instanceof ApiError ? rec.error.code : null;
    return (
      <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
        {code === "recommendation_not_found"
          ? "Recommendation not found in this workspace."
          : rec.error instanceof Error
            ? rec.error.message
            : "Could not load."}
      </div>
    );
  }

  if (!rec.data) return null;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <header className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-grape-700">Recommendation</p>
          <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">{rec.data.title}</h1>
          <p className="mt-1 text-xs text-slate-400">
            From{" "}
            <Link
              to={`/agents/runs/${rec.data.agent_run_id}`}
              className="font-medium text-grape-700 hover:text-grape-800"
            >
              agent run
            </Link>{" "}
            · created {new Date(rec.data.created_at).toLocaleString()}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <RiskPillBadge level={rec.data.risk_level} />
          <ApprovalActions rec={rec.data} />
        </div>
      </header>

      <Card>
        <CardHeader title="Summary" />
        <p className="mt-3 whitespace-pre-wrap text-sm text-slate-700">{rec.data.summary}</p>

        <dl className="mt-4 grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-slate-400">Expected impact</dt>
            <dd className="mt-1 whitespace-pre-wrap text-slate-700">{rec.data.expected_impact}</dd>
          </div>
          <div>
            <dt className="text-slate-400">Suggested action</dt>
            <dd className="mt-1 whitespace-pre-wrap text-slate-700">{rec.data.suggested_action}</dd>
          </div>
        </dl>
      </Card>

      <EditCard rec={rec.data} />

      <ExecutionsPanel rec={rec.data} />

      <Card>
        <CardHeader title="Audit log" subtitle="Every approve/reject/edit action on this recommendation." />
        <AuditLogList entries={auditLog.data ?? []} loading={auditLog.isLoading} />
      </Card>

      <div className="flex justify-between">
        <Link to="/recommendations" className="text-sm font-medium text-grape-700 hover:text-grape-800">
          ← All recommendations
        </Link>
      </div>
    </div>
  );
}

function RiskPillBadge({ level }: { level: RiskLevel }) {
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

function EditCard({ rec }: { rec: RecommendationPublic }) {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();

  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(rec.title);
  const [summary, setSummary] = useState(rec.summary);
  const [impact, setImpact] = useState(rec.expected_impact);
  const [action, setAction] = useState(rec.suggested_action);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTitle(rec.title);
    setSummary(rec.summary);
    setImpact(rec.expected_impact);
    setAction(rec.suggested_action);
  }, [rec.title, rec.summary, rec.expected_impact, rec.suggested_action]);

  const mut = useMutation({
    mutationFn: () =>
      updateRecommendation(workspaceId!, rec.id, {
        title,
        summary,
        expected_impact: impact,
        suggested_action: action,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recommendation", workspaceId, rec.id] });
      queryClient.invalidateQueries({ queryKey: ["recommendations", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["audit-log", workspaceId, rec.id] });
      setOpen(false);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not save."),
  });

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    mut.mutate();
  }

  if (!open) {
    return (
      <Card>
        <CardHeader
          title="Edit before applying"
          subtitle="Tighten the title, summary, expected impact, or suggested action."
          action={
            <Button variant="secondary" onClick={() => setOpen(true)}>
              Edit
            </Button>
          }
        />
        <p className="mt-3 text-xs text-slate-500">
          Editing requires the Admin role or higher. Risk level and recommendation type are immutable.
        </p>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader title="Edit recommendation" />
      <form className="mt-4 flex flex-col gap-3 text-sm" onSubmit={onSubmit}>
        <Field label="Title" value={title} onChange={setTitle} />
        <Field label="Summary" value={summary} onChange={setSummary} multiline rows={3} />
        <Field label="Expected impact" value={impact} onChange={setImpact} multiline rows={3} />
        <Field label="Suggested action" value={action} onChange={setAction} multiline rows={3} />
        {error ? (
          <div className="rounded-lg bg-red-50 px-3 py-2 text-red-700">{error}</div>
        ) : null}
        <div className="flex items-center gap-2">
          <Button type="submit" disabled={mut.isPending}>
            {mut.isPending ? "Saving…" : "Save changes"}
          </Button>
          <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}

function Field({
  label,
  value,
  onChange,
  multiline,
  rows = 3,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  multiline?: boolean;
  rows?: number;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="font-medium text-slate-text">{label}</span>
      {multiline ? (
        <textarea
          rows={rows}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
        />
      ) : (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
        />
      )}
    </label>
  );
}

function AuditLogList({
  entries,
  loading,
}: {
  entries: AuditLogPublic[];
  loading: boolean;
}) {
  if (loading) return <p className="mt-3 text-sm text-slate-400">Loading…</p>;
  if (entries.length === 0) {
    return <p className="mt-3 text-sm text-slate-500">No actions taken on this recommendation yet.</p>;
  }
  return (
    <ol className="mt-3 flex flex-col gap-2 text-sm">
      {entries.map((entry) => (
        <li
          key={entry.id}
          className="flex flex-col gap-1 rounded-xl border border-slate-100 px-4 py-3"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-mono text-xs text-grape-700">{entry.action}</span>
            <span className="text-xs text-slate-400">
              {new Date(entry.created_at).toLocaleString()}
            </span>
          </div>
          <div className="text-xs text-slate-500">
            actor {entry.actor_type}
            {entry.ip_address ? ` · ${entry.ip_address}` : ""}
            {entry.user_agent ? ` · ${entry.user_agent.slice(0, 80)}` : ""}
          </div>
          {entry.metadata ? (
            <details className="text-xs text-slate-500">
              <summary className="cursor-pointer select-none">Metadata</summary>
              <pre className="mt-1 max-h-40 overflow-auto rounded-lg bg-slate-50 p-2 font-mono">
{JSON.stringify(entry.metadata, null, 2)}
              </pre>
            </details>
          ) : null}
        </li>
      ))}
    </ol>
  );
}
