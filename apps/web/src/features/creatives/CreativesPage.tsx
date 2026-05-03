import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError, apiFetch } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import type {
  Creative,
  CreativeSource,
  CreativeType,
  CreativeUpdateRequest,
} from "@/types/api";
import { useWorkspaceStore } from "@/stores/workspace-store";


export function CreativesPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  if (!workspaceId) {
    return <div className="text-sm text-slate-500">Select a workspace first.</div>;
  }
  return <CreativesPageInner workspaceId={workspaceId} />;
}


function CreativesPageInner({ workspaceId }: { workspaceId: string }) {
  const [typeFilter, setTypeFilter] = useState<CreativeType | "all">("all");
  const [sourceFilter, setSourceFilter] = useState<CreativeSource | "all">("all");
  const [editing, setEditing] = useState<Creative | null>(null);

  const list = useQuery<Creative[]>({
    queryKey: ["creatives", workspaceId, typeFilter, sourceFilter],
    queryFn: () => {
      const params = new URLSearchParams();
      if (typeFilter !== "all") params.set("type", typeFilter);
      if (sourceFilter !== "all") params.set("source", sourceFilter);
      const qs = params.toString() ? `?${params.toString()}` : "";
      return apiFetch(`/workspaces/${workspaceId}/creatives${qs}`);
    },
  });

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <header>
        <p className="text-xs uppercase tracking-wider text-grape-700">Creatives</p>
        <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">
          Creative library
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          Every creative the Creative Strategy Agent has generated, plus
          anything synced back from your ad platforms. Edit AI drafts inline
          before attaching them to ads.
        </p>
      </header>

      <Card>
        <CardHeader title="Filters" />
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <FilterSelect
            label="Type"
            value={typeFilter}
            onChange={(v) => setTypeFilter(v as CreativeType | "all")}
            options={[
              ["all", "All types"],
              ["search_ad", "Search ad"],
              ["responsive_display", "Responsive display"],
              ["single_image", "Single image"],
              ["video", "Video"],
              ["carousel", "Carousel"],
              ["ugc", "UGC"],
              ["other", "Other"],
            ]}
          />
          <FilterSelect
            label="Source"
            value={sourceFilter}
            onChange={(v) => setSourceFilter(v as CreativeSource | "all")}
            options={[
              ["all", "All sources"],
              ["ai_generated", "AI-generated"],
              ["platform_synced", "Platform-synced"],
              ["user_uploaded", "User-uploaded"],
            ]}
          />
        </div>
      </Card>

      <Card>
        <CardHeader
          title={`Creatives (${list.data?.length ?? 0})`}
          subtitle="Click a row to edit AI-generated copy."
        />
        {list.isLoading ? (
          <p className="mt-3 text-sm text-slate-400">Loading…</p>
        ) : (list.data ?? []).length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">
            No creatives yet. Run the Creative Strategy agent to generate some.
          </p>
        ) : (
          <ul className="mt-3 flex flex-col divide-y divide-slate-100">
            {(list.data ?? []).map((c) => (
              <li
                key={c.id}
                className="flex cursor-pointer flex-col gap-1 py-3 hover:bg-slate-50"
                onClick={() => setEditing(c)}
              >
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="font-medium text-ink">
                    {c.headline || c.title || "(untitled)"}
                  </span>
                  <span className="flex items-center gap-2 text-xs">
                    <span className="pill bg-grape-100 text-grape-700">
                      {c.type}
                    </span>
                    <span
                      className={cn(
                        "pill",
                        c.source === "ai_generated"
                          ? "pill-grape"
                          : c.source === "platform_synced"
                            ? "pill-success"
                            : "bg-slate-100 text-slate-600",
                      )}
                    >
                      {c.source.replace("_", " ")}
                    </span>
                  </span>
                </div>
                {c.description ? (
                  <span className="line-clamp-2 text-xs text-slate-500">
                    {c.description}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Card>

      {editing ? (
        <CreativeEditor
          workspaceId={workspaceId}
          creative={editing}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </div>
  );
}


function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
}) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      <span className="text-xs uppercase tracking-wider text-slate-400">
        {label}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
      >
        {options.map(([v, lbl]) => (
          <option key={v} value={v}>
            {lbl}
          </option>
        ))}
      </select>
    </label>
  );
}


function CreativeEditor({
  workspaceId,
  creative,
  onClose,
}: {
  workspaceId: string;
  creative: Creative;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<CreativeUpdateRequest>({
    title: creative.title ?? "",
    primary_text: creative.primary_text ?? "",
    headline: creative.headline ?? "",
    description: creative.description ?? "",
    cta: creative.cta ?? "",
    image_url: creative.image_url ?? "",
    video_url: creative.video_url ?? "",
  });
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: async () =>
      apiFetch<Creative>(
        `/workspaces/${workspaceId}/creatives/${creative.id}`,
        { method: "PATCH", body: draft },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["creatives", workspaceId],
      });
      onClose();
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    },
  });

  const isSynced = creative.source === "platform_synced";

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    save.mutate();
  }

  return (
    <div
      className="fixed inset-0 z-30 flex items-center justify-center bg-black/30 p-4"
      onClick={onClose}
    >
      <Card
        className="w-full max-w-2xl"
        onClick={(e: React.MouseEvent) => e.stopPropagation()}
      >
        <CardHeader
          title={`Edit creative · ${creative.type}`}
          subtitle={
            isSynced
              ? "This was synced from a platform. Edits here are local — push them back via your provider's UI."
              : "AI-generated draft. Refine here before attaching to an ad."
          }
        />
        <form className="mt-3 flex flex-col gap-3" onSubmit={onSubmit} noValidate>
          <Field
            id="cre-headline"
            label="Headline"
            value={draft.headline ?? ""}
            onChange={(v) => setDraft((d) => ({ ...d, headline: v }))}
          />
          <Field
            id="cre-title"
            label="Title"
            value={draft.title ?? ""}
            onChange={(v) => setDraft((d) => ({ ...d, title: v }))}
          />
          <Field
            id="cre-primary"
            label="Primary text"
            multiline
            value={draft.primary_text ?? ""}
            onChange={(v) => setDraft((d) => ({ ...d, primary_text: v }))}
          />
          <Field
            id="cre-description"
            label="Description"
            multiline
            value={draft.description ?? ""}
            onChange={(v) => setDraft((d) => ({ ...d, description: v }))}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <Field
              id="cre-cta"
              label="CTA"
              value={draft.cta ?? ""}
              onChange={(v) => setDraft((d) => ({ ...d, cta: v }))}
            />
            <Field
              id="cre-image"
              label="Image URL"
              value={draft.image_url ?? ""}
              onChange={(v) => setDraft((d) => ({ ...d, image_url: v }))}
            />
          </div>
          {error ? (
            <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
              {error}
            </div>
          ) : null}
          <div className="flex items-center justify-end gap-2">
            <Button variant="secondary" type="button" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Save changes"}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}


function Field({
  id,
  label,
  value,
  onChange,
  multiline,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  multiline?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1.5 text-sm" htmlFor={id}>
      <span className="font-medium text-slate-text">{label}</span>
      {multiline ? (
        <textarea
          id={id}
          rows={3}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
        />
      ) : (
        <input
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
        />
      )}
    </label>
  );
}
