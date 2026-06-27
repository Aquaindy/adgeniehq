import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import {
  archiveAbTest,
  declareWinner,
  getAbTest,
  launchAbTest,
  recordVariantMetrics,
} from "@/lib/ab-tests";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type {
  AbTestPublic,
  AbTestStatus,
  AbTestVariantPublic,
} from "@/types/api";

const STATUS_PILL: Record<AbTestStatus, string> = {
  draft: "bg-slate-100 text-slate-600",
  ready: "bg-amber-100 text-amber-700",
  launched: "pill-grape",
  paused: "bg-slate-100 text-slate-500",
  completed: "pill-success",
  archived: "bg-slate-100 text-slate-400",
};

export function AbTestDetailPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const { testId } = useParams<{ testId: string }>();

  const test = useQuery({
    queryKey: ["ab-test", workspaceId, testId],
    queryFn: () => getAbTest(workspaceId!, testId!),
    enabled: !!workspaceId && !!testId,
  });

  if (test.isLoading) return <div className="text-sm text-slate-400">Loading…</div>;
  if (test.error) {
    return (
      <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
        {test.error instanceof Error ? test.error.message : "Could not load."}
      </div>
    );
  }
  if (!test.data) return null;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <Header test={test.data} />
      <Variants test={test.data} />
      {test.data.target === "landing_page" && test.data.status === "launched" ? (
        <InstallSnippetCard test={test.data} />
      ) : null}
      <ActionsCard test={test.data} />

      <div className="text-sm">
        <Link
          to="/ab-tests"
          className="font-medium text-grape-700 hover:text-grape-800"
        >
          ← All tests
        </Link>
      </div>
    </div>
  );
}

function InstallSnippetCard({ test }: { test: AbTestPublic }) {
  const apiBase =
    typeof window !== "undefined"
      ? window.location.origin.replace(/:5173$/, ":8000")
      : "https://api.adgeniehq.com";
  const redirectSnippet = `<script\n  src="${apiBase}/static/adgeniehq-ab.js"\n  data-test="${test.id}"\n  data-mode="redirect"\n></script>`;
  const inplaceSnippet = `<script\n  src="${apiBase}/static/adgeniehq-ab.js"\n  data-test="${test.id}"\n></script>\n\n<!-- Wrap each variant: -->\n<div data-adgeniehq-variant="control" style="display:none">…</div>\n<div data-adgeniehq-variant="treatment" style="display:none">…</div>`;
  const convertSnippet = `// Fire on form submit / purchase / signup\nwindow.adgeniehqConvert("${test.id}", { value_cents: 4900 });`;

  return (
    <Card>
      <CardHeader
        title="Install on your site"
        subtitle="Drop the snippet into your landing page. Visitors get a sticky variant on first load; conversions are recorded against the variant they saw."
      />
      <div className="mt-3 flex flex-col gap-3 text-xs">
        <SnippetBlock label="Redirect mode (each variant has its own URL)" code={redirectSnippet} />
        <SnippetBlock label="In-place mode (swap copy on a single URL)" code={inplaceSnippet} />
        <SnippetBlock label="Track a conversion" code={convertSnippet} />
      </div>
    </Card>
  );
}

function SnippetBlock({ label, code }: { label: string; code: string }) {
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        {label}
      </p>
      <pre className="mt-1 max-h-48 overflow-auto rounded-lg bg-slate-50 p-3 font-mono text-xs text-slate-700">
{code}
      </pre>
    </div>
  );
}

function Header({ test }: { test: AbTestPublic }) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p className="text-xs uppercase tracking-wider text-grape-700">
          {test.target === "ad" ? "Ad test" : "Landing-page test"}
        </p>
        <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">
          {test.name}
        </h1>
        <p className="mt-1 text-xs text-slate-400">
          {test.objective}
          {test.provider ? ` · ${test.provider}` : ""}
          {test.started_at
            ? ` · started ${new Date(test.started_at).toLocaleString()}`
            : ""}
        </p>
        {test.hypothesis ? (
          <p className="mt-2 text-sm text-slate-600">{test.hypothesis}</p>
        ) : null}
      </div>
      <span className={cn("pill", STATUS_PILL[test.status])}>{test.status}</span>
    </header>
  );
}

function Variants({ test }: { test: AbTestPublic }) {
  return (
    <Card>
      <CardHeader title="Variants" subtitle="Record outcome metrics as you collect them; then declare a winner." />
      <ul className="mt-3 flex flex-col gap-3">
        {test.variants.map((v) => (
          <VariantRow key={v.id} test={test} variant={v} />
        ))}
      </ul>
    </Card>
  );
}

function VariantRow({
  test,
  variant,
}: {
  test: AbTestPublic;
  variant: AbTestVariantPublic;
}) {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [visits, setVisits] = useState(
    String((variant.metrics?.visits as number | undefined) ?? ""),
  );
  const [conversions, setConversions] = useState(
    String((variant.metrics?.conversions as number | undefined) ?? ""),
  );
  const [error, setError] = useState<string | null>(null);

  const isWinner = test.winner_variant_id === variant.id;

  const recordMut = useMutation({
    mutationFn: () =>
      recordVariantMetrics(workspaceId!, test.id, variant.id, {
        visits: visits ? Number(visits) : undefined,
        conversions: conversions ? Number(conversions) : undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ab-test", workspaceId, test.id] });
      setOpen(false);
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not save."),
  });

  const winnerMut = useMutation({
    mutationFn: () => declareWinner(workspaceId!, test.id, variant.id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["ab-test", workspaceId, test.id] }),
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not declare winner."),
  });

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    recordMut.mutate();
  }

  const conversionRate =
    typeof variant.metrics?.visits === "number" &&
    typeof variant.metrics?.conversions === "number" &&
    (variant.metrics.visits as number) > 0
      ? (((variant.metrics.conversions as number) /
          (variant.metrics.visits as number)) *
          100
        ).toFixed(2)
      : null;

  return (
    <li
      className={cn(
        "rounded-xl border px-4 py-3",
        isWinner
          ? "border-grape-300 bg-grape-50"
          : "border-slate-100",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-ink">{variant.name}</span>
          {variant.is_control ? (
            <span className="pill bg-slate-100 text-slate-500">control</span>
          ) : null}
          {isWinner ? (
            <span className="pill pill-grape">winner</span>
          ) : null}
          <span className="pill bg-slate-50 text-slate-500">
            traffic {Math.round(variant.traffic_share * 100)}%
          </span>
        </div>
        <div className="flex items-center gap-2">
          {test.status === "launched" || test.status === "completed" ? (
            <Button variant="secondary" onClick={() => setOpen((v) => !v)}>
              {open ? "Cancel" : "Record metrics"}
            </Button>
          ) : null}
          {test.status === "launched" && !test.winner_variant_id ? (
            <Button
              variant="ghost"
              onClick={() => winnerMut.mutate()}
              disabled={winnerMut.isPending}
            >
              {winnerMut.isPending ? "Declaring…" : "Declare winner"}
            </Button>
          ) : null}
        </div>
      </div>

      <dl className="mt-2 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
        <Stat label="Visits" value={(variant.metrics?.visits as number | undefined) ?? "—"} />
        <Stat
          label="Conversions"
          value={(variant.metrics?.conversions as number | undefined) ?? "—"}
        />
        <Stat label="Conversion rate" value={conversionRate ? `${conversionRate}%` : "—"} />
        <Stat label="Provider id" value={variant.external_id ?? "—"} />
      </dl>

      {variant.payload && Object.keys(variant.payload).length ? (
        <details className="mt-2 text-xs text-slate-500">
          <summary className="cursor-pointer select-none">Payload</summary>
          <pre className="mt-1 max-h-32 overflow-auto rounded-lg bg-slate-50 p-2 font-mono">
{JSON.stringify(variant.payload, null, 2)}
          </pre>
        </details>
      ) : null}

      {error ? (
        <p className="mt-2 text-xs text-red-700">{error}</p>
      ) : null}

      {open ? (
        <form className="mt-3 flex flex-wrap items-end gap-2 text-sm" onSubmit={onSubmit}>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-slate-text">Visits</span>
            <input
              type="number"
              min={0}
              value={visits}
              onChange={(e) => setVisits(e.target.value)}
              className="w-32 rounded-xl border border-slate-200 bg-surface px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-slate-text">Conversions</span>
            <input
              type="number"
              min={0}
              value={conversions}
              onChange={(e) => setConversions(e.target.value)}
              className="w-32 rounded-xl border border-slate-200 bg-surface px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
            />
          </label>
          <Button type="submit" disabled={recordMut.isPending}>
            {recordMut.isPending ? "Saving…" : "Save"}
          </Button>
        </form>
      ) : null}
    </li>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-slate-700">{value}</dd>
    </div>
  );
}

function ActionsCard({ test }: { test: AbTestPublic }) {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["ab-test", workspaceId, test.id] });
    queryClient.invalidateQueries({ queryKey: ["ab-tests", workspaceId] });
  }

  const launch = useMutation({
    mutationFn: () => launchAbTest(workspaceId!, test.id),
    onSuccess: invalidate,
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not launch."),
  });
  const archive = useMutation({
    mutationFn: () => archiveAbTest(workspaceId!, test.id),
    onSuccess: invalidate,
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not archive."),
  });

  return (
    <Card>
      <CardHeader title="Actions" />
      {error ? (
        <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {test.status === "ready" || test.status === "paused" ? (
          <Button onClick={() => launch.mutate()} disabled={launch.isPending}>
            {launch.isPending ? "Launching…" : "Launch"}
          </Button>
        ) : null}
        {test.status !== "archived" ? (
          <Button
            variant="ghost"
            onClick={() => archive.mutate()}
            disabled={archive.isPending}
          >
            {archive.isPending ? "Archiving…" : "Archive"}
          </Button>
        ) : null}
      </div>
      {test.target === "ad" ? (
        <p className="mt-3 text-xs text-slate-500">
          Ad-target tests launch each variant as a paused campaign on the
          provider. Switch them to active in the provider's UI (or via an
          approve-then-execute recommendation) when you're ready to spend.
        </p>
      ) : null}
    </Card>
  );
}
