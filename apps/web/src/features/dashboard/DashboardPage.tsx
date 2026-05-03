import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError, apiFetch } from "@/lib/api-client";
import { getGrowthDna, getOnboarding } from "@/lib/onboarding";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { GrowthDna, OnboardingProfile } from "@/types/api";

type HealthResponse = {
  status: "ok" | "error";
  app: string;
  env: string;
  version: string;
};

type ComponentHealth = {
  component: string;
  status: "ok" | "error";
  detail?: string | null;
};

function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => apiFetch<HealthResponse>("/health"),
    refetchInterval: 30_000,
    retry: 1,
  });
}

function useComponentHealth(component: "db" | "redis") {
  return useQuery({
    queryKey: ["health", component],
    queryFn: () => apiFetch<ComponentHealth>(`/health/${component}`),
    refetchInterval: 30_000,
    retry: 1,
  });
}

function StatusPill({
  loading,
  error,
  status,
}: {
  loading: boolean;
  error: unknown;
  status?: "ok" | "error";
}) {
  if (loading) return <span className="pill bg-slate-100 text-slate-600">Checking…</span>;
  if (error) {
    const message = error instanceof ApiError ? error.message : "Unreachable";
    return <span className="pill pill-danger" title={message}>Unreachable</span>;
  }
  if (status === "ok") return <span className="pill pill-success">Healthy</span>;
  return <span className="pill pill-warning">Degraded</span>;
}

export function DashboardPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const app = useHealth();
  const db = useComponentHealth("db");
  const redis = useComponentHealth("redis");

  const onboarding = useQuery({
    queryKey: ["onboarding", workspaceId],
    queryFn: () => getOnboarding(workspaceId!),
    enabled: !!workspaceId,
  });

  const dna = useQuery({
    queryKey: ["growth-dna", workspaceId],
    queryFn: () => getGrowthDna(workspaceId!),
    enabled: !!workspaceId,
    retry: false,
  });

  const dnaMissing =
    dna.error instanceof ApiError && dna.error.code === "growth_dna_not_found";

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <section>
        <p className="text-xs uppercase tracking-wider text-grape-700">Command Center</p>
        <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">
          Your AI Growth Operating System
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-500 sm:text-base">
          Connect your real ad accounts, analytics, and website. Specialized AI Skill Agents will
          analyze performance, surface waste, and propose your next best growth moves — under
          approval.
        </p>
      </section>

      <OnboardingGate onboarding={onboarding.data} dna={dna.data} dnaMissing={dnaMissing} />

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader
            title="API"
            subtitle="FastAPI service heartbeat"
            action={
              <StatusPill
                loading={app.isLoading}
                error={app.error}
                status={app.data?.status}
              />
            }
          />
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-slate-400">App</dt>
              <dd className="font-medium text-ink">{app.data?.app ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-slate-400">Env</dt>
              <dd className="font-medium text-ink">{app.data?.env ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-slate-400">Version</dt>
              <dd className="font-medium text-ink">{app.data?.version ?? "—"}</dd>
            </div>
          </dl>
        </Card>

        <Card>
          <CardHeader
            title="PostgreSQL"
            subtitle="Primary datastore"
            action={
              <StatusPill loading={db.isLoading} error={db.error} status={db.data?.status} />
            }
          />
          <p className="mt-4 text-sm text-slate-500">
            Stores users, workspaces, onboarding answers, and Growth DNA Profiles.
          </p>
        </Card>

        <Card>
          <CardHeader
            title="Redis"
            subtitle="Cache + Celery broker"
            action={
              <StatusPill loading={redis.isLoading} error={redis.error} status={redis.data?.status} />
            }
          />
          <p className="mt-4 text-sm text-slate-500">
            Used later for background agent jobs, sync queues, and rate limiting.
          </p>
        </Card>
      </section>
    </div>
  );
}

function OnboardingGate({
  onboarding,
  dna,
  dnaMissing,
}: {
  onboarding: OnboardingProfile | undefined;
  dna: GrowthDna | undefined;
  dnaMissing: boolean;
}) {
  const completed = !!onboarding?.completed_at;

  if (!completed) {
    const stepsLeft = Math.max(0, 5 - (onboarding?.step_completed ?? 0));
    return (
      <Card className="border-grape-200 bg-grape-soft/60">
        <CardHeader
          title="Complete onboarding to activate your Growth DNA"
          subtitle={
            stepsLeft === 5
              ? "Five short steps. Takes about three minutes."
              : `${stepsLeft} step${stepsLeft === 1 ? "" : "s"} remaining.`
          }
          action={
            <Link to="/onboarding">
              <Button>{stepsLeft === 5 ? "Start onboarding" : "Resume"}</Button>
            </Link>
          }
        />
      </Card>
    );
  }

  if (dnaMissing) {
    return (
      <Card className="border-grape-200 bg-grape-soft/60">
        <CardHeader
          title="Onboarding complete — generate your Growth DNA"
          subtitle="Readiness scores, recommended first campaigns, and your 30-day plan."
          action={
            <Link to="/onboarding">
              <Button>Generate Growth DNA</Button>
            </Link>
          }
        />
      </Card>
    );
  }

  if (!dna) return null;

  return (
    <Card>
      <CardHeader
        title="Growth DNA snapshot"
        subtitle={`Derived from your inputs · engine ${dna.engine_version}`}
        action={
          <Link to="/growth-dna" className="text-sm font-medium text-grape-700 hover:text-grape-800">
            View full profile →
          </Link>
        }
      />
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <ScorePreview label="Funnel readiness" value={dna.funnel_readiness_score} />
        <ScorePreview label="Paid ads readiness" value={dna.paid_ads_readiness_score} />
      </div>
    </Card>
  );
}

function ScorePreview({ label, value }: { label: string; value: number }) {
  const tone = value >= 80 ? "text-success" : value >= 50 ? "text-grape-700" : "text-warning";
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-slate-400">{label}</div>
      <div className="mt-1 flex items-baseline gap-1">
        <span className={cn("text-3xl font-semibold tracking-tight", tone)}>{value}</span>
        <span className="text-sm text-slate-400">/ 100</span>
      </div>
    </div>
  );
}
