import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import {
  approveContentDraft,
  archiveContentDraft,
  getContentDraft,
  publishContentDraft,
  rejectContentDraft,
  updateContentDraft,
} from "@/lib/content-drafts";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { ContentDraftPublic, ContentDraftStatus } from "@/types/api";

const STATUS_PILL: Record<ContentDraftStatus, string> = {
  draft: "bg-slate-100 text-slate-600",
  approved: "pill-success",
  rejected: "pill-danger",
  published: "pill-grape",
  archived: "bg-slate-100 text-slate-500",
};

export function ContentDraftDetailPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const { draftId } = useParams<{ draftId: string }>();

  const draft = useQuery({
    queryKey: ["content-draft", workspaceId, draftId],
    queryFn: () => getContentDraft(workspaceId!, draftId!),
    enabled: !!workspaceId && !!draftId,
  });

  if (draft.isLoading)
    return <div className="text-sm text-slate-400">Loading…</div>;

  if (draft.error) {
    return (
      <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
        {draft.error instanceof Error ? draft.error.message : "Could not load."}
      </div>
    );
  }
  if (!draft.data) return null;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <DetailHeader draft={draft.data} />
      <BodyCard draft={draft.data} />
      <SeoCard draft={draft.data} />
      <ActionsCard draft={draft.data} />

      <div className="flex justify-between text-sm">
        <Link to="/content" className="font-medium text-grape-700 hover:text-grape-800">
          ← All drafts
        </Link>
        {draft.data.agent_run_id ? (
          <Link
            to={`/agents/runs/${draft.data.agent_run_id}`}
            className="text-grape-700 hover:text-grape-800"
          >
            See generating run →
          </Link>
        ) : null}
      </div>
    </div>
  );
}

function DetailHeader({ draft }: { draft: ContentDraftPublic }) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p className="text-xs uppercase tracking-wider text-grape-700">
          {draft.type.replace("_", " ")}
        </p>
        <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">
          {draft.title}
        </h1>
        <p className="mt-1 text-xs text-slate-400">
          {draft.source === "agent" ? "Agent-drafted" : "Manual"} ·{" "}
          {new Date(draft.created_at).toLocaleString()}
          {draft.model_used ? ` · ${draft.model_used}` : ""}
        </p>
      </div>
      <span className={cn("pill", STATUS_PILL[draft.status])}>{draft.status}</span>
    </header>
  );
}

function BodyCard({ draft }: { draft: ContentDraftPublic }) {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(draft.title);
  const [body, setBody] = useState(draft.body);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTitle(draft.title);
    setBody(draft.body);
  }, [draft.title, draft.body]);

  const mut = useMutation({
    mutationFn: () =>
      updateContentDraft(workspaceId!, draft.id, { title, body }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["content-draft", workspaceId, draft.id],
      });
      queryClient.invalidateQueries({ queryKey: ["content-drafts", workspaceId] });
      setOpen(false);
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not save."),
  });

  const editable =
    draft.status !== "published" && draft.status !== "archived";

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    mut.mutate();
  }

  if (!open) {
    return (
      <Card>
        <CardHeader
          title="Body"
          action={
            editable ? (
              <Button variant="secondary" onClick={() => setOpen(true)}>
                Edit
              </Button>
            ) : null
          }
        />
        <pre className="mt-3 max-h-[480px] overflow-auto whitespace-pre-wrap rounded-xl bg-slate-50 p-4 font-sans text-sm text-slate-700">
{draft.body}
        </pre>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader title="Edit" />
      <form className="mt-4 flex flex-col gap-3 text-sm" onSubmit={onSubmit}>
        <label className="flex flex-col gap-1.5">
          <span className="font-medium text-slate-text">Title</span>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="font-medium text-slate-text">Body</span>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={18}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 font-mono text-xs text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
          />
        </label>
        {error ? (
          <div className="rounded-lg bg-red-50 px-3 py-2 text-red-700">{error}</div>
        ) : null}
        <div className="flex items-center gap-2">
          <Button type="submit" disabled={mut.isPending}>
            {mut.isPending ? "Saving…" : "Save"}
          </Button>
          <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}

function SeoCard({ draft }: { draft: ContentDraftPublic }) {
  const meta = draft.seo_metadata as
    | { meta_title?: string; meta_description?: string }
    | null;
  if (!meta || (!meta.meta_title && !meta.meta_description)) return null;
  return (
    <Card>
      <CardHeader title="SEO metadata" />
      <dl className="mt-3 grid grid-cols-1 gap-3 text-sm">
        {meta.meta_title ? (
          <div>
            <dt className="text-slate-400">Meta title</dt>
            <dd className="mt-1 text-slate-700">{meta.meta_title}</dd>
          </div>
        ) : null}
        {meta.meta_description ? (
          <div>
            <dt className="text-slate-400">Meta description</dt>
            <dd className="mt-1 text-slate-700">{meta.meta_description}</dd>
          </div>
        ) : null}
        {draft.keywords && draft.keywords.length ? (
          <div>
            <dt className="text-slate-400">Keywords</dt>
            <dd className="mt-1 flex flex-wrap gap-1">
              {draft.keywords.map((kw) => (
                <span key={kw} className="pill bg-grape-50 text-grape-700">
                  {kw}
                </span>
              ))}
            </dd>
          </div>
        ) : null}
      </dl>
    </Card>
  );
}

function ActionsCard({ draft }: { draft: ContentDraftPublic }) {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [publicationUrl, setPublicationUrl] = useState(draft.target_url ?? "");

  function invalidate() {
    queryClient.invalidateQueries({
      queryKey: ["content-draft", workspaceId, draft.id],
    });
    queryClient.invalidateQueries({ queryKey: ["content-drafts", workspaceId] });
  }

  const approve = useMutation({
    mutationFn: () => approveContentDraft(workspaceId!, draft.id),
    onSuccess: invalidate,
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not approve."),
  });
  const reject = useMutation({
    mutationFn: () => rejectContentDraft(workspaceId!, draft.id),
    onSuccess: invalidate,
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not reject."),
  });
  const publish = useMutation({
    mutationFn: () =>
      publishContentDraft(workspaceId!, draft.id, publicationUrl || undefined),
    onSuccess: invalidate,
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not publish."),
  });
  const archive = useMutation({
    mutationFn: () => archiveContentDraft(workspaceId!, draft.id),
    onSuccess: () => {
      invalidate();
      navigate("/content");
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not archive."),
  });

  return (
    <Card>
      <CardHeader
        title="Actions"
        subtitle="Approve gates publication; only Admins can approve or publish."
      />
      {error ? (
        <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {draft.status === "draft" || draft.status === "rejected" ? (
          <Button onClick={() => approve.mutate()} disabled={approve.isPending}>
            {approve.isPending ? "Approving…" : "Approve"}
          </Button>
        ) : null}
        {(draft.status === "draft" || draft.status === "approved") ? (
          <Button
            variant="ghost"
            onClick={() => reject.mutate()}
            disabled={reject.isPending}
          >
            {reject.isPending ? "Rejecting…" : "Reject"}
          </Button>
        ) : null}
        {draft.status !== "archived" ? (
          <Button
            variant="ghost"
            onClick={() => archive.mutate()}
            disabled={archive.isPending}
          >
            {archive.isPending ? "Archiving…" : "Archive"}
          </Button>
        ) : null}
      </div>

      {draft.status === "approved" ? (
        <div className="mt-4 rounded-xl border border-slate-200 p-3">
          <p className="text-sm font-medium text-slate-text">Publish</p>
          <p className="mt-1 text-xs text-slate-500">
            Optional: paste the URL where this lives once you've pushed it. The
            record is marked published either way.
          </p>
          <div className="mt-2 flex flex-col gap-2 sm:flex-row">
            <input
              type="url"
              value={publicationUrl}
              onChange={(e) => setPublicationUrl(e.target.value)}
              placeholder="https://example.com/blog/post"
              className="flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
            />
            <Button
              onClick={() => publish.mutate()}
              disabled={publish.isPending}
            >
              {publish.isPending ? "Publishing…" : "Mark published"}
            </Button>
          </div>
        </div>
      ) : null}

      {draft.status === "published" && draft.target_url ? (
        <p className="mt-3 text-sm text-slate-500">
          Live at:{" "}
          <a
            href={draft.target_url}
            target="_blank"
            rel="noreferrer"
            className="text-grape-700 hover:text-grape-800"
          >
            {draft.target_url}
          </a>
        </p>
      ) : null}
    </Card>
  );
}
