import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError } from "@/lib/api-client";
import { runAgent } from "@/lib/agents";
import {
  getSeoProject,
  listSeoKeywords,
  syncSearchConsole,
} from "@/lib/seo";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { KeywordPublic, SeoProjectPublic } from "@/types/api";

export function SeoPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();

  const project = useQuery({
    queryKey: ["seo", workspaceId, "project"],
    queryFn: () => getSeoProject(workspaceId!),
    enabled: !!workspaceId,
  });

  const keywords = useQuery({
    queryKey: ["seo", workspaceId, "keywords"],
    queryFn: () => listSeoKeywords(workspaceId!),
    enabled: !!workspaceId,
  });

  const [error, setError] = useState<string | null>(null);

  const sync = useMutation({
    mutationFn: () => syncSearchConsole(workspaceId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["seo", workspaceId] });
      setError(null);
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "search_console_not_connected") {
        setError(
          "Search Console isn't connected for this workspace. Connect it in Integrations.",
        );
      } else {
        setError(err instanceof ApiError ? err.message : "Sync failed.");
      }
    },
  });

  const audit = useMutation({
    mutationFn: () => runAgent(workspaceId!, { agent_type: "seo_audit" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["seo", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["agents", "runs", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["agents", "catalog", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["recommendations", workspaceId] });
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not run SEO audit."),
  });

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-grape-700">SEO &amp; GEO</p>
          <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">
            Search visibility &amp; AI-search readiness
          </h1>
          <p className="mt-2 text-sm text-slate-500">
            The SEO &amp; GEO Agent crawls your site and surfaces missing structured data, FAQ
            schema, and Open Graph tags. Search Console sync turns impressions + position into
            opportunity scores.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => audit.mutate()} disabled={audit.isPending}>
            {audit.isPending ? "Auditing…" : "Run SEO audit"}
          </Button>
          <Button
            variant="secondary"
            onClick={() => sync.mutate()}
            disabled={sync.isPending}
          >
            {sync.isPending ? "Syncing…" : "Sync Search Console"}
          </Button>
        </div>
      </header>

      {error ? (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}{" "}
          {error.includes("Connect") ? (
            <Link className="underline" to="/integrations">
              Open Integrations →
            </Link>
          ) : null}
        </div>
      ) : null}

      {project.data ? <ProjectOverview project={project.data} /> : null}

      <Card>
        <CardHeader
          title="Keyword opportunities"
          subtitle={
            project.data?.last_search_console_synced_at
              ? `Synced ${new Date(project.data.last_search_console_synced_at).toLocaleString()}`
              : "Connect Search Console and click Sync to populate this table."
          }
        />
        {keywords.isLoading ? (
          <p className="mt-3 text-sm text-slate-400">Loading…</p>
        ) : keywords.data && keywords.data.length > 0 ? (
          <KeywordTable rows={keywords.data} />
        ) : (
          <EmptyState
            title="No keyword data yet"
            description={
              project.data?.search_console_site_url
                ? "Click Sync Search Console above to fetch the last 28 days."
                : "Connect Google Search Console in Integrations, then run a sync."
            }
            action={
              project.data?.search_console_site_url ? (
                <Button onClick={() => sync.mutate()} disabled={sync.isPending}>
                  Sync Search Console
                </Button>
              ) : (
                <Link to="/integrations">
                  <Button>Open Integrations</Button>
                </Link>
              )
            }
          />
        )}
      </Card>
    </div>
  );
}

function ProjectOverview({ project }: { project: SeoProjectPublic }) {
  const summary = project.crawl_summary;

  return (
    <Card>
      <CardHeader
        title="Site overview"
        subtitle={
          project.last_crawled_at
            ? `Last crawled ${new Date(project.last_crawled_at).toLocaleString()}`
            : "Run an SEO audit to populate this section."
        }
        action={
          project.site_url ? (
            <a
              href={project.site_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm font-medium text-grape-700 hover:text-grape-800"
            >
              {project.site_url} ↗
            </a>
          ) : null
        }
      />

      <dl className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Cell
          label="Sitemap"
          value={summary?.sitemap_url_found ? "Found" : summary === null ? "—" : "Missing"}
          tone={summary?.sitemap_url_found ? "success" : "warning"}
        />
        <Cell
          label="URLs in sitemap"
          value={summary?.page_url_count ?? "—"}
        />
        <Cell
          label="Pages crawled"
          value={summary?.pages_crawled ?? "—"}
        />
        <Cell
          label="GSC site"
          value={project.search_console_site_url ?? "—"}
        />
      </dl>

      {summary ? (
        <ul className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
          <Issue label="Missing titles" count={summary.title_missing_count} />
          <Issue label="Missing meta descriptions" count={summary.meta_missing_count} />
          <Issue label="H1 issues" count={summary.h1_issue_count} />
          <Issue label="Missing canonical links" count={summary.canonical_missing_count} />
          <Issue label="Pages without JSON-LD" count={summary.structured_data_missing_count} />
          <Issue label="Pages without Open Graph" count={summary.open_graph_missing_count} />
          <Issue label="Pages without FAQ schema" count={summary.faq_schema_missing_count} />
        </ul>
      ) : null}
    </Card>
  );
}

function Cell({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone?: "success" | "warning";
}) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-slate-400">{label}</dt>
      <dd
        className={cn(
          "mt-1 truncate text-sm font-medium",
          tone === "success" && "text-success",
          tone === "warning" && "text-warning",
          !tone && "text-ink",
        )}
        title={typeof value === "string" ? value : undefined}
      >
        {value}
      </dd>
    </div>
  );
}

function Issue({ label, count }: { label: string; count: number | undefined }) {
  if (count === undefined) return null;
  return (
    <li
      className={cn(
        "flex items-center justify-between rounded-xl border px-3 py-2",
        count > 0
          ? "border-amber-200 bg-amber-50/60 text-amber-800"
          : "border-emerald-200 bg-emerald-50/40 text-emerald-700",
      )}
    >
      <span>{label}</span>
      <span className="font-semibold">{count}</span>
    </li>
  );
}

function KeywordTable({ rows }: { rows: KeywordPublic[] }) {
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-100 text-xs uppercase tracking-wider text-slate-400">
            <th className="px-3 py-2">Query</th>
            <th className="px-3 py-2 text-right">Impressions</th>
            <th className="px-3 py-2 text-right">Clicks</th>
            <th className="px-3 py-2 text-right">CTR</th>
            <th className="px-3 py-2 text-right">Position</th>
            <th className="px-3 py-2 text-right">Opportunity</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((kw) => (
            <tr key={kw.id} className="hover:bg-grape-50">
              <td className="max-w-md truncate px-3 py-2 text-ink" title={kw.query}>
                {kw.query}
                {kw.top_page ? (
                  <span className="ml-2 text-xs text-slate-400">
                    {new URL(kw.top_page).pathname}
                  </span>
                ) : null}
              </td>
              <td className="px-3 py-2 text-right text-slate-700">
                {kw.impressions.toLocaleString()}
              </td>
              <td className="px-3 py-2 text-right text-slate-700">
                {kw.clicks.toLocaleString()}
              </td>
              <td className="px-3 py-2 text-right text-slate-700">
                {(kw.ctr * 100).toFixed(2)}%
              </td>
              <td className="px-3 py-2 text-right text-slate-700">
                {kw.position.toFixed(1)}
              </td>
              <td className="px-3 py-2 text-right">
                <OpportunityPill score={kw.opportunity_score} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OpportunityPill({ score }: { score: number }) {
  const tone =
    score >= 60 ? "pill-success" : score >= 30 ? "pill-grape" : "bg-slate-100 text-slate-600";
  return <span className={cn("pill", tone)}>{score}</span>;
}
