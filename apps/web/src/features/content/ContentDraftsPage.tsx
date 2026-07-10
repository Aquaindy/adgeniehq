import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { UsageMeter } from "@/components/UsageMeter";
import { ApiError } from "@/lib/api-client";
import {
  generateContentDraft,
  listContentDrafts,
  resolveUploadUrl,
} from "@/lib/content-drafts";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { ContentDraftStatus, ContentDraftType } from "@/types/api";

const TYPE_LABELS: Record<ContentDraftType, string> = {
  blog_post: "Blog post",
  landing_page: "Landing page",
  ad_copy: "Ad copy",
  meta_description: "Meta description",
  email: "Email",
  social_post: "Social post",
  short_video_script: "Short video script",
};

// Platform-native social drafts are authored in the Social studio, which sets
// the platform and hashtags this generic form has no inputs for.
const GENERIC_TYPES = (Object.keys(TYPE_LABELS) as ContentDraftType[]).filter(
  (t) => t !== "short_video_script",
);

const STATUS_PILL: Record<ContentDraftStatus, string> = {
  draft: "bg-slate-100 text-slate-600",
  approved: "pill-success",
  rejected: "pill-danger",
  published: "pill-grape",
  archived: "bg-slate-100 text-slate-500",
};

export function ContentDraftsPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const drafts = useQuery({
    queryKey: ["content-drafts", workspaceId],
    queryFn: () => listContentDrafts(workspaceId!),
    enabled: !!workspaceId,
  });

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <header>
        <p className="text-xs uppercase tracking-wider text-grape-700">Content</p>
        <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">
          Content drafts
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Generate, review, edit, approve, and publish copy. Drafts never auto-publish — an Admin must approve.
        </p>
        <p className="mt-1 text-sm text-slate-500">
          For platform-native posts and Reels/Shorts scripts, use the{" "}
          <Link to="/social" className="font-medium text-grape hover:underline">
            Social studio
          </Link>
          .
        </p>
      </header>

      <UsageMeter resource="content_drafts" />

      <GenerateForm />

      {drafts.isLoading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : drafts.error ? (
        <Card>
          <p className="text-sm text-red-700">
            {drafts.error instanceof Error
              ? drafts.error.message
              : "Could not load drafts."}
          </p>
        </Card>
      ) : drafts.data && drafts.data.length === 0 ? (
        <EmptyState
          title="No drafts yet"
          description="Generate your first draft above, or write one manually via the API."
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {drafts.data?.map((d) => (
            <li key={d.id}>
              <Link
                to={`/content/${d.id}`}
                className="card flex items-start gap-3 p-4 transition hover:bg-grape-50"
              >
                <div className="flex min-w-0 flex-1 flex-col gap-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className={cn("pill", STATUS_PILL[d.status])}>
                        {d.status}
                      </span>
                      <span className="pill bg-slate-50 text-slate-500">
                        {TYPE_LABELS[d.type]}
                      </span>
                      {d.platform ? (
                        <span className="pill pill-grape">{d.platform}</span>
                      ) : null}
                      {d.source === "manual" ? (
                        <span className="pill bg-slate-50 text-slate-500">manual</span>
                      ) : null}
                      {d.model_used ? (
                        <span className="pill bg-grape-50 text-grape-700">
                          {d.model_used}
                        </span>
                      ) : d.source === "agent" ? (
                        <span className="pill bg-amber-50 text-amber-700">
                          deterministic
                        </span>
                      ) : null}
                    </div>
                    <span className="text-xs text-slate-400">
                      {new Date(d.created_at).toLocaleString()}
                    </span>
                  </div>
                  <h3 className="text-sm font-semibold text-ink">{d.title}</h3>
                  <p className="line-clamp-2 text-xs text-slate-500">{d.body}</p>
                </div>
                {d.image_url ? (
                  <img
                    src={resolveUploadUrl(d.image_url)}
                    alt=""
                    className="h-16 w-16 shrink-0 rounded-lg border border-slate-200 object-cover"
                    loading="lazy"
                  />
                ) : null}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function GenerateForm() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const [type, setType] = useState<ContentDraftType>("blog_post");
  const [topic, setTopic] = useState("");
  const [audience, setAudience] = useState("");
  const [keywordsRaw, setKeywordsRaw] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mut = useMutation({
    mutationFn: () =>
      generateContentDraft(workspaceId!, {
        type,
        topic,
        keywords: keywordsRaw
          .split(",")
          .map((k) => k.trim())
          .filter(Boolean),
        audience: audience || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["content-drafts", workspaceId] });
      setTopic("");
      setKeywordsRaw("");
      setAudience("");
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not generate."),
  });

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    if (!topic.trim()) {
      setError("Provide a topic to draft about.");
      return;
    }
    mut.mutate();
  }

  return (
    <Card>
      <CardHeader
        title="Generate a draft"
        subtitle="The agent uses your configured LLM if available; otherwise a deterministic template populated from onboarding."
      />
      <form className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2" onSubmit={onSubmit}>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-slate-text">Type</span>
          <select
            value={type}
            onChange={(e) => setType(e.target.value as ContentDraftType)}
            className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
          >
            {GENERIC_TYPES.map((t) => (
              <option key={t} value={t}>
                {TYPE_LABELS[t]}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-slate-text">Audience (optional)</span>
          <input
            type="text"
            value={audience}
            onChange={(e) => setAudience(e.target.value)}
            placeholder="e.g. demand-gen leads at SaaS companies"
            className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm sm:col-span-2">
          <span className="font-medium text-slate-text">Topic</span>
          <input
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g. Why first-touch attribution misleads B2B teams"
            className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm sm:col-span-2">
          <span className="font-medium text-slate-text">Keywords (comma-separated)</span>
          <input
            type="text"
            value={keywordsRaw}
            onChange={(e) => setKeywordsRaw(e.target.value)}
            placeholder="attribution, b2b, marketing"
            className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
          />
        </label>
        {error ? (
          <div className="sm:col-span-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        ) : null}
        <div className="sm:col-span-2">
          <Button type="submit" disabled={mut.isPending}>
            {mut.isPending ? "Generating…" : "Generate draft"}
          </Button>
        </div>
      </form>
    </Card>
  );
}
