import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import {
  createAd,
  createAdGroup,
  createCreative,
  deleteAd,
  deleteAdGroup,
  listAdGroups,
  listAds,
  listCreatives,
  publishAd,
  publishAdGroup,
} from "@/lib/ad-builder";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { Ad, AdGroup, Creative } from "@/types/api";

const inputCls =
  "w-full rounded-xl border border-slate-200 bg-surface px-3 py-1.5 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200";

const splitCsv = (s: string) =>
  s.split(",").map((x) => x.trim()).filter(Boolean);

export function AdStructureBuilder({ campaignId }: { campaignId: string }) {
  const ws = useWorkspaceStore((s) => s.currentWorkspaceId)!;
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);

  const groups = useQuery({
    queryKey: ["ad-groups", ws, campaignId],
    queryFn: () => listAdGroups(ws, campaignId),
    enabled: !!ws,
  });
  const ads = useQuery({
    queryKey: ["ads", ws, campaignId],
    queryFn: () => listAds(ws, campaignId),
    enabled: !!ws,
  });
  const creatives = useQuery({
    queryKey: ["creatives", ws],
    queryFn: () => listCreatives(ws),
    enabled: !!ws,
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["ad-groups", ws, campaignId] });
    qc.invalidateQueries({ queryKey: ["ads", ws, campaignId] });
  };

  return (
    <Card>
      <CardHeader
        title="Ad structure"
        subtitle="Build ad sets (targeting + budget) → ads → creatives as drafts, then publish them live. Publishing creates the object paused and needs admin approval."
        action={
          <Button variant="secondary" onClick={() => setAdding((v) => !v)}>
            {adding ? "Close" : "Add ad set"}
          </Button>
        }
      />

      {adding ? (
        <AddAdSetForm
          onClose={() => setAdding(false)}
          onCreate={async (body) => {
            await createAdGroup(ws, campaignId, body);
            refresh();
            setAdding(false);
          }}
        />
      ) : null}

      <div className="mt-4 flex flex-col gap-3">
        {groups.isLoading ? (
          <p className="text-sm text-slate-400">Loading…</p>
        ) : (groups.data ?? []).length === 0 ? (
          <p className="text-sm text-slate-500">
            No ad sets yet. Add one to define targeting, then add ads and creatives under it.
          </p>
        ) : (
          (groups.data ?? []).map((g) => (
            <AdGroupCard
              key={g.id}
              group={g}
              ads={(ads.data ?? []).filter((a) => a.ad_group_id === g.id)}
              creatives={creatives.data ?? []}
              workspaceId={ws}
              onChanged={refresh}
              onNewCreative={() => qc.invalidateQueries({ queryKey: ["creatives", ws] })}
            />
          ))
        )}
      </div>
    </Card>
  );
}

function AddAdSetForm({
  onClose,
  onCreate,
}: {
  onClose: () => void;
  onCreate: (body: {
    name: string;
    daily_budget_cents: number | null;
    targeting: Record<string, unknown>;
  }) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [budget, setBudget] = useState("");
  const [locations, setLocations] = useState("");
  const [ageMin, setAgeMin] = useState("");
  const [ageMax, setAgeMax] = useState("");
  const [interests, setInterests] = useState("");
  const [goal, setGoal] = useState("");
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () =>
      onCreate({
        name: name.trim(),
        daily_budget_cents: budget ? Math.round(parseFloat(budget) * 100) : null,
        targeting: {
          locations: splitCsv(locations),
          age_min: ageMin ? parseInt(ageMin, 10) : null,
          age_max: ageMax ? parseInt(ageMax, 10) : null,
          interests: splitCsv(interests),
          optimization_goal: goal || null,
        },
      }),
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not save."),
  });

  return (
    <div className="mt-3 rounded-2xl border border-grape-100 p-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Ad set name">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="US · 25-44 · Founders" className={inputCls} />
        </Field>
        <Field label="Daily budget ($)">
          <input type="number" min="0" step="1" value={budget} onChange={(e) => setBudget(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Optimization goal">
          <input value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="Conversions" className={inputCls} />
        </Field>
        <Field label="Locations (comma-sep)">
          <input value={locations} onChange={(e) => setLocations(e.target.value)} placeholder="US, CA, UK" className={inputCls} />
        </Field>
        <Field label="Age range">
          <div className="flex items-center gap-2">
            <input type="number" min="13" max="99" value={ageMin} onChange={(e) => setAgeMin(e.target.value)} placeholder="25" className={inputCls} />
            <span className="text-slate-400">–</span>
            <input type="number" min="13" max="99" value={ageMax} onChange={(e) => setAgeMax(e.target.value)} placeholder="44" className={inputCls} />
          </div>
        </Field>
        <Field label="Interests (comma-sep)">
          <input value={interests} onChange={(e) => setInterests(e.target.value)} placeholder="SaaS, Marketing" className={inputCls} />
        </Field>
      </div>
      {error ? <div className="mt-2 text-sm text-danger">{error}</div> : null}
      <div className="mt-3 flex gap-2">
        <Button onClick={() => save.mutate()} disabled={!name.trim() || save.isPending}>
          {save.isPending ? "Saving…" : "Save ad set"}
        </Button>
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
      </div>
    </div>
  );
}

function AdGroupCard({
  group,
  ads,
  creatives,
  workspaceId,
  onChanged,
  onNewCreative,
}: {
  group: AdGroup;
  ads: Ad[];
  creatives: Creative[];
  workspaceId: string;
  onChanged: () => void;
  onNewCreative: () => void;
}) {
  const [addingAd, setAddingAd] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const isGroupLive = !!group.external_id;

  const publishGroup = useMutation({
    mutationFn: () => publishAdGroup(workspaceId, group.id),
    onSuccess: (r) => {
      setNotice(r.message);
      onChanged();
    },
    onError: (e) => setNotice(e instanceof ApiError ? e.message : "Publish failed."),
  });

  const t = group.targeting ?? {};
  const targetingBits = [
    (t.locations ?? []).length ? `📍 ${(t.locations ?? []).join(", ")}` : null,
    t.age_min || t.age_max ? `${t.age_min ?? "?"}–${t.age_max ?? "?"}` : null,
    (t.interests ?? []).length ? (t.interests ?? []).join(", ") : null,
    t.optimization_goal ? `🎯 ${t.optimization_goal}` : null,
  ].filter(Boolean);

  const isDraft = group.source === "advanta_draft";

  return (
    <div className="rounded-2xl border border-slate-100 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-ink">{group.name}</span>
            <span className={`pill ${isDraft ? "pill-grape" : "bg-slate-100 text-slate-500"}`}>
              {isDraft ? "draft" : "synced"}
            </span>
          </div>
          <div className="mt-1 text-xs text-slate-500">
            {group.daily_budget_cents != null
              ? `$${(group.daily_budget_cents / 100).toFixed(2)}/day`
              : "No budget set"}
            {targetingBits.length ? ` · ${targetingBits.join(" · ")}` : ""}
          </div>
        </div>
        {isDraft ? (
          <div className="flex items-center gap-3">
            <button
              onClick={() => publishGroup.mutate()}
              disabled={publishGroup.isPending}
              className="text-xs font-medium text-grape-700 hover:text-grape-800 disabled:opacity-50"
            >
              {publishGroup.isPending ? "Publishing…" : "Publish ad set"}
            </button>
            <button
              onClick={async () => {
                await deleteAdGroup(workspaceId, group.id);
                onChanged();
              }}
              className="text-xs text-danger hover:underline"
            >
              Delete
            </button>
          </div>
        ) : null}
      </div>

      {notice ? (
        <div className="mt-2 rounded-lg bg-grape-50 px-3 py-2 text-xs text-grape-800">
          {notice}
        </div>
      ) : null}

      {/* Ads */}
      <ul className="mt-3 flex flex-col gap-1.5">
        {ads.map((ad) => {
          const cr = creatives.find((c) => c.id === ad.creative_id);
          return (
            <li key={ad.id} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm">
              <div>
                <span className="font-medium text-ink">{ad.name}</span>
                {cr ? <span className="ml-2 text-xs text-slate-500">“{cr.headline ?? cr.title ?? "creative"}”</span> : null}
                {ad.landing_page_url ? <span className="ml-2 text-xs text-grape-700">{ad.landing_page_url}</span> : null}
              </div>
              {ad.source === "advanta_draft" ? (
                <div className="flex items-center gap-3">
                  {isGroupLive ? (
                    <AdPublishButton
                      workspaceId={workspaceId}
                      adId={ad.id}
                      onResult={(msg) => {
                        setNotice(msg);
                        onChanged();
                      }}
                    />
                  ) : null}
                  <button
                    onClick={async () => {
                      await deleteAd(workspaceId, ad.id);
                      onChanged();
                    }}
                    className="text-xs text-danger hover:underline"
                  >
                    Remove
                  </button>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>

      {isDraft ? (
        addingAd ? (
          <AddAdForm
            workspaceId={workspaceId}
            creatives={creatives}
            onNewCreative={onNewCreative}
            onClose={() => setAddingAd(false)}
            onCreate={async (body) => {
              await createAd(workspaceId, group.id, body);
              onChanged();
              setAddingAd(false);
            }}
          />
        ) : (
          <button onClick={() => setAddingAd(true)} className="mt-2 text-xs font-medium text-grape-700 hover:text-grape-800">
            + Add ad
          </button>
        )
      ) : null}
    </div>
  );
}

function AddAdForm({
  workspaceId,
  creatives,
  onNewCreative,
  onClose,
  onCreate,
}: {
  workspaceId: string;
  creatives: Creative[];
  onNewCreative: () => void;
  onClose: () => void;
  onCreate: (body: { name: string; landing_page_url: string | null; creative_id: string | null }) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [creativeId, setCreativeId] = useState("");
  const [showNewCreative, setShowNewCreative] = useState(false);
  const [headline, setHeadline] = useState("");
  const [primaryText, setPrimaryText] = useState("");
  const [cta, setCta] = useState("");

  const saveAd = useMutation({
    mutationFn: () =>
      onCreate({
        name: name.trim(),
        landing_page_url: url.trim() || null,
        creative_id: creativeId || null,
      }),
  });

  const saveCreative = useMutation({
    mutationFn: () =>
      createCreative(workspaceId, {
        type: "single_image",
        headline: headline.trim() || null,
        primary_text: primaryText.trim() || null,
        cta: cta.trim() || null,
        image_url: null,
      }),
    onSuccess: (cr) => {
      onNewCreative();
      setCreativeId(cr.id);
      setShowNewCreative(false);
    },
  });

  return (
    <div className="mt-3 rounded-xl border border-slate-100 bg-white p-3">
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Ad name">
          <input value={name} onChange={(e) => setName(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Landing page URL">
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" className={inputCls} />
        </Field>
        <Field label="Creative">
          <select value={creativeId} onChange={(e) => setCreativeId(e.target.value)} className={inputCls}>
            <option value="">— none —</option>
            {creatives.map((c) => (
              <option key={c.id} value={c.id}>
                {c.headline ?? c.title ?? `${c.type} creative`}
              </option>
            ))}
          </select>
        </Field>
        <div className="flex items-end">
          <button onClick={() => setShowNewCreative((v) => !v)} className="text-xs font-medium text-grape-700 hover:text-grape-800">
            {showNewCreative ? "Cancel new creative" : "+ New creative"}
          </button>
        </div>
      </div>

      {showNewCreative ? (
        <div className="mt-2 grid gap-2 rounded-lg bg-slate-50 p-3 sm:grid-cols-3">
          <Field label="Headline">
            <input value={headline} onChange={(e) => setHeadline(e.target.value)} className={inputCls} />
          </Field>
          <Field label="Primary text">
            <input value={primaryText} onChange={(e) => setPrimaryText(e.target.value)} className={inputCls} />
          </Field>
          <Field label="CTA">
            <input value={cta} onChange={(e) => setCta(e.target.value)} className={inputCls} />
          </Field>
          <div>
            <Button onClick={() => saveCreative.mutate()} disabled={saveCreative.isPending}>
              {saveCreative.isPending ? "Saving…" : "Save creative"}
            </Button>
          </div>
        </div>
      ) : null}

      <div className="mt-3 flex gap-2">
        <Button onClick={() => saveAd.mutate()} disabled={!name.trim() || saveAd.isPending}>
          {saveAd.isPending ? "Adding…" : "Add ad"}
        </Button>
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
      </div>
    </div>
  );
}

function AdPublishButton({
  workspaceId,
  adId,
  onResult,
}: {
  workspaceId: string;
  adId: string;
  onResult: (message: string) => void;
}) {
  const publish = useMutation({
    mutationFn: () => publishAd(workspaceId, adId),
    onSuccess: (r) => onResult(r.message),
    onError: (e) => onResult(e instanceof ApiError ? e.message : "Publish failed."),
  });
  return (
    <button
      onClick={() => publish.mutate()}
      disabled={publish.isPending}
      className="text-xs font-medium text-grape-700 hover:text-grape-800 disabled:opacity-50"
    >
      {publish.isPending ? "Publishing…" : "Publish"}
    </button>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-slate-500">{label}</span>
      {children}
    </label>
  );
}
