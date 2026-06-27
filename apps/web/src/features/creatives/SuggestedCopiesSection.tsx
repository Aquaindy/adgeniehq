import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import { getOnboarding } from "@/lib/onboarding";
import {
  deleteSuggestedCopy,
  fetchSuggestedCopiesBundleBlob,
  fetchSuggestedCopyBlob,
  generateSuggestedCopies,
  listSuggestedCopies,
  saveBlob,
} from "@/lib/suggested-copies";
import { cn } from "@/lib/utils";
import type {
  AgentRunDetail,
  OnboardingProfile,
  SuggestedCopy,
  SuggestedCopyType,
} from "@/types/api";

const TYPE_LABEL: Record<SuggestedCopyType, string> = {
  keywords: "Keywords",
  ad_copy: "Ad copy",
  landing_page: "Landing page",
  email: "Email",
  social_post: "Social",
  blog_outline: "Blog outline",
  meta_tags: "Meta tags",
};

function slugify(text: string): string {
  return text.replace(/[^a-z0-9_-]+/gi, "_").slice(0, 60) || "suggested_copy";
}

export function SuggestedCopiesSection({ workspaceId }: { workspaceId: string }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const onboarding = useQuery<OnboardingProfile>({
    queryKey: ["onboarding", workspaceId],
    queryFn: () => getOnboarding(workspaceId),
  });
  const productName = onboarding.data?.business_name ?? null;

  const list = useQuery<SuggestedCopy[]>({
    queryKey: ["suggested-copies", workspaceId],
    queryFn: () => listSuggestedCopies(workspaceId),
  });

  const generate = useMutation<AgentRunDetail>({
    mutationFn: () =>
      generateSuggestedCopies(workspaceId, {
        product_name: productName ?? undefined,
      }),
    onMutate: () => {
      setError(null);
      setNotice(null);
    },
    onSuccess: (run) => {
      const payload = (run.output_payload ?? {}) as { skipped?: boolean; copy_count?: number };
      if (payload.skipped) {
        setNotice(
          "Generate a Growth DNA Profile first — Suggested Copies are written from it.",
        );
      } else {
        setNotice(`Generated ${payload.copy_count ?? 0} suggested copies.`);
      }
      void queryClient.invalidateQueries({ queryKey: ["suggested-copies", workspaceId] });
      void queryClient.invalidateQueries({ queryKey: ["billing", "status", workspaceId] });
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not generate suggested copies. Please try again.",
      );
    },
  });

  const copies = list.data ?? [];
  const isGenerating = generate.isPending;

  async function downloadAll(format: "txt" | "docx") {
    setError(null);
    try {
      const blob = await fetchSuggestedCopiesBundleBlob(workspaceId, format);
      saveBlob(blob, `suggested_copies_${slugify(productName ?? "adgeniehq")}.${format}`);
    } catch {
      setError(`Could not download the ${format.toUpperCase()} bundle.`);
    }
  }

  return (
    <Card>
      <CardHeader
        title="Suggested Copies"
        subtitle={
          productName
            ? `AI-written copy from your Growth DNA for ${productName}. Download any item as .txt or .docx.`
            : "AI-written copy from your Growth DNA — keywords, ad copy, landing pages, emails, social, and meta tags."
        }
      />

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button onClick={() => generate.mutate()} disabled={isGenerating}>
          {isGenerating ? "Generating…" : "Generate suggested copies"}
        </Button>
        {copies.length > 0 ? (
          <>
            <Button variant="secondary" onClick={() => downloadAll("docx")}>
              Download all (.docx)
            </Button>
            <Button variant="ghost" onClick={() => downloadAll("txt")}>
              Download all (.txt)
            </Button>
          </>
        ) : null}
        {productName ? (
          <span className="text-xs text-slate-400">
            Target: <span className="font-medium text-slate-600">{productName}</span>
          </span>
        ) : null}
      </div>

      {error ? (
        <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </div>
      ) : null}
      {notice ? (
        <div className="mt-3 rounded-lg bg-grape-50 px-3 py-2 text-sm text-grape-700">
          {notice}
        </div>
      ) : null}

      {list.isLoading ? (
        <p className="mt-3 text-sm text-slate-400">Loading…</p>
      ) : copies.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">
          No suggested copies yet. Click{" "}
          <span className="font-medium text-slate-700">Generate suggested copies</span> to
          turn each section of your{" "}
          <Link to="/growth-dna" className="text-grape-700 underline-offset-2 hover:underline">
            Growth DNA Profile
          </Link>{" "}
          into ready-to-edit keyword plans, ad copy, landing-page copy, emails, social hooks,
          and SEO meta tags.
        </p>
      ) : (
        <ul className="mt-4 flex flex-col gap-2">
          {copies.map((copy) => (
            <SuggestedCopyRow
              key={copy.id}
              workspaceId={workspaceId}
              copy={copy}
              onError={setError}
              onDeleted={() =>
                queryClient.invalidateQueries({
                  queryKey: ["suggested-copies", workspaceId],
                })
              }
            />
          ))}
        </ul>
      )}
    </Card>
  );
}

function SuggestedCopyRow({
  workspaceId,
  copy,
  onError,
  onDeleted,
}: {
  workspaceId: string;
  copy: SuggestedCopy;
  onError: (msg: string | null) => void;
  onDeleted: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  async function download(format: "txt" | "docx") {
    onError(null);
    setBusy(true);
    try {
      const blob = await fetchSuggestedCopyBlob(workspaceId, copy.id, format);
      saveBlob(blob, `${slugify(copy.title)}.${format}`);
    } catch {
      onError(`Could not download the ${format.toUpperCase()}.`);
    } finally {
      setBusy(false);
    }
  }

  const remove = useMutation({
    mutationFn: () => deleteSuggestedCopy(workspaceId, copy.id),
    onSuccess: onDeleted,
    onError: () => onError("Could not delete this copy."),
  });

  return (
    <li className="rounded-xl border border-slate-200 bg-surface">
      <div className="flex items-start justify-between gap-3 px-4 py-3">
        <button
          type="button"
          className="flex flex-1 flex-col items-start gap-1 text-left"
          onClick={() => setOpen((v) => !v)}
        >
          <span className="flex flex-wrap items-center gap-2">
            <span className="pill bg-grape-100 text-grape-700">
              {TYPE_LABEL[copy.copy_type]}
            </span>
            <span className="text-xs text-slate-400">{copy.section}</span>
            {copy.source === "llm" ? (
              <span className="pill pill-success text-xs">AI</span>
            ) : null}
          </span>
          <span className="text-sm font-medium text-ink">{copy.title}</span>
        </button>
        <div className="flex shrink-0 items-center gap-1.5">
          <Button variant="ghost" onClick={() => download("txt")} disabled={busy}>
            .txt
          </Button>
          <Button variant="secondary" onClick={() => download("docx")} disabled={busy}>
            .docx
          </Button>
        </div>
      </div>
      {open ? (
        <div className="border-t border-slate-100 px-4 py-3">
          <pre className="whitespace-pre-wrap break-words font-sans text-sm text-slate-700">
            {copy.body}
          </pre>
          <div className="mt-2 flex justify-end">
            <Button
              variant="ghost"
              onClick={() => remove.mutate()}
              disabled={remove.isPending}
              className={cn("text-xs text-red-600 hover:text-red-700")}
            >
              {remove.isPending ? "Removing…" : "Delete"}
            </Button>
          </div>
        </div>
      ) : null}
    </li>
  );
}
