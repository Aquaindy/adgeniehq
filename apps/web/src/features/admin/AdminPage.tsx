import { useQuery } from "@tanstack/react-query";
import { Navigate } from "react-router-dom";

import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import {
  getAdminOverview,
  listAdminUsers,
  listAdminWorkspaces,
} from "@/lib/admin";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";


export function AdminPage() {
  const user = useAuthStore((s) => s.user);
  const hydrated = useAuthStore((s) => s.hydrated);

  const overview = useQuery({
    queryKey: ["admin", "overview"],
    queryFn: getAdminOverview,
    enabled: !!user?.is_superuser,
  });
  const workspaces = useQuery({
    queryKey: ["admin", "workspaces"],
    queryFn: listAdminWorkspaces,
    enabled: !!user?.is_superuser,
  });
  const users = useQuery({
    queryKey: ["admin", "users"],
    queryFn: listAdminUsers,
    enabled: !!user?.is_superuser,
  });

  if (!hydrated) {
    return <div className="text-sm text-slate-400">Loading…</div>;
  }
  if (!user?.is_superuser) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header>
        <p className="text-xs uppercase tracking-wider text-grape-700">Admin</p>
        <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">System overview</h1>
        <p className="mt-2 text-sm text-slate-500">
          Superuser-only system view. Counts are computed live across every workspace.
        </p>
      </header>

      {overview.isLoading ? (
        <p className="text-sm text-slate-400">Loading overview…</p>
      ) : overview.data ? (
        <OverviewGrid data={overview.data} />
      ) : null}

      <Card>
        <CardHeader title="Workspaces" subtitle="Newest first." />
        {workspaces.isLoading ? (
          <p className="mt-3 text-sm text-slate-400">Loading…</p>
        ) : (
          <Table
            columns={["Name", "Slug", "Members", "Plan", "Status", "Created"]}
            rows={(workspaces.data ?? []).map((w) => [
              w.name,
              <span key="slug" className="font-mono text-xs text-slate-500">
                {w.slug}
              </span>,
              w.member_count,
              <PlanPill key="plan" code={w.plan_code} />,
              <SubscriptionPill key="sub" value={w.subscription_status} />,
              <span key="created" className="text-xs text-slate-500">
                {new Date(w.created_at).toLocaleString()}
              </span>,
            ])}
          />
        )}
      </Card>

      <Card>
        <CardHeader title="Users" subtitle="Active accounts across the system." />
        {users.isLoading ? (
          <p className="mt-3 text-sm text-slate-400">Loading…</p>
        ) : (
          <Table
            columns={["Email", "Name", "Workspaces", "Active", "Superuser", "Created"]}
            rows={(users.data ?? []).map((u) => [
              u.email,
              u.full_name ?? "—",
              u.workspace_count,
              u.is_active ? <span key="a" className="pill pill-success">yes</span> : <span key="a" className="pill pill-danger">no</span>,
              u.is_superuser ? <span key="s" className="pill pill-grape">yes</span> : <span key="s" className="text-slate-400">—</span>,
              <span key="c" className="text-xs text-slate-500">
                {new Date(u.created_at).toLocaleString()}
              </span>,
            ])}
          />
        )}
      </Card>

      {(overview.error || workspaces.error || users.error) ? (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {[overview.error, workspaces.error, users.error]
            .filter((e): e is Error => Boolean(e))
            .map((e) => (e instanceof ApiError ? e.message : e.message))
            .join(" · ")}
        </div>
      ) : null}
    </div>
  );
}


function OverviewGrid({ data }: { data: NonNullable<ReturnType<typeof getAdminOverview> extends Promise<infer T> ? T : never> }) {
  const tiles: { label: string; value: number; tone?: "success" | "warning" | "grape" }[] = [
    { label: "Users", value: data.users_total },
    { label: "Superusers", value: data.superusers_total, tone: "grape" },
    { label: "Workspaces", value: data.workspaces_total },
    { label: "Paid workspaces", value: data.paid_workspaces_total, tone: "success" },
    { label: "Agent runs (total)", value: data.agent_runs_total },
    { label: "Agent runs · 7d", value: data.agent_runs_last_7d, tone: "grape" },
    { label: "Open recs", value: data.recommendations_open },
    { label: "Integrations connected", value: data.integrations_connected },
    { label: "Landing pages", value: data.landing_pages_total },
    { label: "Reports · 7d", value: data.reports_generated_last_7d },
    { label: "Executions (total)", value: data.executions_total },
    { label: "Exec ok · 7d", value: data.executions_succeeded_last_7d, tone: "success" },
    { label: "Content drafts", value: data.content_drafts_total },
    { label: "Drafts published · 7d", value: data.content_drafts_published_last_7d, tone: "success" },
    { label: "Outreach sent · 7d", value: data.outreach_emails_sent_last_7d, tone: "grape" },
    { label: "Prospects", value: data.outreach_prospects_total },
    { label: "A/B tests active", value: data.ab_tests_active, tone: "grape" },
    { label: "A/B done · 7d", value: data.ab_tests_completed_last_7d, tone: "success" },
  ];
  return (
    <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      {tiles.map((t) => (
        <div key={t.label} className="rounded-2xl border border-slate-100 bg-white px-4 py-3 shadow-card">
          <div className="text-[11px] uppercase tracking-wider text-slate-400">{t.label}</div>
          <div
            className={cn(
              "mt-1 text-2xl font-semibold",
              t.tone === "grape" && "text-grape-700",
              t.tone === "success" && "text-success",
              t.tone === "warning" && "text-warning",
              !t.tone && "text-ink",
            )}
          >
            {t.value.toLocaleString()}
          </div>
        </div>
      ))}
    </section>
  );
}


function Table({
  columns,
  rows,
}: {
  columns: string[];
  rows: React.ReactNode[][];
}) {
  if (rows.length === 0) {
    return <p className="mt-3 text-sm text-slate-500">No rows.</p>;
  }
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-100 text-xs uppercase tracking-wider text-slate-400">
            {columns.map((c) => (
              <th key={c} className="px-3 py-2">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row, idx) => (
            <tr key={idx} className="hover:bg-slate-50">
              {row.map((cell, ci) => (
                <td key={ci} className="px-3 py-2 text-slate-700">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


function PlanPill({ code }: { code: string }) {
  return (
    <span
      className={cn(
        "pill",
        code === "free" && "bg-slate-100 text-slate-600",
        code === "starter" && "pill-grape",
        code === "pro" && "pill-success",
        code === "agency" && "pill-success",
      )}
    >
      {code}
    </span>
  );
}


function SubscriptionPill({ value }: { value: string }) {
  return (
    <span
      className={cn(
        "pill",
        value === "active" && "pill-success",
        value === "trialing" && "pill-grape",
        value === "past_due" && "pill-warning",
        value === "canceled" && "pill-danger",
        (value === "none" || !value) && "bg-slate-100 text-slate-600",
      )}
    >
      {value}
    </span>
  );
}
