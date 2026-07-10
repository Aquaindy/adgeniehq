import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { UsageMeter } from "@/components/UsageMeter";
import { ApiError } from "@/lib/api-client";
import {
  generateContentDraftImage,
  resolveUploadUrl,
} from "@/lib/content-drafts";
import {
  composeForClipboard,
  generateSocialPack,
  listSocialPlatforms,
  readVideoScript,
} from "@/lib/social-content";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type {
  ContentDraftPublic,
  SocialPackResponse,
  SocialPlatformPublic,
} from "@/types/api";

export function SocialStudioPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const platforms = useQuery({
    queryKey: ["social-platforms", workspaceId],
    queryFn: () => listSocialPlatforms(workspaceId!),
    enabled: !!workspaceId,
    // Static reference data — no need to refetch on every focus.
    staleTime: Infinity,
  });

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <header>
        <p className="text-xs uppercase tracking-wider text-grape-700">Content</p>
        <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">
          Social studio
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Turn one topic into platform-native posts and short-form video scripts,
          each with its own keywords and hashtags. Drafts never auto-publish — an
          Admin must approve.
        </p>
      </header>

      <UsageMeter resource="content_drafts" />

      {platforms.isLoading ? (
        <p className="text-sm text-slate-400">Loading platforms…</p>
      ) : platforms.error ? (
        <Card>
          <p className="text-sm text-red-700">
            {platforms.error instanceof Error
              ? platforms.error.message
              : "Could not load platforms."}
          </p>
        </Card>
      ) : platforms.data && platforms.data.length > 0 ? (
        <GenerateForm platforms={platforms.data} />
      ) : (
        <EmptyState
          title="No platforms available"
          description="The social platform catalog returned nothing. This is a configuration problem — contact support."
        />
      )}
    </div>
  );
}

function GenerateForm({ platforms }: { platforms: SocialPlatformPublic[] }) {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();

  const [topic, setTopic] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [audience, setAudience] = useState("");
  const [targetUrl, setTargetUrl] = useState("");
  const [cta, setCta] = useState("");
  const [selected, setSelected] = useState<string[]>(["linkedin", "x"]);
  const [error, setError] = useState<string | null>(null);
  const [pack, setPack] = useState<SocialPackResponse | null>(null);

  const posts = useMemo(
    () => platforms.filter((p) => p.format === "post"),
    [platforms],
  );
  const videos = useMemo(
    () => platforms.filter((p) => p.format === "video_script"),
    [platforms],
  );

  const mut = useMutation({
    mutationFn: () =>
      generateSocialPack(workspaceId!, {
        topic: topic.trim() || null,
        source_url: sourceUrl.trim() || null,
        platforms: selected,
        audience: audience || null,
        target_url: targetUrl || null,
        call_to_action: cta || null,
      }),
    onSuccess: (data) => {
      setPack(data);
      queryClient.invalidateQueries({
        queryKey: ["content-drafts", workspaceId],
      });
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not generate."),
  });

  function toggle(slug: string) {
    setSelected((prev) =>
      prev.includes(slug) ? prev.filter((s) => s !== slug) : [...prev, slug],
    );
  }

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    if (!topic.trim() && !sourceUrl.trim()) {
      setError("Provide a topic or a source URL to generate from.");
      return;
    }
    if (selected.length === 0) {
      setError("Select at least one platform.");
      return;
    }
    setPack(null);
    mut.mutate();
  }

  return (
    <>
      <Card>
        <CardHeader
          title="Generate a social pack"
          subtitle="Start from a topic or a web link — one tailored draft per platform out. The agent uses your configured LLM if available; otherwise a deterministic skeleton."
        />
        <form className="mt-4 flex flex-col gap-4" onSubmit={onSubmit}>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-slate-text">Topic or keyword</span>
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g. Why first-touch attribution misleads B2B teams"
              className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
            />
          </label>

          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-slate-text">
              …or repurpose a web link
            </span>
            <input
              type="url"
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              placeholder="https://yourblog.com/an-article-to-turn-into-posts"
              className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
            />
            <span className="text-xs text-slate-400">
              We fetch the page and turn its content into posts and scripts. Leave
              the topic blank to use the page's own title, or set both to angle it.
            </span>
          </label>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="font-medium text-slate-text">
                Audience (optional)
              </span>
              <input
                type="text"
                value={audience}
                onChange={(e) => setAudience(e.target.value)}
                placeholder="e.g. demand-gen leads at SaaS companies"
                className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
              />
            </label>
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="font-medium text-slate-text">
                Link to promote (optional)
              </span>
              <input
                type="url"
                value={targetUrl}
                onChange={(e) => setTargetUrl(e.target.value)}
                placeholder="https://example.com/pricing"
                className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
              />
            </label>
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="font-medium text-slate-text">
                Call to action (optional)
              </span>
              <input
                type="text"
                value={cta}
                onChange={(e) => setCta(e.target.value)}
                placeholder="e.g. Follow for weekly teardowns"
                className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
              />
            </label>
          </div>

          <PlatformGroup
            heading="Posts"
            platforms={posts}
            selected={selected}
            onToggle={toggle}
          />
          <PlatformGroup
            heading="Reels & Shorts"
            platforms={videos}
            selected={selected}
            onToggle={toggle}
          />

          {error ? (
            <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={mut.isPending || selected.length === 0}>
              {mut.isPending
                ? `Generating ${selected.length}…`
                : `Generate ${selected.length} draft${selected.length === 1 ? "" : "s"}`}
            </Button>
            <p className="text-xs text-slate-400">
              Each platform costs one content-draft credit.
            </p>
          </div>
        </form>
      </Card>

      {pack ? (
        <PackResults
          pack={pack}
          platforms={platforms}
          workspaceId={workspaceId!}
          onDraftUpdated={(updated) =>
            setPack((prev) =>
              prev
                ? {
                    ...prev,
                    drafts: prev.drafts.map((d) =>
                      d.id === updated.id ? updated : d,
                    ),
                  }
                : prev,
            )
          }
        />
      ) : null}
    </>
  );
}

function PlatformGroup({
  heading,
  platforms,
  selected,
  onToggle,
}: {
  heading: string;
  platforms: SocialPlatformPublic[];
  selected: string[];
  onToggle: (slug: string) => void;
}) {
  if (platforms.length === 0) return null;
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-sm font-medium text-slate-text">{heading}</legend>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {platforms.map((p) => {
          const on = selected.includes(p.slug);
          return (
            <button
              key={p.slug}
              type="button"
              onClick={() => onToggle(p.slug)}
              aria-pressed={on}
              className={cn(
                "flex flex-col items-start gap-1 rounded-xl border px-3 py-2.5 text-left transition",
                on
                  ? "border-grape bg-grape-50 ring-2 ring-grape-200"
                  : "border-slate-200 bg-surface hover:bg-grape-50",
              )}
            >
              <span className="text-sm font-medium text-ink">{p.label}</span>
              <span className="text-xs text-slate-500">
                {p.format === "video_script"
                  ? `${p.duration_min_seconds}-${p.duration_max_seconds}s · ${p.aspect_ratio}`
                  : p.hard_char_limit
                    ? `up to ${p.hard_char_limit.toLocaleString()} chars`
                    : "long-form"}
                {" · "}
                {p.hashtag_max === 0
                  ? "no hashtags"
                  : `${p.hashtag_min}-${p.hashtag_max} hashtags`}
              </span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

function PackResults({
  pack,
  platforms,
  workspaceId,
  onDraftUpdated,
}: {
  pack: SocialPackResponse;
  platforms: SocialPlatformPublic[];
  workspaceId: string;
  onDraftUpdated: (draft: ContentDraftPublic) => void;
}) {
  const byslug = useMemo(
    () => new Map(platforms.map((p) => [p.slug, p])),
    [platforms],
  );
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkError, setBulkError] = useState<string | null>(null);

  // How many drafts still lack an image — drives the "generate all" affordance.
  const missing = pack.drafts.filter((d) => !d.image_url);

  async function generateAll() {
    setBulkBusy(true);
    setBulkError(null);
    // Sequential, not parallel: each image is a metered call, and serial keeps
    // the credit spend legible and avoids hammering the provider.
    for (const draft of missing) {
      try {
        const updated = await generateContentDraftImage(workspaceId, draft.id);
        onDraftUpdated(updated);
      } catch (err) {
        setBulkError(
          err instanceof ApiError ? err.message : "Some images could not be generated.",
        );
        break;
      }
    }
    setBulkBusy(false);
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-ink">
          {pack.drafts.length} draft{pack.drafts.length === 1 ? "" : "s"} for “
          {pack.topic}”
        </h2>
        {missing.length > 0 ? (
          <Button type="button" variant="secondary" onClick={generateAll} disabled={bulkBusy}>
            {bulkBusy
              ? "Generating images…"
              : `Generate images for ${missing.length} draft${missing.length === 1 ? "" : "s"}`}
          </Button>
        ) : null}
      </div>
      {bulkError ? (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{bulkError}</p>
      ) : null}
      {pack.drafts.map((draft) => (
        <DraftCard
          key={draft.id}
          draft={draft}
          platform={draft.platform ? byslug.get(draft.platform) : undefined}
          workspaceId={workspaceId}
          onUpdated={onDraftUpdated}
        />
      ))}
    </section>
  );
}

function DraftCard({
  draft,
  platform,
  workspaceId,
  onUpdated,
}: {
  draft: ContentDraftPublic;
  platform?: SocialPlatformPublic;
  workspaceId: string;
  onUpdated: (draft: ContentDraftPublic) => void;
}) {
  const [copied, setCopied] = useState(false);
  const script = readVideoScript(draft);

  const imageMut = useMutation({
    mutationFn: () => generateContentDraftImage(workspaceId, draft.id),
    onSuccess: (updated) => onUpdated(updated),
  });

  // The platform counts body + hashtags together, so surface the composed
  // number rather than the body length alone.
  const composed = draft.seo_metadata?.composed_character_count as
    | number
    | undefined;
  const limit = platform?.hard_char_limit ?? null;
  const overLimit = limit != null && composed != null && composed > limit;

  async function copy() {
    await navigator.clipboard.writeText(composeForClipboard(draft));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="pill pill-grape">{platform?.label ?? draft.platform}</span>
          <span className="pill bg-slate-50 text-slate-500">
            {draft.type === "short_video_script" ? "Script" : "Post"}
          </span>
          {draft.model_used ? (
            <span className="pill bg-grape-50 text-grape-700">
              {draft.model_used}
            </span>
          ) : (
            <span className="pill bg-amber-50 text-amber-700">deterministic</span>
          )}
          {limit != null && composed != null ? (
            <span
              className={cn(
                "pill",
                overLimit
                  ? "pill-danger"
                  : "bg-slate-50 text-slate-500",
              )}
            >
              {composed.toLocaleString()}/{limit.toLocaleString()} chars
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="secondary"
            onClick={() => imageMut.mutate()}
            disabled={imageMut.isPending}
          >
            {imageMut.isPending
              ? "Generating…"
              : draft.image_url
                ? "Regenerate image"
                : "Generate image"}
          </Button>
          <Button type="button" variant="secondary" onClick={copy}>
            {copied ? "Copied" : "Copy"}
          </Button>
          <Link
            to={`/content/${draft.id}`}
            className="text-sm font-medium text-grape hover:underline"
          >
            Open
          </Link>
        </div>
      </div>

      {imageMut.error ? (
        <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
          {imageMut.error instanceof ApiError
            ? imageMut.error.message
            : "Could not generate the image."}
        </p>
      ) : null}

      {draft.image_url ? (
        <img
          src={resolveUploadUrl(draft.image_url)}
          alt={`Creative for the ${platform?.label ?? draft.platform ?? ""} draft`}
          className="mt-3 w-full rounded-xl border border-slate-200 object-cover"
          loading="lazy"
        />
      ) : null}

      {overLimit ? (
        <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
          This draft exceeds {platform?.label}'s limit once hashtags are added.
          Trim it before posting.
        </p>
      ) : null}

      {typeof draft.seo_metadata?.source_url === "string" ? (
        <p className="mt-2 text-xs text-slate-400">
          Repurposed from{" "}
          <a
            href={draft.seo_metadata.source_url as string}
            target="_blank"
            rel="noreferrer"
            className="text-grape hover:underline"
          >
            {(draft.seo_metadata.source_url as string).replace(/^https?:\/\//, "")}
          </a>
        </p>
      ) : null}

      {script ? (
        <VideoScriptView script={script} />
      ) : (
        <p className="mt-3 whitespace-pre-wrap text-sm text-slate-text">
          {draft.body}
        </p>
      )}

      {draft.hashtags && draft.hashtags.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {draft.hashtags.map((tag) => (
            <span key={tag} className="pill bg-grape-50 text-grape-700">
              {tag}
            </span>
          ))}
        </div>
      ) : null}

      {draft.keywords && draft.keywords.length > 0 ? (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-slate-400">Keywords:</span>
          {draft.keywords.map((kw) => (
            <span key={kw} className="pill bg-slate-50 text-slate-500">
              {kw}
            </span>
          ))}
        </div>
      ) : null}
    </Card>
  );
}

function VideoScriptView({
  script,
}: {
  script: NonNullable<ReturnType<typeof readVideoScript>>;
}) {
  const [low, high] = script.target_duration_seconds ?? [20, 60];
  return (
    <div className="mt-3 flex flex-col gap-3">
      <div className="rounded-xl bg-grape-50 px-3 py-2">
        <p className="text-xs font-medium uppercase tracking-wide text-grape-700">
          Hook · 0-2s
        </p>
        <p className="mt-0.5 text-sm text-ink">{script.hook}</p>
      </div>

      <ol className="flex flex-col gap-2">
        {script.beats.map((beat, i) => (
          <li
            key={i}
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
          >
            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
              Beat {i + 1}
            </p>
            <p className="mt-1 text-slate-text">{beat.narration}</p>
            {beat.on_screen_text ? (
              <p className="mt-1 text-xs text-slate-500">
                <span className="font-medium">On-screen:</span>{" "}
                {beat.on_screen_text}
              </p>
            ) : null}
            {beat.visual ? (
              <p className="mt-0.5 text-xs text-slate-500">
                <span className="font-medium">Visual:</span> {beat.visual}
              </p>
            ) : null}
          </li>
        ))}
      </ol>

      <div className="rounded-xl border border-slate-200 px-3 py-2">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
          CTA
        </p>
        <p className="mt-0.5 text-sm text-slate-text">{script.cta}</p>
      </div>

      <p className="text-xs text-slate-400">
        {script.aspect_ratio} vertical · {low}-{high}s
      </p>
    </div>
  );
}
