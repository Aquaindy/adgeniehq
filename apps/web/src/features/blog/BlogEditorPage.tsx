import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  type DragEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import {
  aiAssist,
  approveBlogPost,
  archiveBlogPost,
  getBlogPost,
  publishBlogPost,
  updateBlogPost,
  uploadBlogImage,
} from "@/lib/blog";
import { renderMarkdown } from "@/lib/markdown";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type {
  AiAssistAction,
  AiAssistResponse,
  ContentDraftPublic,
} from "@/types/api";


type TabId = "editor" | "ai" | "settings";


/**
 * Three-tab post editor:
 *
 *   - Editor    : title + body (markdown) with live preview, drag-drop image
 *                 upload, cover-image picker.
 *   - AI Assist : action buttons (outline / expand / refine / suggest title /
 *                 suggest meta) hooked to /content-drafts/{id}/ai-assist.
 *                 Returned suggestions render as cards with Insert / Replace
 *                 / Discard so the operator stays in control.
 *   - Settings  : slug, excerpt, cover image, keywords, meta_title +
 *                 meta_description, target_url. Lifecycle buttons
 *                 (approve / publish / archive) sit at the bottom.
 */
export function BlogEditorPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const { draftId } = useParams<{ draftId: string }>();
  if (!workspaceId || !draftId) {
    return <div className="text-sm text-slate-500">Loading…</div>;
  }
  return <BlogEditorPageInner workspaceId={workspaceId} draftId={draftId} />;
}


function BlogEditorPageInner({
  workspaceId,
  draftId,
}: {
  workspaceId: string;
  draftId: string;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const post = useQuery<ContentDraftPublic>({
    queryKey: ["blog-post", workspaceId, draftId],
    queryFn: () => getBlogPost(workspaceId, draftId),
  });

  const [tab, setTab] = useState<TabId>("editor");
  const [draft, setDraft] = useState<ContentDraftPublic | null>(null);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Hydrate local draft from server, but only the first time. Subsequent
  // refetches don't clobber unsaved local edits.
  useEffect(() => {
    if (post.data && draft === null) {
      setDraft(post.data);
    }
  }, [post.data, draft]);

  const save = useMutation({
    mutationFn: (patch: Partial<ContentDraftPublic>) =>
      updateBlogPost(workspaceId, draftId, patch),
    onSuccess: (saved) => {
      setDraft(saved);
      setSavedAt(new Date());
      void queryClient.invalidateQueries({
        queryKey: ["blog-post", workspaceId, draftId],
      });
      void queryClient.invalidateQueries({ queryKey: ["blog-posts", workspaceId] });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    },
  });

  const approve = useMutation({
    mutationFn: () => approveBlogPost(workspaceId, draftId),
    onSuccess: (saved) => {
      setDraft(saved);
      void queryClient.invalidateQueries({
        queryKey: ["blog-post", workspaceId, draftId],
      });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Could not approve.");
    },
  });

  const publish = useMutation({
    mutationFn: () => publishBlogPost(workspaceId, draftId),
    onSuccess: (saved) => {
      setDraft(saved);
      void queryClient.invalidateQueries({
        queryKey: ["blog-post", workspaceId, draftId],
      });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Could not publish.");
    },
  });

  const archive = useMutation({
    mutationFn: () => archiveBlogPost(workspaceId, draftId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["blog-posts", workspaceId] });
      navigate("/blog/posts");
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Could not archive.");
    },
  });

  if (post.isLoading || draft === null) {
    return <div className="text-sm text-slate-400">Loading post…</div>;
  }

  function patchDraft(patch: Partial<ContentDraftPublic>) {
    setDraft((d) => (d ? { ...d, ...patch } : d));
  }

  function saveNow() {
    if (!draft) return;
    setError(null);
    save.mutate({
      title: draft.title,
      body: draft.body,
      slug: draft.slug ?? undefined,
      excerpt: draft.excerpt ?? undefined,
      image_url: draft.image_url ?? undefined,
      keywords: draft.keywords ?? undefined,
      seo_metadata: draft.seo_metadata ?? undefined,
      target_url: draft.target_url ?? undefined,
    });
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link
            to="/blog/posts"
            className="text-xs font-medium text-grape-700 hover:text-grape-800"
          >
            ← All posts
          </Link>
          <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">
            {draft.title || "(untitled)"}
          </h1>
          <p className="mt-1 text-xs uppercase tracking-wider text-slate-400">
            {draft.status} ·{" "}
            {savedAt
              ? `saved ${savedAt.toLocaleTimeString()}`
              : `last updated ${new Date(draft.updated_at).toLocaleString()}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            onClick={() => archive.mutate()}
            disabled={archive.isPending || draft.status === "archived"}
          >
            Archive
          </Button>
          {draft.status === "draft" ? (
            <Button onClick={() => approve.mutate()} disabled={approve.isPending}>
              {approve.isPending ? "Approving…" : "Approve"}
            </Button>
          ) : null}
          {draft.status === "approved" ? (
            <Button onClick={() => publish.mutate()} disabled={publish.isPending}>
              {publish.isPending ? "Publishing…" : "Publish"}
            </Button>
          ) : null}
          <Button onClick={saveNow} disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      </header>

      {error ? (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </div>
      ) : null}

      <Tabs current={tab} onChange={setTab} />

      {tab === "editor" ? (
        <EditorTab
          workspaceId={workspaceId}
          draft={draft}
          onPatch={patchDraft}
        />
      ) : null}
      {tab === "ai" ? (
        <AiAssistantTab
          workspaceId={workspaceId}
          draftId={draftId}
          draft={draft}
          onPatch={patchDraft}
        />
      ) : null}
      {tab === "settings" ? (
        <SettingsTab
          workspaceId={workspaceId}
          draft={draft}
          onPatch={patchDraft}
        />
      ) : null}
    </div>
  );
}


/* ------------------------------------------------------------------------ */
/* Tabs                                                                     */
/* ------------------------------------------------------------------------ */


function Tabs({
  current,
  onChange,
}: {
  current: TabId;
  onChange: (id: TabId) => void;
}) {
  const tabs: { id: TabId; label: string }[] = [
    { id: "editor", label: "Editor" },
    { id: "ai", label: "AI Assistant" },
    { id: "settings", label: "Settings" },
  ];
  return (
    <div className="border-b border-slate-100">
      <nav className="flex gap-1">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => onChange(t.id)}
            className={cn(
              "rounded-t-xl px-4 py-2 text-sm font-medium transition",
              current === t.id
                ? "border border-b-white border-slate-100 bg-white text-grape-700"
                : "text-slate-500 hover:text-ink",
            )}
          >
            {t.label}
          </button>
        ))}
      </nav>
    </div>
  );
}


/* ------------------------------------------------------------------------ */
/* Editor tab                                                               */
/* ------------------------------------------------------------------------ */


function EditorTab({
  workspaceId,
  draft,
  onPatch,
}: {
  workspaceId: string;
  draft: ContentDraftPublic;
  onPatch: (p: Partial<ContentDraftPublic>) => void;
}) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  async function handleUpload(file: File) {
    setUploading(true);
    setUploadError(null);
    try {
      const result = await uploadBlogImage(workspaceId, file);
      const snippet = `\n\n![${file.name.replace(/\.[^.]+$/, "")}](${result.url})\n\n`;
      const ta = textareaRef.current;
      const cursor = ta?.selectionStart ?? draft.body.length;
      const next =
        draft.body.slice(0, cursor) + snippet + draft.body.slice(cursor);
      onPatch({ body: next });
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  function onDrop(e: DragEvent<HTMLTextAreaElement>) {
    e.preventDefault();
    const file = e.dataTransfer?.files?.[0];
    if (file && file.type.startsWith("image/")) {
      void handleUpload(file);
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader
          title="Compose"
          subtitle="Markdown supported. Drop an image into the body to upload + insert."
          action={
            <ImageUploadButton
              uploading={uploading}
              onPicked={(f) => void handleUpload(f)}
            />
          }
        />
        <div className="mt-3 flex flex-col gap-3">
          <input
            value={draft.title}
            onChange={(e) => onPatch({ title: e.target.value })}
            placeholder="Post title"
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-lg font-semibold text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
          />
          <textarea
            ref={textareaRef}
            value={draft.body}
            onChange={(e) => onPatch({ body: e.target.value })}
            onDrop={onDrop}
            onDragOver={(e) => e.preventDefault()}
            rows={20}
            className="min-h-[28rem] rounded-xl border border-slate-200 bg-white px-3 py-2 font-mono text-sm leading-relaxed text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
          />
          {uploadError ? (
            <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
              {uploadError}
            </div>
          ) : null}
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Live preview"
          subtitle="What readers will see on /blog/{slug}."
        />
        <div className="mt-3 max-h-[36rem] overflow-y-auto pr-1">
          <h2 className="text-2xl font-semibold tracking-tight text-ink">
            {draft.title || "Untitled post"}
          </h2>
          {draft.image_url ? (
            <img
              src={draft.image_url}
              alt=""
              loading="lazy"
              className="mt-4 w-full rounded-2xl border border-slate-100"
            />
          ) : null}
          <div className="mt-2">{renderMarkdown(draft.body)}</div>
        </div>
      </Card>
    </div>
  );
}


function ImageUploadButton({
  uploading,
  onPicked,
}: {
  uploading: boolean;
  onPicked: (file: File) => void;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onPicked(file);
          e.target.value = "";
        }}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={uploading}
        className="rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
      >
        {uploading ? "Uploading…" : "Insert image"}
      </button>
    </>
  );
}


/* ------------------------------------------------------------------------ */
/* AI Assistant tab                                                         */
/* ------------------------------------------------------------------------ */


type Suggestion = {
  id: number;
  action: AiAssistAction;
  source: "llm" | "deterministic";
  rendered: string; // human-readable text we'll show + insert
};


function AiAssistantTab({
  workspaceId,
  draftId,
  draft,
  onPatch,
}: {
  workspaceId: string;
  draftId: string;
  draft: ContentDraftPublic;
  onPatch: (p: Partial<ContentDraftPublic>) => void;
}) {
  const [selection, setSelection] = useState("");
  const [instructions, setInstructions] = useState("");
  const [pending, setPending] = useState<AiAssistAction | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [error, setError] = useState<string | null>(null);
  const idRef = useRef(0);

  async function run(action: AiAssistAction) {
    setPending(action);
    setError(null);
    try {
      const resp = await aiAssist(
        workspaceId,
        draftId,
        action,
        selection || null,
        instructions || null,
      );
      const rendered = renderSuggestion(resp);
      setSuggestions((prev) => [
        { id: ++idRef.current, action, source: resp.source, rendered },
        ...prev,
      ]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "AI request failed.");
    } finally {
      setPending(null);
    }
  }

  function applyAsAppend(text: string) {
    const sep = draft.body.endsWith("\n") ? "\n" : "\n\n";
    onPatch({ body: (draft.body || "") + sep + text });
  }

  function applyAsReplaceTitle(title: string) {
    onPatch({ title });
  }

  function applyAsMeta(metaTitle: string, metaDescription: string) {
    const next = {
      ...(draft.seo_metadata ?? {}),
      meta_title: metaTitle,
      meta_description: metaDescription,
    };
    onPatch({ seo_metadata: next });
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader
          title="Ask the assistant"
          subtitle="Each action is metered against your workspace's LLM budget. With no LLM configured, you'll see a deterministic stub instead of a hallucination — clearly tagged."
        />
        <div className="mt-3 flex flex-col gap-3">
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-slate-text">
              Selection (required for Expand / Refine)
            </span>
            <textarea
              rows={3}
              value={selection}
              onChange={(e) => setSelection(e.target.value)}
              placeholder="Paste the heading or paragraph you want the assistant to work on."
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-slate-text">
              Instructions (optional)
            </span>
            <textarea
              rows={2}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder='e.g. "more concrete examples", "tighten — half the length"'
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <ActionButton label="Outline" busy={pending === "outline"} onClick={() => run("outline")} />
            <ActionButton label="Expand selection" busy={pending === "expand"} onClick={() => run("expand")} />
            <ActionButton label="Refine selection" busy={pending === "refine"} onClick={() => run("refine")} />
            <ActionButton label="Suggest title" busy={pending === "suggest_title"} onClick={() => run("suggest_title")} />
            <ActionButton label="Suggest meta" busy={pending === "suggest_meta"} onClick={() => run("suggest_meta")} />
          </div>
          {error ? (
            <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
              {error}
            </div>
          ) : null}
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Suggestions"
          subtitle="Newest first. Insert / replace flows keep the body and AI side-by-side."
        />
        {suggestions.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">
            No suggestions yet. Pick an action on the left.
          </p>
        ) : (
          <ul className="mt-3 flex flex-col gap-3">
            {suggestions.map((s) => (
              <SuggestionCard
                key={s.id}
                s={s}
                onAppend={applyAsAppend}
                onReplaceTitle={applyAsReplaceTitle}
                onApplyMeta={applyAsMeta}
                onDiscard={() =>
                  setSuggestions((prev) => prev.filter((p) => p.id !== s.id))
                }
              />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}


function ActionButton({
  label,
  busy,
  onClick,
}: {
  label: string;
  busy: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className="rounded-xl border border-grape-200 bg-grape-50 px-3 py-1.5 text-xs font-semibold text-grape-700 transition hover:bg-grape-100 disabled:opacity-50"
    >
      {busy ? "Thinking…" : label}
    </button>
  );
}


function renderSuggestion(resp: AiAssistResponse): string {
  const r = resp.result as Record<string, unknown>;
  switch (resp.action) {
    case "outline": {
      const sections = (r.sections as { heading: string; summary: string }[]) ?? [];
      return sections
        .map((s) => `## ${s.heading}\n\n${s.summary}`)
        .join("\n\n");
    }
    case "expand":
      return (r.paragraph as string) ?? "";
    case "refine":
      return (r.passage as string) ?? "";
    case "suggest_title": {
      const candidates = (r.candidates as string[]) ?? [];
      return candidates.map((c, i) => `${i + 1}. ${c}`).join("\n");
    }
    case "suggest_meta": {
      const mt = (r.meta_title as string) ?? "";
      const md = (r.meta_description as string) ?? "";
      return `meta_title: ${mt}\nmeta_description: ${md}`;
    }
  }
}


function SuggestionCard({
  s,
  onAppend,
  onReplaceTitle,
  onApplyMeta,
  onDiscard,
}: {
  s: Suggestion;
  onAppend: (text: string) => void;
  onReplaceTitle: (title: string) => void;
  onApplyMeta: (metaTitle: string, metaDescription: string) => void;
  onDiscard: () => void;
}) {
  return (
    <li className="rounded-xl border border-slate-100 bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-medium uppercase tracking-wider text-grape-700">
          {s.action.replace("_", " ")}
        </span>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider",
            s.source === "llm"
              ? "bg-grape-100 text-grape-700"
              : "bg-amber-50 text-amber-700",
          )}
        >
          {s.source === "llm" ? "AI" : "stub (no LLM key)"}
        </span>
      </div>
      <pre className="mt-3 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-lg bg-cloud px-3 py-2 font-mono text-xs text-slate-700">
        {s.rendered}
      </pre>
      <div className="mt-3 flex flex-wrap gap-2">
        {s.action === "suggest_title" ? (
          <Button
            variant="secondary"
            onClick={() => {
              const first = s.rendered.split("\n")[0]?.replace(/^\d+\.\s+/, "");
              if (first) onReplaceTitle(first);
            }}
          >
            Use first as title
          </Button>
        ) : s.action === "suggest_meta" ? (
          <Button
            variant="secondary"
            onClick={() => {
              const mt = /meta_title: (.*)/.exec(s.rendered)?.[1] ?? "";
              const md = /meta_description: ([\s\S]*)/.exec(s.rendered)?.[1] ?? "";
              onApplyMeta(mt, md);
            }}
          >
            Apply to settings
          </Button>
        ) : (
          <Button variant="secondary" onClick={() => onAppend(s.rendered)}>
            Append to body
          </Button>
        )}
        <Button variant="secondary" onClick={onDiscard}>
          Discard
        </Button>
      </div>
    </li>
  );
}


/* ------------------------------------------------------------------------ */
/* Settings tab                                                             */
/* ------------------------------------------------------------------------ */


function SettingsTab({
  workspaceId,
  draft,
  onPatch,
}: {
  workspaceId: string;
  draft: ContentDraftPublic;
  onPatch: (p: Partial<ContentDraftPublic>) => void;
}) {
  const [coverUploading, setCoverUploading] = useState(false);
  const [coverError, setCoverError] = useState<string | null>(null);
  const seo = (draft.seo_metadata ?? {}) as Record<string, string | undefined>;
  const keywordsString = useMemo(
    () => (draft.keywords ?? []).join(", "),
    [draft.keywords],
  );

  async function handleCoverUpload(file: File) {
    setCoverError(null);
    setCoverUploading(true);
    try {
      const result = await uploadBlogImage(workspaceId, file);
      onPatch({ image_url: result.url });
    } catch (err) {
      setCoverError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setCoverUploading(false);
    }
  }

  function patchSeo(patch: Record<string, string>) {
    onPatch({ seo_metadata: { ...(draft.seo_metadata ?? {}), ...patch } });
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader
          title="URL + summary"
          subtitle="Slug auto-fills on publish if blank."
        />
        <div className="mt-3 flex flex-col gap-3 text-sm">
          <Field
            label="Slug"
            value={draft.slug ?? ""}
            onChange={(v) => onPatch({ slug: v })}
            mono
            placeholder="my-post"
          />
          <Field
            label="Excerpt"
            value={draft.excerpt ?? ""}
            onChange={(v) => onPatch({ excerpt: v })}
            multiline
            placeholder="Short summary for cards + RSS. Auto-derived on publish if left blank."
          />
          <Field
            label="Target URL (legacy CMS publish)"
            value={draft.target_url ?? ""}
            onChange={(v) => onPatch({ target_url: v })}
            placeholder="https://..."
          />
          <Field
            label="Keywords (comma-separated)"
            value={keywordsString}
            onChange={(v) =>
              onPatch({
                keywords: v
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
            placeholder="paid-ads, conversion"
          />
        </div>
      </Card>

      <Card>
        <CardHeader title="Cover image" subtitle="Shown on cards + the post header." />
        <div className="mt-3 flex flex-col gap-3">
          {draft.image_url ? (
            <img
              src={draft.image_url}
              alt=""
              className="w-full rounded-xl border border-slate-100"
              loading="lazy"
            />
          ) : (
            <div className="flex aspect-[16/9] w-full items-center justify-center rounded-xl border border-dashed border-slate-200 bg-cloud text-xs text-slate-400">
              No cover image yet
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <CoverUploadButton
              uploading={coverUploading}
              onPicked={(f) => void handleCoverUpload(f)}
            />
            {draft.image_url ? (
              <Button
                variant="secondary"
                onClick={() => onPatch({ image_url: null })}
              >
                Remove
              </Button>
            ) : null}
          </div>
          {coverError ? (
            <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
              {coverError}
            </div>
          ) : null}
        </div>
      </Card>

      <Card className="lg:col-span-2">
        <CardHeader title="SEO metadata" subtitle="Used in <head> + OG / Twitter cards." />
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <Field
            label="Meta title (≤60 chars)"
            value={seo.meta_title ?? ""}
            onChange={(v) => patchSeo({ meta_title: v })}
          />
          <Field
            label="Meta description (≤155 chars)"
            value={seo.meta_description ?? ""}
            onChange={(v) => patchSeo({ meta_description: v })}
            multiline
          />
          <Field
            label="OG image URL"
            value={seo.og_image ?? ""}
            onChange={(v) => patchSeo({ og_image: v })}
          />
          <Field
            label="Canonical URL"
            value={seo.canonical_url ?? ""}
            onChange={(v) => patchSeo({ canonical_url: v })}
          />
        </div>
      </Card>
    </div>
  );
}


function CoverUploadButton({
  uploading,
  onPicked,
}: {
  uploading: boolean;
  onPicked: (file: File) => void;
}) {
  const ref = useRef<HTMLInputElement | null>(null);
  return (
    <>
      <input
        ref={ref}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onPicked(f);
          e.target.value = "";
        }}
      />
      <Button onClick={() => ref.current?.click()} disabled={uploading}>
        {uploading ? "Uploading…" : "Upload cover image"}
      </Button>
    </>
  );
}


function Field({
  label,
  value,
  onChange,
  multiline,
  mono,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  multiline?: boolean;
  mono?: boolean;
  placeholder?: string;
}) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      <span className="font-medium text-slate-text">{label}</span>
      {multiline ? (
        <textarea
          rows={3}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
        />
      ) : (
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className={cn(
            "rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200",
            mono && "font-mono",
          )}
        />
      )}
    </label>
  );
}
