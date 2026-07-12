import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError } from "@/lib/api-client";
import {
  downloadTextFile,
  growthDnaFilename,
  growthDnaToMarkdown,
} from "@/lib/growth-dna-export";
import {
  deleteGrowthDna,
  generateGrowthDna,
  getGrowthDna,
  getGrowthDnaById,
  listGrowthDnaHistory,
  renameGrowthDna,
} from "@/lib/onboarding";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type {
  ChannelStrategy,
  ContentPillar,
  GrowthDna,
  GrowthDnaSummary,
  MarketingStrategy,
} from "@/types/api";

export function GrowthDnaPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  // `?profile=<id>` pins the page to a saved (historical) profile.
  const savedId = searchParams.get("profile");
  const [showHistory, setShowHistory] = useState(false);

  const latest = useQuery({
    queryKey: ["growth-dna", workspaceId],
    queryFn: () => getGrowthDna(workspaceId!),
    enabled: !!workspaceId && !savedId,
    retry: false,
    // While the AI tailoring runs in the background, poll until it lands.
    refetchInterval: (query) =>
      (query.state.data as GrowthDna | undefined)?.marketing_strategy?.enrichment ===
      "pending"
        ? 3000
        : false,
  });

  const saved = useQuery({
    queryKey: ["growth-dna", workspaceId, savedId],
    queryFn: () => getGrowthDnaById(workspaceId!, savedId!),
    enabled: !!workspaceId && !!savedId,
    retry: false,
  });

  const history = useQuery({
    queryKey: ["growth-dna-history", workspaceId],
    queryFn: () => listGrowthDnaHistory(workspaceId!),
    enabled: !!workspaceId,
  });

  const viewSaved = (id: string | null) =>
    setSearchParams(id ? { profile: id } : {});

  const regenerate = useMutation({
    mutationFn: () => generateGrowthDna(workspaceId!),
    onSuccess: (fresh) => {
      queryClient.setQueryData(["growth-dna", workspaceId], fresh);
      queryClient.invalidateQueries({ queryKey: ["growth-dna", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["growth-dna-history", workspaceId] });
    },
  });

  const rename = useMutation({
    mutationFn: ({ id, label }: { id: string; label: string | null }) =>
      renameGrowthDna(workspaceId!, id, label),
    onSuccess: (fresh) => {
      queryClient.setQueryData(["growth-dna", workspaceId, fresh.id], fresh);
      queryClient.invalidateQueries({ queryKey: ["growth-dna", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["growth-dna-history", workspaceId] });
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteGrowthDna(workspaceId!, id),
    onSuccess: (_res, id) => {
      if (savedId === id) viewSaved(null);
      queryClient.invalidateQueries({ queryKey: ["growth-dna", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["growth-dna-history", workspaceId] });
    },
  });

  const active = savedId ? saved : latest;
  const historyItems = history.data ?? [];

  if (active.isLoading) {
    return <div className="text-sm text-slate-400">Loading…</div>;
  }

  if (active.error) {
    const code = active.error instanceof ApiError ? active.error.code : null;
    if (code === "growth_dna_not_found") {
      if (savedId) {
        return (
          <div className="mx-auto max-w-3xl">
            <EmptyState
              title="Saved profile not found"
              description="This Growth DNA profile no longer exists — it may have been deleted."
              action={<Button onClick={() => viewSaved(null)}>View latest profile</Button>}
            />
          </div>
        );
      }
      return (
        <div className="mx-auto max-w-3xl">
          <EmptyState
            title="No Growth DNA Profile yet"
            description="Complete onboarding to generate your readiness scores, recommended first campaigns, and 30-day growth plan."
            action={
              <Link to="/onboarding">
                <Button>Start onboarding</Button>
              </Link>
            }
          />
        </div>
      );
    }
    return (
      <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
        {active.error instanceof Error ? active.error.message : "Could not load Growth DNA Profile."}
      </div>
    );
  }

  if (!active.data) return null;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" onClick={() => setShowHistory((v) => !v)}>
          {showHistory
            ? "Hide saved profiles"
            : `Saved profiles${historyItems.length > 0 ? ` (${historyItems.length})` : ""}`}
        </Button>
        {savedId && (
          <Button variant="secondary" onClick={() => viewSaved(null)}>
            ← Back to latest
          </Button>
        )}
      </div>

      {showHistory && (
        <HistoryPanel
          items={historyItems}
          activeId={active.data.id}
          loading={history.isLoading}
          onView={(id) => viewSaved(id)}
          onRename={(id, label) => rename.mutate({ id, label })}
          onDelete={(id) => {
            if (window.confirm("Delete this saved Growth DNA profile? This cannot be undone.")) {
              remove.mutate(id);
            }
          }}
        />
      )}

      {savedId && (
        <div className="rounded-xl border border-grape-100 bg-grape-soft px-4 py-3 text-sm text-grape-800">
          You&apos;re viewing a saved profile generated{" "}
          {new Date(active.data.created_at).toLocaleString()}. The latest profile stays
          untouched — go back to it to regenerate.
        </div>
      )}

      <GrowthDnaView
        dna={active.data}
        onRegenerate={savedId ? undefined : () => regenerate.mutate()}
        regenerating={regenerate.isPending}
        regenerateError={
          regenerate.error instanceof Error ? regenerate.error.message : null
        }
        onRename={(label) => rename.mutate({ id: active.data!.id, label })}
        renamePending={rename.isPending}
      />
    </div>
  );
}

export function GrowthDnaView({
  dna,
  onRegenerate,
  regenerating = false,
  regenerateError = null,
  onRename,
  renamePending = false,
}: {
  dna: GrowthDna;
  onRegenerate?: () => void;
  regenerating?: boolean;
  regenerateError?: string | null;
  onRename?: (label: string | null) => void;
  renamePending?: boolean;
}) {
  const isAi = dna.marketing_strategy?.source === "ai";
  const enriching = dna.marketing_strategy?.enrichment === "pending";
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-grape-700">Growth DNA Profile</p>
          {dna.label ? (
            <>
              <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">{dna.label}</h1>
              <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">
                {dna.business_summary}
              </p>
            </>
          ) : (
            <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">{dna.business_summary}</h1>
          )}
          <p className="mt-1 text-xs text-slate-400">
            Generated {new Date(dna.created_at).toLocaleString()} · engine {dna.engine_version}
            {isAi ? " · AI-tailored" : ""}
          </p>
          {onRename && (
            <div className="mt-2">
              <NameControl value={dna.label} onSave={onRename} pending={renamePending} />
            </div>
          )}
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
              variant="ghost"
              onClick={() =>
                downloadTextFile(
                  growthDnaFilename(dna, "md"),
                  growthDnaToMarkdown(dna),
                  "text/markdown",
                )
              }
            >
              Download .md
            </Button>
            <Button
              variant="ghost"
              onClick={() =>
                downloadTextFile(
                  growthDnaFilename(dna, "json"),
                  JSON.stringify(dna, null, 2),
                  "application/json",
                )
              }
            >
              Download .json
            </Button>
            <Button variant="ghost" onClick={() => window.print()}>
              Print / PDF
            </Button>
            {onRegenerate && (
              <Button variant="secondary" onClick={onRegenerate} disabled={regenerating}>
                {regenerating ? "Regenerating…" : "Regenerate"}
              </Button>
            )}
          </div>
          {regenerateError && <span className="text-xs text-danger">{regenerateError}</span>}
        </div>
      </header>

      {enriching ? (
        <div className="flex items-center gap-3 rounded-xl border border-grape-100 bg-grape-soft px-4 py-3 text-sm text-grape-800">
          <span className="size-2 animate-pulse rounded-full bg-grape-600" aria-hidden />
          Your profile is ready — tailoring the strategy and content with AI in the
          background. This page updates automatically in a few seconds.
        </div>
      ) : null}

      <section className="grid gap-4 sm:grid-cols-2">
        <ScoreCard
          title="Funnel readiness"
          score={dna.funnel_readiness_score}
          subtitle="Audience clarity, offer clarity, landing pages, brand voice, analytics."
        />
        <ScoreCard
          title="Paid ads readiness"
          score={dna.paid_ads_readiness_score}
          subtitle="Budget, conversion goal, audience, geo, platforms, analytics."
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="ICP summary" />
          <p className="mt-3 text-sm leading-relaxed text-slate-700">{dna.icp_summary}</p>
        </Card>
        <Card>
          <CardHeader title="Offer positioning" />
          <p className="mt-3 text-sm leading-relaxed text-slate-700">{dna.offer_positioning}</p>
        </Card>
      </section>

      <MarketingStrategySection strategy={dna.marketing_strategy} />

      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="SEO & GEO opportunity" />
          <p className="mt-3 text-sm leading-relaxed text-slate-700">
            {dna.seo_geo_opportunity_summary}
          </p>
        </Card>
        <Card>
          <CardHeader title="Tracking readiness" />
          <p className="mt-3 text-sm leading-relaxed text-slate-700">{dna.tracking_readiness}</p>
        </Card>
      </section>

      <Card>
        <CardHeader
          title="Website conversion risks"
          subtitle="Things to fix before scaling spend."
        />
        {dna.website_conversion_risks.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">No critical risks detected from your inputs.</p>
        ) : (
          <ul className="mt-3 flex flex-col gap-2 text-sm text-slate-700">
            {dna.website_conversion_risks.map((r) => (
              <li key={r} className="flex gap-2">
                <span aria-hidden className="mt-1 size-1.5 shrink-0 rounded-full bg-warning" />
                {r}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <CardHeader
          title="Recommended first campaigns"
          subtitle="A starting allocation across the platforms you selected."
        />
        <ul className="mt-3 flex flex-col gap-3">
          {dna.recommended_first_campaigns.map((c) => (
            <li
              key={c.platform}
              className="flex flex-col gap-1 rounded-xl border border-slate-100 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div>
                <div className="text-sm font-semibold text-ink">{c.platform}</div>
                <div className="text-xs text-slate-500">{c.objective}</div>
                <div className="mt-1 text-xs text-slate-500">{c.rationale}</div>
              </div>
              <span className="pill pill-grape self-start sm:self-auto">
                {c.budget_share_pct}% of budget
              </span>
            </li>
          ))}
        </ul>
      </Card>

      <Card>
        <CardHeader
          title="30-day growth plan"
          subtitle="Adapts based on your readiness scores. Each week's deliverables are derived from the gaps in your onboarding answers."
        />
        <ol className="mt-3 grid gap-3 lg:grid-cols-2">
          {dna.thirty_day_growth_plan.map((week) => (
            <li
              key={week.week}
              className="rounded-xl border border-slate-100 bg-grape-soft/40 px-4 py-3"
            >
              <div className="flex items-center gap-2">
                <span className="pill pill-grape">Week {week.week}</span>
                <span className="text-sm font-semibold text-ink">{week.focus}</span>
              </div>
              <ul className="mt-2 flex flex-col gap-1.5 text-sm text-slate-700">
                {week.deliverables.map((d) => (
                  <li key={d} className="flex gap-2">
                    <span aria-hidden className="mt-1 size-1.5 shrink-0 rounded-full bg-grape" />
                    {d}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      </Card>

      <div className="flex items-center justify-between">
        <Link
          to="/onboarding"
          className="text-sm font-medium text-grape-700 hover:text-grape-800"
        >
          Refine onboarding answers →
        </Link>
        <Link
          to="/dashboard"
          className="text-sm font-medium text-slate-500 hover:text-ink"
        >
          Back to Command Center
        </Link>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Saved profiles (history)
// ---------------------------------------------------------------------------

/** Label if named, else the first sentence of the business summary. */
function profileDisplayName(item: { label: string | null; business_summary: string }) {
  if (item.label) return item.label;
  const idx = item.business_summary.indexOf(". ");
  const first = idx > 0 ? item.business_summary.slice(0, idx) : item.business_summary;
  return first.length > 72 ? `${first.slice(0, 71).trimEnd()}…` : first;
}

function NameControl({
  value,
  onSave,
  pending = false,
}: {
  value: string | null;
  onSave: (label: string | null) => void;
  pending?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");

  if (!editing) {
    return (
      <button
        type="button"
        onClick={() => {
          setDraft(value ?? "");
          setEditing(true);
        }}
        className="text-xs font-medium text-grape-700 hover:underline"
      >
        {value ? "Rename profile" : "Name this profile"}
      </button>
    );
  }
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSave(draft.trim() || null);
        setEditing(false);
      }}
      className="flex flex-wrap items-center gap-2"
    >
      <input
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        maxLength={160}
        placeholder="e.g. DemoGenius launch"
        className="w-64 rounded-lg border border-slate-200 px-2.5 py-1.5 text-sm focus:border-grape-500 focus:outline-none"
      />
      <button
        type="submit"
        disabled={pending}
        className="text-xs font-medium text-grape-700 hover:underline disabled:opacity-50"
      >
        Save
      </button>
      <button
        type="button"
        onClick={() => setEditing(false)}
        className="text-xs font-medium text-slate-500 hover:underline"
      >
        Cancel
      </button>
    </form>
  );
}

function HistoryPanel({
  items,
  activeId,
  loading = false,
  onView,
  onRename,
  onDelete,
}: {
  items: GrowthDnaSummary[];
  activeId: string;
  loading?: boolean;
  onView: (id: string) => void;
  onRename: (id: string, label: string | null) => void;
  onDelete: (id: string) => void;
}) {
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  return (
    <Card>
      <CardHeader
        title="Saved profiles"
        subtitle="Every generated Growth DNA is kept here automatically. Name the ones you want to find again, and reopen any of them at any time."
      />
      {loading ? (
        <p className="mt-3 text-sm text-slate-400">Loading saved profiles…</p>
      ) : items.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">
          Nothing saved yet — generate a profile and it will appear here.
        </p>
      ) : (
        <ul className="mt-3 flex flex-col gap-2">
          {items.map((item) => {
            const isActive = item.id === activeId;
            const isAi = item.engine_version.startsWith("ai-");
            return (
              <li
                key={item.id}
                className={cn(
                  "flex flex-col gap-2 rounded-xl border px-4 py-3 sm:flex-row sm:items-center sm:justify-between",
                  isActive ? "border-grape-100 bg-grape-soft/40" : "border-slate-100",
                )}
              >
                <div className="min-w-0">
                  {renamingId === item.id ? (
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        onRename(item.id, draft.trim() || null);
                        setRenamingId(null);
                      }}
                      className="flex flex-wrap items-center gap-2"
                    >
                      <input
                        autoFocus
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        maxLength={160}
                        placeholder="e.g. DemoGenius launch"
                        className="w-56 rounded-lg border border-slate-200 px-2.5 py-1 text-sm focus:border-grape-500 focus:outline-none"
                      />
                      <button
                        type="submit"
                        className="text-xs font-medium text-grape-700 hover:underline"
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        onClick={() => setRenamingId(null)}
                        className="text-xs font-medium text-slate-500 hover:underline"
                      >
                        Cancel
                      </button>
                    </form>
                  ) : (
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-sm font-semibold text-ink">
                        {profileDisplayName(item)}
                      </span>
                      {isAi && <span className="pill pill-grape">AI-tailored</span>}
                      {isActive && (
                        <span className="pill bg-slate-100 text-slate-600">Viewing</span>
                      )}
                    </div>
                  )}
                  <p className="mt-0.5 text-xs text-slate-400">
                    {new Date(item.created_at).toLocaleString()} · Funnel{" "}
                    {item.funnel_readiness_score} · Paid ads {item.paid_ads_readiness_score}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  {!isActive && (
                    <button
                      type="button"
                      onClick={() => onView(item.id)}
                      className="text-xs font-medium text-grape-700 hover:underline"
                    >
                      View
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      setDraft(item.label ?? "");
                      setRenamingId(item.id);
                    }}
                    className="text-xs font-medium text-slate-600 hover:underline"
                  >
                    {item.label ? "Rename" : "Name"}
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(item.id)}
                    className="text-xs font-medium text-danger hover:underline"
                  >
                    Delete
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

function ScoreCard({
  title,
  score,
  subtitle,
}: {
  title: string;
  score: number;
  subtitle: string;
}) {
  const tone =
    score >= 80
      ? "text-success"
      : score >= 50
        ? "text-grape-700"
        : "text-warning";
  return (
    <Card>
      <CardHeader title={title} subtitle={subtitle} />
      <div className="mt-3 flex items-baseline gap-2">
        <span className={cn("text-4xl font-semibold tracking-tight", tone)}>{score}</span>
        <span className="text-sm text-slate-400">/ 100</span>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className={cn(
            "h-full rounded-full transition-all",
            score >= 80
              ? "bg-success"
              : score >= 50
                ? "bg-grape"
                : "bg-warning",
          )}
          style={{ width: `${Math.max(2, Math.min(100, score))}%` }}
        />
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Comprehensive marketing strategy
// ---------------------------------------------------------------------------

const CATEGORY_GROUPS: { key: string; label: string; blurb: string }[] = [
  { key: "paid", label: "Paid media", blurb: "Bought attention — fastest to test, scales with budget." },
  { key: "owned", label: "Owned media", blurb: "Channels you control — compounding, lower long-run cost." },
  { key: "earned", label: "Earned media", blurb: "Trust from others — low-CAC when it works." },
  { key: "foundation", label: "Measurement foundation", blurb: "Make every other channel trustworthy." },
];

function MarketingStrategySection({ strategy }: { strategy?: MarketingStrategy }) {
  if (!strategy || !strategy.channels || strategy.channels.length === 0) {
    return null;
  }
  const { overview, channels, content_pillars, platform_strategy, email_strategy, content_calendar } =
    strategy;
  const isAi = strategy.source === "ai";

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-xl font-semibold text-ink sm:text-2xl">Marketing strategy</h2>
          <p className="text-sm text-slate-500">
            A comprehensive, cross-channel playbook tailored to your business.
          </p>
        </div>
        <span
          className={cn(
            "pill",
            isAi ? "pill-grape" : "bg-slate-100 text-slate-600",
          )}
          title={strategy.model_used ? `Model: ${strategy.model_used}` : undefined}
        >
          {isAi ? "AI-tailored" : "Baseline strategy"}
        </span>
      </div>

      {overview?.thesis && (
        <Card className="border-grape-100 bg-grape-soft/40">
          <CardHeader title="Strategic thesis" />
          <p className="mt-2 text-sm leading-relaxed text-slate-700">{overview.thesis}</p>
          {overview.priorities?.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {overview.priorities.map((p) => (
                <span key={p} className="pill pill-grape">
                  {p}
                </span>
              ))}
            </div>
          )}
        </Card>
      )}

      {overview?.budget_allocation?.length > 0 && (
        <Card>
          <CardHeader
            title="Suggested budget allocation"
            subtitle="A starting split across channel groups — adjust as data comes in."
          />
          <ul className="mt-3 flex flex-col gap-3">
            {overview.budget_allocation.map((b) => (
              <li key={b.channel}>
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium text-ink">{b.channel}</span>
                  <span className="text-slate-500">{b.pct}%</span>
                </div>
                <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full bg-grape transition-all"
                    style={{ width: `${Math.max(2, Math.min(100, b.pct))}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Channels grouped by media type */}
      {CATEGORY_GROUPS.map((group) => {
        const items = channels.filter((c) => c.category === group.key);
        if (items.length === 0) return null;
        return (
          <div key={group.key} className="flex flex-col gap-3">
            <div className="flex items-baseline gap-2">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-grape-700">
                {group.label}
              </h3>
              <span className="text-xs text-slate-400">{group.blurb}</span>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              {items
                .sort((a, b) => priorityRank(a.priority) - priorityRank(b.priority))
                .map((c) => (
                  <ChannelCard key={c.channel} channel={c} />
                ))}
            </div>
          </div>
        );
      })}

      {/* Content pillars (80/20) */}
      {content_pillars?.length > 0 && (
        <Card>
          <CardHeader
            title="Content pillars & the 80/20 rule"
            subtitle="What to post, and how much of each. Mostly value, sparing promotion."
          />
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {content_pillars.map((p) => (
              <ContentPillarCard key={p.name} pillar={p} />
            ))}
          </div>
        </Card>
      )}

      {/* Platform strategy table */}
      {platform_strategy?.length > 0 && (
        <Card>
          <CardHeader
            title="Organic social platform strategy"
            subtitle="Where to show up, how often, and what each platform is best for."
          />
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[36rem] border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wide text-slate-400">
                  <th className="py-2 pr-4 font-medium">Platform</th>
                  <th className="py-2 pr-4 font-medium">Cadence</th>
                  <th className="py-2 font-medium">Best for</th>
                </tr>
              </thead>
              <tbody>
                {platform_strategy.map((p) => (
                  <tr key={p.platform} className="border-b border-slate-50 last:border-0">
                    <td className="py-2 pr-4 font-semibold text-ink">{p.platform}</td>
                    <td className="py-2 pr-4 text-slate-600">{p.cadence}</td>
                    <td className="py-2 text-slate-600">{p.best_for || p.focus}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Email / lifecycle */}
      {email_strategy?.flows?.length > 0 && (
        <Card>
          <CardHeader title="Email marketing & lifecycle" subtitle={email_strategy.summary} />
          {email_strategy.newsletter_cadence && (
            <p className="mt-2 text-xs text-slate-500">
              Broadcast cadence: <span className="font-medium text-slate-700">{email_strategy.newsletter_cadence}</span>
            </p>
          )}
          <ul className="mt-3 flex flex-col gap-2">
            {email_strategy.flows.map((f) => (
              <li
                key={f.name}
                className="flex flex-col gap-1 rounded-xl border border-slate-100 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <div className="text-sm font-semibold text-ink">{f.name}</div>
                  <div className="text-xs text-slate-500">Trigger: {f.trigger}</div>
                </div>
                <div className="text-xs text-slate-600 sm:max-w-[50%] sm:text-right">{f.goal}</div>
              </li>
            ))}
          </ul>
          {email_strategy.kpis?.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {email_strategy.kpis.map((k) => (
                <span key={k} className="pill bg-slate-100 text-slate-600">
                  {k}
                </span>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* Content calendar */}
      {content_calendar?.length > 0 && (
        <Card>
          <CardHeader
            title="30-day content calendar"
            subtitle="A starting cadence of specific posts across your channels and pillars."
          />
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[44rem] border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wide text-slate-400">
                  <th className="py-2 pr-3 font-medium">Day</th>
                  <th className="py-2 pr-3 font-medium">Channel</th>
                  <th className="py-2 pr-3 font-medium">Format</th>
                  <th className="py-2 pr-3 font-medium">Pillar</th>
                  <th className="py-2 font-medium">Hook & direction</th>
                </tr>
              </thead>
              <tbody>
                {content_calendar
                  .slice()
                  .sort((a, b) => a.day - b.day)
                  .map((c, i) => (
                    <tr key={`${c.day}-${i}`} className="border-b border-slate-50 align-top last:border-0">
                      <td className="py-2 pr-3 font-semibold text-grape-700">{c.day}</td>
                      <td className="py-2 pr-3 text-slate-600">{c.channel}</td>
                      <td className="py-2 pr-3 text-slate-600">{c.format}</td>
                      <td className="py-2 pr-3 text-slate-600">{c.pillar}</td>
                      <td className="py-2 text-slate-700">
                        <span className="font-medium text-ink">{c.hook}</span>
                        {c.caption_direction && (
                          <span className="block text-xs text-slate-500">{c.caption_direction}</span>
                        )}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </section>
  );
}

function priorityRank(priority: string): number {
  return priority === "high" ? 0 : priority === "medium" ? 1 : 2;
}

function ChannelCard({ channel }: { channel: ChannelStrategy }) {
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <h4 className="text-sm font-semibold text-ink">{channel.channel}</h4>
        <div className="flex shrink-0 gap-1.5">
          <PriorityBadge priority={channel.priority} />
          <StatusBadge status={channel.status} />
        </div>
      </div>
      {channel.summary && (
        <p className="text-sm leading-relaxed text-slate-600">{channel.summary}</p>
      )}
      {channel.cadence && (
        <p className="text-xs text-slate-400">Cadence: {channel.cadence}</p>
      )}
      {channel.tactics?.length > 0 && (
        <ul className="mt-1 flex flex-col gap-1 text-sm text-slate-700">
          {channel.tactics.map((t) => (
            <li key={t} className="flex gap-2">
              <span aria-hidden className="mt-1.5 size-1.5 shrink-0 rounded-full bg-grape" />
              {t}
            </li>
          ))}
        </ul>
      )}
      {channel.kpis?.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1.5">
          {channel.kpis.map((k) => (
            <span key={k} className="pill bg-slate-100 text-slate-600">
              {k}
            </span>
          ))}
        </div>
      )}
      {channel.first_step && (
        <p className="mt-1 rounded-lg bg-grape-soft/50 px-3 py-2 text-xs text-grape-800">
          <span className="font-semibold">First step:</span> {channel.first_step}
        </p>
      )}
    </Card>
  );
}

function ContentPillarCard({ pillar }: { pillar: ContentPillar }) {
  return (
    <div className="rounded-xl border border-slate-100 px-4 py-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-ink">{pillar.name}</span>
        <span className="pill pill-grape">{pillar.allocation_pct}%</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-grape"
          style={{ width: `${Math.max(2, Math.min(100, pillar.allocation_pct))}%` }}
        />
      </div>
      {pillar.description && (
        <p className="mt-2 text-xs leading-relaxed text-slate-600">{pillar.description}</p>
      )}
      {pillar.example_hooks?.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1 text-xs text-slate-700">
          {pillar.example_hooks.map((h) => (
            <li key={h} className="flex gap-1.5">
              <span aria-hidden className="text-grape-500">“</span>
              <span className="italic">{h}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PriorityBadge({ priority }: { priority: string }) {
  const label = priority.charAt(0).toUpperCase() + priority.slice(1);
  const tone =
    priority === "high"
      ? "bg-grape text-white"
      : priority === "medium"
        ? "bg-grape-soft text-grape-800"
        : "bg-slate-100 text-slate-500";
  return <span className={cn("pill", tone)}>{label}</span>;
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; tone: string }> = {
    ready: { label: "Ready", tone: "bg-success/10 text-success" },
    needs_setup: { label: "Needs setup", tone: "bg-warning/10 text-warning" },
    recommended: { label: "Recommended", tone: "bg-slate-100 text-slate-500" },
  };
  const entry = map[status] ?? { label: status, tone: "bg-slate-100 text-slate-500" };
  return <span className={cn("pill", entry.tone)}>{entry.label}</span>;
}
