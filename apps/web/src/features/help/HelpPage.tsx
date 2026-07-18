import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Card } from "@/components/ui/Card";
import {
  getHelpAudio,
  getHelpTopic,
  getHelpTopics,
  startHelpAudio,
} from "@/lib/help";
import { renderMarkdown } from "@/lib/markdown";
import { cn } from "@/lib/utils";
import type { HelpTopicSummary } from "@/types/api";

/**
 * Help / Knowledge Base. Two-pane: a category-grouped topic list on the left,
 * and the selected article on the right with Text / Audio / Video tabs.
 *
 * - Text: the article markdown.
 * - Audio: ElevenLabs narration (generate-on-first-play + cache). Degrades to a
 *   "coming soon" state when the platform key isn't configured.
 * - Video: Coming Soon.
 */
export function HelpPage() {
  const params = useParams();
  const topics = useQuery({ queryKey: ["help-topics"], queryFn: getHelpTopics });

  const topicList = topics.data ?? [];
  const selectedId =
    params.topicId && topicList.some((t) => t.id === params.topicId)
      ? params.topicId
      : topicList[0]?.id;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold text-ink sm:text-3xl">Help &amp; Knowledge Base</h1>
        <p className="mt-2 text-sm text-slate-500">
          Learn each part of AdGenieHQ. Choose how you take it in — read it, listen
          to the narration, or watch a walkthrough (coming soon).
        </p>
      </header>

      {topics.isLoading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : topicList.length === 0 ? (
        <p className="text-sm text-slate-400">No help topics available yet.</p>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[16rem,1fr]">
          <TopicNav topics={topicList} selectedId={selectedId} />
          {selectedId ? <HelpArticle key={selectedId} topicId={selectedId} /> : null}
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Topic navigation (grouped by category)                                     */
/* -------------------------------------------------------------------------- */

function TopicNav({
  topics,
  selectedId,
}: {
  topics: HelpTopicSummary[];
  selectedId?: string;
}) {
  const groups = useMemo(() => {
    const byCategory = new Map<string, HelpTopicSummary[]>();
    for (const t of [...topics].sort((a, b) => a.order - b.order)) {
      const list = byCategory.get(t.category) ?? [];
      list.push(t);
      byCategory.set(t.category, list);
    }
    return [...byCategory.entries()];
  }, [topics]);

  return (
    <nav className="lg:sticky lg:top-4 lg:self-start">
      <div className="flex flex-col gap-5">
        {groups.map(([category, items]) => (
          <div key={category}>
            <h2 className="px-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
              {category}
            </h2>
            <ul className="mt-2 flex flex-col gap-0.5">
              {items.map((t) => (
                <li key={t.id}>
                  <Link
                    to={`/help/${t.id}`}
                    className={cn(
                      "block rounded-xl px-3 py-2 text-sm font-medium transition",
                      t.id === selectedId
                        ? "bg-grape-50 text-grape-700"
                        : "text-slate-600 hover:bg-slate-100 hover:text-ink",
                    )}
                  >
                    {t.title}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </nav>
  );
}

/* -------------------------------------------------------------------------- */
/* Article + tabs                                                             */
/* -------------------------------------------------------------------------- */

type TabId = "text" | "audio" | "video";

function HelpArticle({ topicId }: { topicId: string }) {
  const [tab, setTab] = useState<TabId>("text");
  const topic = useQuery({
    queryKey: ["help-topic", topicId],
    queryFn: () => getHelpTopic(topicId),
  });

  if (topic.isLoading) {
    return <Card className="p-6 text-sm text-slate-400">Loading…</Card>;
  }
  if (!topic.data) {
    return <Card className="p-6 text-sm text-slate-400">Topic not found.</Card>;
  }

  const data = topic.data;

  return (
    <Card className="flex flex-col gap-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          {data.category}
        </p>
        <h2 className="mt-1 text-xl font-semibold text-ink">{data.title}</h2>
        <p className="mt-1 text-sm text-slate-500">{data.summary}</p>
      </div>

      <Tabs current={tab} onChange={setTab} />

      <div>
        {tab === "text" ? (
          <div className="max-w-2xl">{renderMarkdown(data.body_markdown)}</div>
        ) : null}
        {tab === "audio" ? (
          <AudioTab topicId={topicId} audioSupported={data.audio_supported} />
        ) : null}
        {tab === "video" ? <VideoTab /> : null}
      </div>
    </Card>
  );
}

function Tabs({
  current,
  onChange,
}: {
  current: TabId;
  onChange: (id: TabId) => void;
}) {
  const tabs: { id: TabId; label: string; soon?: boolean }[] = [
    { id: "text", label: "Text" },
    { id: "audio", label: "Audio" },
    { id: "video", label: "Video", soon: true },
  ];
  return (
    <div className="border-b border-slate-100">
      <nav className="flex gap-1">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => onChange(t.id)}
            className={cn(
              "flex items-center gap-1.5 rounded-t-xl px-4 py-2 text-sm font-medium transition",
              current === t.id
                ? "border border-b-white border-slate-100 bg-surface text-grape-700"
                : "text-slate-500 hover:text-ink",
            )}
          >
            {t.label}
            {t.soon ? (
              <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
                Soon
              </span>
            ) : null}
          </button>
        ))}
      </nav>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Audio tab — generate-on-first-play + poll + play                           */
/* -------------------------------------------------------------------------- */

function AudioTab({
  topicId,
  audioSupported,
}: {
  topicId: string;
  audioSupported: boolean;
}) {
  const queryClient = useQueryClient();

  const audio = useQuery({
    queryKey: ["help-audio", topicId],
    queryFn: () => getHelpAudio(topicId),
    enabled: audioSupported,
    // One quiet retry smooths over a transient blip before we surface an error.
    retry: 1,
    // Poll only while a narration is being generated.
    refetchInterval: (query) =>
      query.state.data?.status === "generating" ? 2500 : false,
  });

  const start = useMutation({
    mutationFn: () => startHelpAudio(topicId),
    onSuccess: (data) => queryClient.setQueryData(["help-audio", topicId], data),
  });

  const status = audio.data?.status;

  // Auto-start generation the first time someone opens Audio for this topic.
  // Gated on start.isIdle so a *failed* attempt doesn't silently loop — after a
  // failure the user retries explicitly via the button below.
  useEffect(() => {
    if (audioSupported && status === "none" && start.isIdle) {
      start.mutate();
    }
  }, [audioSupported, status, start]);

  // Safety net: if generation never resolves (e.g. the worker died mid-run, or
  // the server keeps reporting "generating"), stop after a while and offer a
  // retry instead of spinning forever.
  const [timedOut, setTimedOut] = useState(false);
  useEffect(() => {
    setTimedOut(false);
    if (status !== "generating") return;
    const timer = setTimeout(() => setTimedOut(true), 90_000);
    return () => clearTimeout(timer);
  }, [status]);

  const retry = () => {
    setTimedOut(false);
    start.reset();
    start.mutate();
  };

  // 1) TTS not configured on the server → honest "coming soon".
  if (!audioSupported || status === "unavailable") {
    return (
      <ComingSoon
        title="Audio narration coming soon"
        body="Spoken narration for this article isn't available yet. Check back soon — or read the Text tab in the meantime."
      />
    );
  }

  // 2) Ready → play.
  if (status === "ready" && audio.data?.url) {
    return (
      <div className="flex flex-col gap-3 py-2">
        <p className="text-sm text-slate-600">Listen to this article:</p>
        {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
        <audio controls preload="none" src={audio.data.url} className="w-full max-w-lg">
          Your browser doesn&apos;t support audio playback.
        </audio>
        <p className="text-xs text-slate-400">Narrated with ElevenLabs AI voices.</p>
      </div>
    );
  }

  // 3) Actively working — the initial status check, the first auto-start, an
  // in-flight retry, or generation in progress. Takes precedence over a stale
  // error so a retry shows the spinner, not the old message. Bails out if
  // generation has stalled past the timeout.
  const working =
    !timedOut &&
    (start.isPending ||
      status === "generating" ||
      audio.isLoading ||
      (status === "none" && !start.isError));
  if (working) {
    return (
      <div className="flex items-center gap-3 rounded-xl bg-slate-50 px-4 py-6 text-sm text-slate-600">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-grape-300 border-t-grape-700" />
        Preparing narration… this can take a few seconds the first time.
      </div>
    );
  }

  // 4) Anything else is a failure we can retry: the status request failed, the
  // start request failed, the server marked the asset "failed", or generation
  // stalled. Never a stuck spinner.
  return (
    <div className="flex flex-col gap-3 rounded-xl bg-amber-50 px-4 py-5 text-sm text-amber-800">
      <p>We couldn&apos;t load the narration right now.</p>
      <button
        onClick={retry}
        disabled={start.isPending}
        className="w-fit rounded-lg bg-grape px-3 py-1.5 text-sm font-medium text-white transition hover:bg-grape-800 disabled:opacity-60"
      >
        Try again
      </button>
      <p className="text-xs text-amber-700/70">
        You can keep reading on the Text tab in the meantime.
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Video tab — Coming Soon                                                     */
/* -------------------------------------------------------------------------- */

function VideoTab() {
  return (
    <ComingSoon
      title="Interactive video walkthroughs — coming soon"
      body="Short, guided videos for each topic are on the way. For now, use the Text and Audio tabs."
    />
  );
}

function ComingSoon({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 px-6 py-12 text-center">
      <span className="rounded-full bg-amber-100 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
        Coming soon
      </span>
      <h3 className="mt-1 text-base font-semibold text-ink">{title}</h3>
      <p className="max-w-md text-sm text-slate-500">{body}</p>
    </div>
  );
}
