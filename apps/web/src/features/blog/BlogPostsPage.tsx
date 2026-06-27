import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import { createBlogPost, listBlogPosts } from "@/lib/blog";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { ContentDraftPublic, ContentDraftStatus } from "@/types/api";


/**
 * Dashboard route at /blog/posts.
 *
 * Lists every ContentDraft of type=blog_post in the current workspace,
 * grouped by status. The "New post" button mints an empty draft and
 * redirects straight into the editor — same model gomega uses ("draft
 * something now, polish later").
 */
export function BlogPostsPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  if (!workspaceId) {
    return (
      <div className="text-sm text-slate-500">Select a workspace first.</div>
    );
  }
  return <BlogPostsPageInner workspaceId={workspaceId} />;
}


function BlogPostsPageInner({ workspaceId }: { workspaceId: string }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const list = useQuery<ContentDraftPublic[]>({
    queryKey: ["blog-posts", workspaceId],
    queryFn: () => listBlogPosts(workspaceId),
  });

  const [showNew, setShowNew] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<ContentDraftStatus | "all">(
    "all",
  );

  const create = useMutation({
    mutationFn: () => createBlogPost(workspaceId, newTitle.trim() || "Untitled"),
    onSuccess: (draft) => {
      void queryClient.invalidateQueries({ queryKey: ["blog-posts", workspaceId] });
      navigate(`/blog/posts/${draft.id}`);
    },
    onError: (err) => {
      setCreateError(err instanceof ApiError ? err.message : "Could not create post.");
    },
  });

  function onCreate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setCreateError(null);
    create.mutate();
  }

  const filtered = (list.data ?? []).filter((d) =>
    statusFilter === "all" ? true : d.status === statusFilter,
  );

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-grape-700">Blog</p>
          <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">
            Blog posts
          </h1>
          <p className="mt-2 text-sm text-slate-500">
            Drafts, approvals, and published posts for this workspace. AI
            Assistant + image upload live inside each post's editor.
          </p>
        </div>
        <Button onClick={() => setShowNew((v) => !v)}>
          {showNew ? "Cancel" : "New post"}
        </Button>
      </header>

      {showNew ? (
        <Card>
          <CardHeader title="Start a new post" />
          <form
            className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-end"
            onSubmit={onCreate}
            noValidate
          >
            <label
              className="flex flex-1 flex-col gap-1.5 text-sm"
              htmlFor="new-post-title"
            >
              <span className="font-medium text-slate-text">Working title</span>
              <input
                id="new-post-title"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="e.g. How AdGenieHQ cuts wasted ad spend"
                className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
              />
            </label>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Creating…" : "Create + edit"}
            </Button>
          </form>
          {createError ? (
            <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
              {createError}
            </div>
          ) : null}
        </Card>
      ) : null}

      <Card>
        <CardHeader
          title={`Posts (${filtered.length})`}
          action={
            <select
              value={statusFilter}
              onChange={(e) =>
                setStatusFilter(e.target.value as ContentDraftStatus | "all")
              }
              className="rounded-xl border border-slate-200 bg-surface px-3 py-1.5 text-xs text-ink shadow-sm focus:border-grape focus:ring-2 focus:ring-grape-200"
            >
              <option value="all">All statuses</option>
              <option value="draft">Draft</option>
              <option value="approved">Approved</option>
              <option value="published">Published</option>
              <option value="archived">Archived</option>
              <option value="rejected">Rejected</option>
            </select>
          }
        />

        {list.isLoading ? (
          <p className="mt-3 text-sm text-slate-400">Loading…</p>
        ) : filtered.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">
            {statusFilter === "all"
              ? "No posts yet. Click New post to start."
              : `No posts with status "${statusFilter}".`}
          </p>
        ) : (
          <ul className="mt-3 flex flex-col divide-y divide-slate-100">
            {filtered.map((p) => (
              <li
                key={p.id}
                className="flex items-start justify-between gap-3 py-3"
              >
                <Link
                  to={`/blog/posts/${p.id}`}
                  className="flex flex-1 flex-col gap-1 text-left hover:text-grape-700"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-base font-semibold text-ink hover:text-grape-700">
                      {p.title || "(untitled)"}
                    </span>
                    {p.slug ? (
                      <code className="rounded bg-grape-100 px-1.5 py-0.5 font-mono text-[10px] text-grape-700">
                        /{p.slug}
                      </code>
                    ) : null}
                  </div>
                  {p.excerpt ? (
                    <span className="line-clamp-1 text-xs text-slate-500">
                      {p.excerpt}
                    </span>
                  ) : null}
                  <span className="text-[11px] uppercase tracking-wider text-slate-400">
                    Updated {new Date(p.updated_at).toLocaleString()}
                  </span>
                </Link>
                <StatusPill status={p.status} />
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}


function StatusPill({ status }: { status: ContentDraftStatus }) {
  const tone =
    status === "published"
      ? "pill-success"
      : status === "approved"
        ? "pill-grape"
        : status === "rejected"
          ? "pill-danger"
          : status === "archived"
            ? "bg-slate-100 text-slate-600"
            : "pill-warning";
  return <span className={cn("pill shrink-0", tone)}>{status}</span>;
}
