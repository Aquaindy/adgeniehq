import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError } from "@/lib/api-client";
import { fetchReportBlob, generateReport, listReports } from "@/lib/reports";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { ReportPeriod, ReportSummaryRow } from "@/types/api";


const PERIODS: { value: ReportPeriod; label: string; window: string }[] = [
  { value: "daily", label: "Daily", window: "Last 24 hours" },
  { value: "weekly", label: "Weekly", window: "Last 7 days" },
  { value: "monthly", label: "Monthly", window: "Last 30 days" },
];


export function ReportsPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [activePeriod, setActivePeriod] = useState<ReportPeriod | null>(null);

  const reports = useQuery({
    queryKey: ["reports", workspaceId],
    queryFn: () => listReports(workspaceId!),
    enabled: !!workspaceId,
  });

  const generate = useMutation({
    mutationFn: (period: ReportPeriod) => {
      setActivePeriod(period);
      return generateReport(workspaceId!, { period });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reports", workspaceId] });
      setError(null);
      setActivePeriod(null);
    },
    onError: (err) => {
      setActivePeriod(null);
      setError(err instanceof ApiError ? err.message : "Could not generate report.");
    },
  });

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <header>
        <p className="text-xs uppercase tracking-wider text-grape-700">Reports</p>
        <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">
          Snapshot what your AI growth team did
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          Reports roll up real workspace data — agent runs, recommendations, campaigns, SEO, and
          landing-page audits — over the chosen window. Empty sections mean no data exists yet.
        </p>
      </header>

      {error ? (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </div>
      ) : null}

      <Card>
        <CardHeader title="Generate a new report" />
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          {PERIODS.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => generate.mutate(p.value)}
              disabled={generate.isPending}
              className={cn(
                "flex flex-col items-start gap-1 rounded-2xl border border-slate-200 bg-surface px-4 py-3 text-left transition hover:border-grape hover:bg-grape-50",
                generate.isPending && activePeriod === p.value && "opacity-60",
              )}
            >
              <span className="text-xs uppercase tracking-wider text-slate-400">
                {p.window}
              </span>
              <span className="text-base font-semibold text-ink">{p.label}</span>
              {generate.isPending && activePeriod === p.value ? (
                <span className="text-xs text-grape-700">Generating…</span>
              ) : (
                <span className="text-xs text-slate-500">Click to generate</span>
              )}
            </button>
          ))}
        </div>
      </Card>

      <Card>
        <CardHeader title="Generated reports" subtitle="Newest first." />
        {reports.isLoading ? (
          <p className="mt-3 text-sm text-slate-400">Loading…</p>
        ) : reports.data && reports.data.length > 0 ? (
          <ul className="mt-3 flex flex-col divide-y divide-slate-100">
            {reports.data.map((r) => (
              <ReportRow key={r.id} report={r} />
            ))}
          </ul>
        ) : (
          <div className="mt-2">
            <EmptyState
              title="No reports yet"
              description="Generate your first report above. It pulls only data your workspace already has."
            />
          </div>
        )}
      </Card>
    </div>
  );
}


function ReportRow({ report }: { report: ReportSummaryRow }) {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const [busy, setBusy] = useState<"pdf" | "csv" | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  async function download(format: "pdf" | "csv") {
    if (!workspaceId) return;
    setBusy(format);
    setDownloadError(null);
    try {
      const blob = await fetchReportBlob(workspaceId, report.id, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${report.title.replace(/[^a-z0-9_-]+/gi, "_")}.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setDownloadError(`Could not download the ${format.toUpperCase()}. Please try again.`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="flex-1 min-w-0">
        <Link
          to={`/reports/${report.id}`}
          className="block truncate text-sm font-semibold text-ink hover:text-grape-700"
        >
          {report.title}
        </Link>
        <div className="text-xs text-slate-500">
          {new Date(report.period_start).toLocaleDateString()} →{" "}
          {new Date(report.period_end).toLocaleDateString()} · generated{" "}
          {new Date(report.created_at).toLocaleString()}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "pill",
            report.status === "ready" && "pill-success",
            report.status === "failed" && "pill-danger",
            report.status === "generating" && "pill-grape",
          )}
        >
          {report.status}
        </span>
        <Button
          variant="secondary"
          onClick={() => download("pdf")}
          disabled={busy !== null || report.status !== "ready"}
        >
          {busy === "pdf" ? "Downloading…" : "PDF"}
        </Button>
        <Button
          variant="ghost"
          onClick={() => download("csv")}
          disabled={busy !== null || report.status !== "ready"}
        >
          {busy === "csv" ? "Downloading…" : "CSV"}
        </Button>
      </div>
      {downloadError ? (
        <p className="w-full text-right text-xs text-red-600" role="alert">
          {downloadError}
        </p>
      ) : null}
    </li>
  );
}
