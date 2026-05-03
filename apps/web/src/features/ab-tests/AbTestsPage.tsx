import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { UsageMeter } from "@/components/UsageMeter";
import { ApiError } from "@/lib/api-client";
import { createAbTest, listAbTests } from "@/lib/ab-tests";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { AbTestStatus, AbTestTarget } from "@/types/api";

const STATUS_PILL: Record<AbTestStatus, string> = {
  draft: "bg-slate-100 text-slate-600",
  ready: "bg-amber-100 text-amber-700",
  launched: "pill-grape",
  paused: "bg-slate-100 text-slate-500",
  completed: "pill-success",
  archived: "bg-slate-100 text-slate-400",
};

export function AbTestsPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const tests = useQuery({
    queryKey: ["ab-tests", workspaceId],
    queryFn: () => listAbTests(workspaceId!),
    enabled: !!workspaceId,
  });

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <header>
        <p className="text-xs uppercase tracking-wider text-grape-700">Experiments</p>
        <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">
          A/B tests
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Run head-to-head tests on ads or landing pages. Ad tests launch
          paused on the provider — flip them to active explicitly to start
          spending.
        </p>
      </header>

      <UsageMeter resource="ab_tests" />

      <CreateAbTestForm />

      {tests.isLoading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : tests.error ? (
        <Card>
          <p className="text-sm text-red-700">
            {tests.error instanceof Error
              ? tests.error.message
              : "Could not load tests."}
          </p>
        </Card>
      ) : tests.data && tests.data.length === 0 ? (
        <EmptyState
          title="No tests yet"
          description="Create a landing-page test above, or POST to /ab-tests with target=ad to launch on Google/Meta/LinkedIn."
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {tests.data?.map((t) => (
            <li key={t.id}>
              <Link
                to={`/ab-tests/${t.id}`}
                className="card flex flex-col gap-2 p-4 transition hover:bg-grape-50"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className={cn("pill", STATUS_PILL[t.status])}>
                      {t.status}
                    </span>
                    <span className="pill bg-slate-50 text-slate-500">
                      {t.target === "ad" ? "Ad" : "Landing page"}
                    </span>
                    <span className="pill bg-grape-50 text-grape-700">
                      {t.objective}
                    </span>
                  </div>
                  <span className="text-xs text-slate-400">
                    {new Date(t.created_at).toLocaleString()}
                  </span>
                </div>
                <h3 className="text-sm font-semibold text-ink">{t.name}</h3>
                <p className="text-xs text-slate-500">
                  {t.variants.length} variants
                  {t.winner_variant_id ? " · winner declared" : ""}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CreateAbTestForm() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const [target, setTarget] = useState<AbTestTarget>("landing_page");
  const [name, setName] = useState("");
  const [hypothesis, setHypothesis] = useState("");
  const [objective, setObjective] = useState("conversion_rate");

  // Landing-page form state
  const [variantA, setVariantA] = useState("");
  const [variantB, setVariantB] = useState("");

  // Ad-target form state
  const [provider, setProvider] = useState("meta_ads");
  const [externalAccountId, setExternalAccountId] = useState("");
  const [adAName, setAdAName] = useState("");
  const [adABudget, setAdABudget] = useState("5000");
  const [adBName, setAdBName] = useState("");
  const [adBBudget, setAdBBudget] = useState("5000");

  const [error, setError] = useState<string | null>(null);

  const mut = useMutation({
    mutationFn: () => {
      if (target === "landing_page") {
        return createAbTest(workspaceId!, {
          name,
          hypothesis: hypothesis || null,
          target: "landing_page",
          objective,
          variants: [
            {
              name: "control",
              is_control: true,
              traffic_share: 0.5,
              payload: { url: variantA },
            },
            {
              name: "treatment",
              traffic_share: 0.5,
              payload: { url: variantB },
            },
          ],
        });
      }
      return createAbTest(workspaceId!, {
        name,
        hypothesis: hypothesis || null,
        target: "ad",
        objective,
        provider,
        external_account_id: externalAccountId,
        variants: [
          {
            name: "control",
            is_control: true,
            traffic_share: 0.5,
            payload: {
              name: adAName || `${name} — control`,
              objective: "OUTCOME_LEADS",
              daily_budget_cents: Number(adABudget),
            },
          },
          {
            name: "treatment",
            traffic_share: 0.5,
            payload: {
              name: adBName || `${name} — treatment`,
              objective: "OUTCOME_LEADS",
              daily_budget_cents: Number(adBBudget),
            },
          },
        ],
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ab-tests", workspaceId] });
      setName("");
      setHypothesis("");
      setVariantA("");
      setVariantB("");
      setExternalAccountId("");
      setAdAName("");
      setAdBName("");
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not create."),
  });

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    if (!name.trim()) {
      setError("Provide a test name.");
      return;
    }
    if (target === "landing_page") {
      if (!variantA.trim() || !variantB.trim()) {
        setError("Provide both variant URLs.");
        return;
      }
    } else {
      if (!externalAccountId.trim()) {
        setError("Provide the ad account ID for the connected provider.");
        return;
      }
      if (!Number(adABudget) || !Number(adBBudget)) {
        setError("Each variant needs a positive daily budget (in cents).");
        return;
      }
    }
    mut.mutate();
  }

  return (
    <Card>
      <CardHeader
        title="Create a test"
        subtitle="Landing-page tests use the public traffic-split snippet. Ad tests launch each variant as a paused campaign on the connected provider — flip them to active in the provider UI when ready to spend."
      />
      <div className="mt-3 flex gap-1">
        <TargetTab
          active={target === "landing_page"}
          label="Landing page"
          onClick={() => setTarget("landing_page")}
        />
        <TargetTab
          active={target === "ad"}
          label="Ad creative"
          onClick={() => setTarget("ad")}
        />
      </div>
      <form className="mt-4 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2" onSubmit={onSubmit}>
        <label className="flex flex-col gap-1.5 sm:col-span-2">
          <span className="font-medium text-slate-text">Test name</span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={target === "landing_page" ? "Hero copy: specific value props" : "Headline test: question vs statement"}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
          />
        </label>
        <label className="flex flex-col gap-1.5 sm:col-span-2">
          <span className="font-medium text-slate-text">Hypothesis (optional)</span>
          <textarea
            value={hypothesis}
            onChange={(e) => setHypothesis(e.target.value)}
            rows={2}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="font-medium text-slate-text">Objective</span>
          <select
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
          >
            <option value="conversion_rate">Conversion rate</option>
            <option value="click_through_rate">Click-through rate</option>
            <option value="signup_rate">Signup rate</option>
            <option value="revenue_per_visit">Revenue per visit</option>
            {target === "ad" ? (
              <>
                <option value="cpa">Cost per acquisition</option>
                <option value="roas">ROAS</option>
              </>
            ) : null}
          </select>
        </label>
        <div />

        {target === "landing_page" ? (
          <>
            <FormField label="Control URL" value={variantA} onChange={setVariantA} type="url" placeholder="https://example.com/a" />
            <FormField label="Treatment URL" value={variantB} onChange={setVariantB} type="url" placeholder="https://example.com/b" />
          </>
        ) : (
          <>
            <label className="flex flex-col gap-1.5">
              <span className="font-medium text-slate-text">Provider</span>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
              >
                <option value="meta_ads">Meta Ads</option>
                <option value="google_ads">Google Ads</option>
                <option value="linkedin_ads">LinkedIn Ads</option>
              </select>
            </label>
            <FormField
              label="External account ID"
              value={externalAccountId}
              onChange={setExternalAccountId}
              placeholder={provider === "meta_ads" ? "act_123" : provider === "google_ads" ? "1234567890" : "500001"}
            />
            <FormField
              label="Variant A — campaign name (optional)"
              value={adAName}
              onChange={setAdAName}
              placeholder="Auto: <test name> — control"
            />
            <FormField
              label="Variant A — daily budget (cents)"
              value={adABudget}
              onChange={setAdABudget}
              type="number"
              placeholder="5000"
            />
            <FormField
              label="Variant B — campaign name (optional)"
              value={adBName}
              onChange={setAdBName}
              placeholder="Auto: <test name> — treatment"
            />
            <FormField
              label="Variant B — daily budget (cents)"
              value={adBBudget}
              onChange={setAdBBudget}
              type="number"
              placeholder="5000"
            />
          </>
        )}

        {error ? (
          <div className="sm:col-span-2 rounded-lg bg-red-50 px-3 py-2 text-red-700">
            {error}
          </div>
        ) : null}
        <div className="sm:col-span-2">
          <Button type="submit" disabled={mut.isPending}>
            {mut.isPending ? "Creating…" : "Create test"}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function TargetTab({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-xl px-3 py-1.5 text-xs font-medium transition",
        active
          ? "bg-grape-100 text-grape-700"
          : "bg-slate-100 text-slate-500 hover:bg-slate-200",
      )}
    >
      {label}
    </button>
  );
}

function FormField({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="font-medium text-slate-text">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
      />
    </label>
  );
}
