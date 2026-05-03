import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError } from "@/lib/api-client";
import {
  auditLandingPage,
  createLandingPage,
  deleteLandingPage,
  importFromOnboarding,
  listLandingPages,
} from "@/lib/landing-pages";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { LandingPagePublic } from "@/types/api";


const SKILL_LABELS: Record<string, string> = {
  "conversion.above_fold": "Above-the-fold value prop",
  "conversion.cta_analysis": "Primary CTA",
  "conversion.trust_signals": "Trust signals",
  "conversion.form_friction": "Form friction",
  "conversion.copy_clarity": "Copy clarity",
  "conversion.viewport": "Mobile viewport",
};


export function WebsitePage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();

  const pages = useQuery({
    queryKey: ["landing-pages", workspaceId],
    queryFn: () => listLandingPages(workspaceId!),
    enabled: !!workspaceId,
  });

  const [url, setUrl] = useState("");
  const [label, setLabel] = useState("");
  const [error, setError] = useState<string | null>(null);

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["landing-pages", workspaceId] });
    queryClient.invalidateQueries({ queryKey: ["recommendations", workspaceId] });
    queryClient.invalidateQueries({ queryKey: ["agents", "runs", workspaceId] });
  }

  const create = useMutation({
    mutationFn: () =>
      createLandingPage(workspaceId!, {
        url: url.trim(),
        label: label.trim() || undefined,
      }),
    onSuccess: () => {
      setUrl("");
      setLabel("");
      setError(null);
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not add."),
  });

  const importMut = useMutation({
    mutationFn: () => importFromOnboarding(workspaceId!),
    onSuccess: () => invalidate(),
    onError: (err) => setError(err instanceof ApiError ? err.message : "Import failed."),
  });

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!url.trim()) return;
    setError(null);
    create.mutate();
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-grape-700">Website Intelligence</p>
          <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">
            Landing-page conversion audits
          </h1>
          <p className="mt-2 text-sm text-slate-500">
            Each audit fetches the page, scores hero copy / CTA / trust / form friction / copy
            clarity / mobile viewport, and runs a real PageSpeed Insights query for mobile
            performance.
          </p>
        </div>
        <Button
          variant="secondary"
          onClick={() => importMut.mutate()}
          disabled={importMut.isPending}
        >
          {importMut.isPending ? "Importing…" : "Import from onboarding"}
        </Button>
      </header>

      {error ? (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </div>
      ) : null}

      <Card>
        <CardHeader title="Add a landing page" subtitle="One URL per row." />
        <form className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={onSubmit}>
          <Field
            id="url"
            label="URL"
            type="url"
            placeholder="https://acme.example/pricing"
            value={url}
            onChange={setUrl}
            required
          />
          <Field
            id="label"
            label="Label (optional)"
            placeholder="Pricing"
            value={label}
            onChange={setLabel}
          />
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? "Adding…" : "Add"}
          </Button>
        </form>
      </Card>

      {pages.isLoading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : pages.data && pages.data.length > 0 ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {pages.data.map((lp) => (
            <LandingPageCard key={lp.id} page={lp} onChanged={invalidate} />
          ))}
        </div>
      ) : (
        <EmptyState
          title="No landing pages tracked yet"
          description="Add one above, or import the URLs you listed during onboarding."
        />
      )}
    </div>
  );
}

function LandingPageCard({
  page,
  onChanged,
}: {
  page: LandingPagePublic;
  onChanged: () => void;
}) {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const [error, setError] = useState<string | null>(null);

  const audit = useMutation({
    mutationFn: () => auditLandingPage(workspaceId!, page.id),
    onSuccess: () => {
      setError(null);
      onChanged();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Audit failed."),
  });

  const remove = useMutation({
    mutationFn: () => deleteLandingPage(workspaceId!, page.id),
    onSuccess: () => onChanged(),
    onError: (err) => setError(err instanceof ApiError ? err.message : "Delete failed."),
  });

  const summary = page.last_audit_summary;

  return (
    <Card>
      <CardHeader
        title={page.label ?? new URL(page.url).pathname}
        subtitle={
          <a
            href={page.url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-mono text-xs text-grape-700 hover:text-grape-800"
          >
            {page.url} ↗
          </a>
        }
        action={
          <span
            className={cn(
              "pill",
              page.source === "onboarding" ? "bg-grape-100 text-grape-700" : "bg-slate-100 text-slate-600",
            )}
          >
            {page.source}
          </span>
        }
      />

      <div className="mt-4 grid grid-cols-3 gap-3">
        <ScoreTile label="Conversion" value={summary?.scores?.conversion ?? null} />
        <ScoreTile label="Mobile UX" value={summary?.scores?.mobile_ux ?? null} />
        <ScoreTile label="Page speed" value={summary?.scores?.page_speed ?? null} />
      </div>

      {summary ? (
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer select-none font-medium text-slate-text">
            Skill breakdown
          </summary>
          <ul className="mt-2 flex flex-col gap-1.5 text-xs text-slate-600">
            {Object.entries(summary.skills ?? {}).map(([skill, entry]) => (
              <li key={skill} className="flex items-center justify-between gap-2 rounded-lg border border-slate-100 px-3 py-1.5">
                <span>{SKILL_LABELS[skill] ?? skill}</span>
                <span className="flex items-center gap-2">
                  {entry.severity ? <SeverityPill severity={entry.severity} /> : null}
                  <span className="font-mono text-slate-700">{entry.score ?? "—"}</span>
                </span>
              </li>
            ))}
          </ul>
        </details>
      ) : (
        <p className="mt-3 text-sm text-slate-500">
          No audit yet. Click <span className="font-medium text-grape-700">Run audit</span> to
          generate scores and recommendations.
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs text-slate-400">
          {page.last_audited_at
            ? `Last audited ${new Date(page.last_audited_at).toLocaleString()}`
            : "Never audited"}
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => audit.mutate()} disabled={audit.isPending}>
            {audit.isPending ? "Auditing…" : "Run audit"}
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              if (confirm(`Remove ${page.url} from tracking?`)) {
                remove.mutate();
              }
            }}
            disabled={remove.isPending}
          >
            Remove
          </Button>
        </div>
      </div>

      {error ? <p className="mt-2 text-xs text-red-700">{error}</p> : null}

      {audit.data ? (
        <div className="mt-3 text-xs">
          <Link
            to={`/agents/runs/${audit.data.id}`}
            className="font-medium text-grape-700 hover:text-grape-800"
          >
            View latest agent run →
          </Link>
        </div>
      ) : null}
    </Card>
  );
}

function ScoreTile({ label, value }: { label: string; value: number | null }) {
  const tone =
    value === null
      ? "text-slate-400"
      : value >= 80
        ? "text-success"
        : value >= 50
          ? "text-grape-700"
          : "text-warning";
  const barTone =
    value === null
      ? "bg-slate-200"
      : value >= 80
        ? "bg-success"
        : value >= 50
          ? "bg-grape"
          : "bg-warning";
  return (
    <div className="rounded-xl border border-slate-100 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wider text-slate-400">{label}</div>
      <div className={cn("mt-0.5 text-2xl font-semibold tracking-tight", tone)}>
        {value === null ? "—" : value}
      </div>
      <div className="mt-1 h-1 overflow-hidden rounded-full bg-slate-100">
        {value !== null ? (
          <div
            className={cn("h-full rounded-full transition-all", barTone)}
            style={{ width: `${Math.max(2, Math.min(100, value))}%` }}
          />
        ) : null}
      </div>
    </div>
  );
}

function SeverityPill({ severity }: { severity: "ok" | "low" | "medium" | "high" }) {
  return (
    <span
      className={cn(
        "pill",
        severity === "ok" && "pill-success",
        severity === "low" && "pill-grape",
        severity === "medium" && "pill-warning",
        severity === "high" && "pill-danger",
      )}
    >
      {severity}
    </span>
  );
}

function Field({
  id,
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  required,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
  required?: boolean;
}) {
  return (
    <label className="flex flex-1 flex-col gap-1.5 text-sm" htmlFor={id}>
      <span className="font-medium text-slate-text">{label}</span>
      <input
        id={id}
        type={type}
        value={value}
        placeholder={placeholder}
        required={required}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
      />
    </label>
  );
}
