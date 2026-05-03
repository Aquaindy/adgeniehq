import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError, apiFetch } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";

type AutopilotMode = "off" | "advisor" | "approval" | "autopilot";

type AutopilotConfig = {
  mode: AutopilotMode;
  max_daily_spend_increase_cents: number | null;
  max_daily_spend_total_cents: number | null;
  max_pct_increase_per_change: number | null;
  min_conversion_threshold: number | null;
  allowed_action_types: string[] | null;
  risk_ceiling: "low" | "medium" | "high";
  stop_loss_active: boolean;
  stop_loss_reason: string | null;
};

type AutopilotPreviewItem = {
  recommendation_id: string;
  recommendation_type: string;
  risk_level: "low" | "medium" | "high";
  allow: boolean;
  reason: string;
  matched_rules: string[];
};


export function AutopilotPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  if (!workspaceId) {
    return <div className="text-sm text-slate-500">Select a workspace first.</div>;
  }
  return <AutopilotPageInner workspaceId={workspaceId} />;
}


function AutopilotPageInner({ workspaceId }: { workspaceId: string }) {
  const queryClient = useQueryClient();

  const config = useQuery<AutopilotConfig>({
    queryKey: ["autopilot", workspaceId],
    queryFn: () => apiFetch(`/workspaces/${workspaceId}/autopilot`),
  });
  const preview = useQuery<AutopilotPreviewItem[]>({
    queryKey: ["autopilot-preview", workspaceId],
    queryFn: () => apiFetch(`/workspaces/${workspaceId}/autopilot/preview`),
  });

  const [draft, setDraft] = useState<AutopilotConfig | null>(null);
  const [savedNote, setSavedNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Hydrate the draft from the server config once it lands.
  useEffect(() => {
    if (config.data && draft === null) {
      setDraft(config.data);
    }
  }, [config.data, draft]);

  const save = useMutation({
    mutationFn: async (patch: Partial<AutopilotConfig>) => {
      return apiFetch<AutopilotConfig>(
        `/workspaces/${workspaceId}/autopilot`,
        { method: "PATCH", body: patch },
      );
    },
    onSuccess: (next) => {
      setDraft(next);
      setSavedNote("Saved.");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["autopilot", workspaceId] });
      void queryClient.invalidateQueries({ queryKey: ["autopilot-preview", workspaceId] });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Could not save.");
      setSavedNote(null);
    },
  });

  function patchDraft(patch: Partial<AutopilotConfig>) {
    setDraft((d) => (d ? { ...d, ...patch } : d));
  }

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!draft) return;
    save.mutate({
      mode: draft.mode,
      max_daily_spend_increase_cents: draft.max_daily_spend_increase_cents,
      max_daily_spend_total_cents: draft.max_daily_spend_total_cents,
      max_pct_increase_per_change: draft.max_pct_increase_per_change,
      min_conversion_threshold: draft.min_conversion_threshold,
      allowed_action_types: draft.allowed_action_types,
      risk_ceiling: draft.risk_ceiling,
    });
  }

  function toggleStopLoss() {
    if (!draft) return;
    save.mutate({
      stop_loss_active: !draft.stop_loss_active,
      stop_loss_reason: draft.stop_loss_active ? null : "Manually toggled by owner.",
    });
  }

  if (config.isLoading || draft === null) {
    return <div className="text-sm text-slate-400">Loading autopilot config…</div>;
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <header>
        <p className="text-xs uppercase tracking-wider text-grape-700">Autopilot</p>
        <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">
          Autopilot mode
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          Off by default. When set to <strong>autopilot</strong>, recommendations
          that match the guardrails below are auto-approved (and audit-logged
          as <code className="text-xs">SYSTEM</code>) without waiting for a
          human. Anything that fails a rule keeps the manual approve/reject
          flow.
        </p>
      </header>

      {error ? (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </div>
      ) : null}
      {savedNote ? (
        <div className="rounded-lg bg-grape-soft px-3 py-2 text-sm text-grape-700">
          {savedNote}
        </div>
      ) : null}

      <Card>
        <CardHeader
          title="Stop-loss"
          subtitle="Emergency switch. While active, autopilot refuses every recommendation regardless of guardrails."
        />
        <div className="mt-3 flex items-start justify-between gap-3">
          <div>
            <span
              className={cn(
                "pill",
                draft.stop_loss_active ? "pill-danger" : "pill-success",
              )}
            >
              {draft.stop_loss_active ? "stop-loss ACTIVE" : "all-clear"}
            </span>
            {draft.stop_loss_active && draft.stop_loss_reason ? (
              <p className="mt-2 text-sm text-slate-500">{draft.stop_loss_reason}</p>
            ) : null}
          </div>
          <Button
            variant={draft.stop_loss_active ? "secondary" : "primary"}
            onClick={toggleStopLoss}
            disabled={save.isPending}
          >
            {draft.stop_loss_active ? "Clear stop-loss" : "Engage stop-loss"}
          </Button>
        </div>
      </Card>

      <Card>
        <CardHeader title="Configuration" subtitle="Owner-only. Saving switches into the new mode atomically." />
        <form className="mt-3 flex flex-col gap-4" onSubmit={onSubmit} noValidate>
          <label className="flex flex-col gap-1.5 text-sm" htmlFor="ap-mode">
            <span className="font-medium text-slate-text">Mode</span>
            <select
              id="ap-mode"
              value={draft.mode}
              onChange={(e) =>
                patchDraft({ mode: e.target.value as AutopilotMode })
              }
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
            >
              <option value="off">off — manual approvals</option>
              <option value="advisor">advisor — recommendations only</option>
              <option value="approval">approval — recs + manual approve flow</option>
              <option value="autopilot">autopilot — auto-approve under guardrails</option>
            </select>
          </label>

          <div className="grid gap-4 sm:grid-cols-2">
            <NumberField
              label="Max daily spend increase (cents)"
              value={draft.max_daily_spend_increase_cents}
              onChange={(v) => patchDraft({ max_daily_spend_increase_cents: v })}
            />
            <NumberField
              label="Max daily spend total (cents)"
              value={draft.max_daily_spend_total_cents}
              onChange={(v) => patchDraft({ max_daily_spend_total_cents: v })}
            />
            <NumberField
              label="Max % increase per change"
              value={draft.max_pct_increase_per_change}
              onChange={(v) => patchDraft({ max_pct_increase_per_change: v })}
            />
            <NumberField
              label="Min recent conversions for spend-up"
              value={draft.min_conversion_threshold}
              onChange={(v) => patchDraft({ min_conversion_threshold: v })}
            />
          </div>

          <label className="flex flex-col gap-1.5 text-sm" htmlFor="ap-risk">
            <span className="font-medium text-slate-text">Risk ceiling</span>
            <select
              id="ap-risk"
              value={draft.risk_ceiling}
              onChange={(e) =>
                patchDraft({
                  risk_ceiling: e.target.value as AutopilotConfig["risk_ceiling"],
                })
              }
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
            >
              <option value="low">low (safest)</option>
              <option value="medium">medium</option>
              <option value="high">high (auto-approve high-risk recs — careful)</option>
            </select>
          </label>

          <label className="flex flex-col gap-1.5 text-sm" htmlFor="ap-actions">
            <span className="font-medium text-slate-text">Allowed action types</span>
            <textarea
              id="ap-actions"
              rows={3}
              value={(draft.allowed_action_types ?? []).join("\n")}
              onChange={(e) =>
                patchDraft({
                  allowed_action_types: e.target.value
                    .split(/[\n,]/)
                    .map((s) => s.trim())
                    .filter(Boolean),
                })
              }
              placeholder={"paid_ads.budget_unset\npaid_ads.scale_up"}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 font-mono text-xs text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
            />
            <span className="text-xs text-slate-400">
              One recommendation_type per line. Empty list means autopilot won't
              auto-approve anything.
            </span>
          </label>

          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save configuration"}
          </Button>
        </form>
      </Card>

      <Card>
        <CardHeader
          title="Preview"
          subtitle="What autopilot would do right now for every OPEN recommendation. Saving the config refreshes this list."
        />
        {preview.isLoading ? (
          <p className="mt-3 text-sm text-slate-400">Loading preview…</p>
        ) : (preview.data ?? []).length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">
            No open recommendations to preview.
          </p>
        ) : (
          <ul className="mt-3 flex flex-col divide-y divide-slate-100 text-sm">
            {(preview.data ?? []).map((p) => (
              <li
                key={p.recommendation_id}
                className="flex items-start justify-between gap-3 py-2"
              >
                <div className="min-w-0 flex-1">
                  <div className="font-mono text-xs text-grape-700">
                    {p.recommendation_type}
                  </div>
                  <div className="text-xs text-slate-500">
                    risk: {p.risk_level} · {p.reason}
                  </div>
                </div>
                <span
                  className={cn(
                    "pill shrink-0",
                    p.allow ? "pill-success" : "bg-slate-100 text-slate-600",
                  )}
                >
                  {p.allow ? "would auto-approve" : "manual"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}


function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
}) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      <span className="font-medium text-slate-text">{label}</span>
      <input
        type="number"
        min={0}
        value={value ?? ""}
        onChange={(e) => {
          const raw = e.target.value;
          onChange(raw === "" ? null : Number(raw));
        }}
        className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
      />
    </label>
  );
}
