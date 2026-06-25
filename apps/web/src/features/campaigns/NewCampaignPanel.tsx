import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import { launchCampaign } from "@/lib/campaigns";
import { getPrelaunchFeeQuote } from "@/lib/fees";
import { cn } from "@/lib/utils";
import type { CampaignLaunchResponse } from "@/types/api";

const PROVIDERS = [
  { value: "meta_ads", label: "Meta Ads" },
  { value: "google_ads", label: "Google Ads" },
  { value: "linkedin_ads", label: "LinkedIn Ads" },
];

const CAMPAIGN_TYPES = [
  { value: "leads", label: "Leads" },
  { value: "sales", label: "Sales" },
  { value: "traffic", label: "Traffic" },
  { value: "awareness", label: "Awareness" },
  { value: "engagement", label: "Engagement" },
  { value: "app", label: "App promotion" },
];

const money = (cents: number) =>
  new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(cents / 100);

export function NewCampaignPanel({
  workspaceId,
  onClose,
  onLaunched,
}: {
  workspaceId: string;
  onClose: () => void;
  onLaunched: () => void;
}) {
  const [provider, setProvider] = useState("meta_ads");
  const [name, setName] = useState("");
  const [campaignType, setCampaignType] = useState("leads");
  const [budgetDollars, setBudgetDollars] = useState("20");
  const [result, setResult] = useState<CampaignLaunchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const dollars = parseFloat(budgetDollars);
  const budgetCents = !Number.isNaN(dollars) && dollars > 0 ? Math.round(dollars * 100) : 0;
  const canLaunch = name.trim().length > 0 && budgetCents > 0;

  const quote = useQuery({
    queryKey: ["prelaunch-quote", workspaceId, provider, campaignType, budgetCents],
    queryFn: () =>
      getPrelaunchFeeQuote(workspaceId, {
        provider,
        campaign_type: campaignType,
        daily_budget_cents: budgetCents,
      }),
    enabled: budgetCents > 0,
  });

  const launch = useMutation({
    mutationFn: () =>
      launchCampaign(workspaceId, {
        provider,
        name: name.trim(),
        campaign_type: campaignType,
        daily_budget_cents: budgetCents,
      }),
    onSuccess: (data) => {
      setError(null);
      setResult(data);
      onLaunched();
    },
    onError: (e) => {
      setResult(null);
      setError(e instanceof ApiError ? e.message : "Could not launch campaign.");
    },
  });

  return (
    <Card className="border-grape-100">
      <CardHeader
        title="New campaign"
        subtitle="Launches paused on the connected platform, routed through approval. You'll see the platform fees before you launch."
        action={
          <button onClick={onClose} className="text-sm text-slate-400 hover:text-ink">
            ✕
          </button>
        }
      />

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Field label="Platform">
          <Select value={provider} onChange={setProvider} options={PROVIDERS} />
        </Field>
        <Field label="Objective">
          <Select value={campaignType} onChange={setCampaignType} options={CAMPAIGN_TYPES} />
        </Field>
        <Field label="Campaign name">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Q3 Lead Gen — US"
            className={inputCls}
          />
        </Field>
        <Field label="Daily budget ($)">
          <input
            type="number"
            min="1"
            step="1"
            value={budgetDollars}
            onChange={(e) => setBudgetDollars(e.target.value)}
            className={inputCls}
          />
        </Field>
      </div>

      {quote.data ? (
        <div className="mt-3 rounded-xl bg-grape-soft/40 px-4 py-3 text-sm">
          <div className="font-medium text-ink">Platform fees</div>
          <div className="mt-1 flex flex-wrap gap-x-6 gap-y-1 text-slate-600">
            <span>
              Listing: <span className="font-semibold text-ink">{money(quote.data.listing_fee_cents)}</span> once
            </span>
            <span>
              Run:{" "}
              <span className="font-semibold text-ink">
                {money(quote.data.run_flat_fee_cents)}
                {quote.data.run_pct_basis_points > 0
                  ? ` + ${(quote.data.run_pct_basis_points / 100).toFixed(1)}%`
                  : ""}
              </span>{" "}
              / mo
            </span>
            <span>
              Est. first month:{" "}
              <span className="font-semibold text-grape-700">
                {money(quote.data.est_first_month_total_cents)}
              </span>
            </span>
          </div>
        </div>
      ) : null}

      {error ? (
        <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}{" "}
          {error.toLowerCase().includes("connect") ? (
            <Link to="/integrations" className="underline">
              Open Integrations →
            </Link>
          ) : null}
        </div>
      ) : null}

      {result ? (
        <div
          className={cn(
            "mt-3 rounded-lg px-3 py-2 text-sm",
            result.status === "executed"
              ? "bg-success/10 text-success"
              : result.status === "queued"
                ? "bg-grape-soft/60 text-grape-800"
                : "bg-red-50 text-red-700",
          )}
          role="status"
        >
          {result.message}
          {result.status === "executed" && result.campaign ? (
            <>
              {" "}
              <Link to={`/campaigns/${result.campaign.id}`} className="font-medium underline">
                View campaign →
              </Link>
            </>
          ) : null}
          {result.status === "queued" ? (
            <>
              {" "}
              <Link to="/recommendations" className="font-medium underline">
                View in Recommendations →
              </Link>
            </>
          ) : null}
        </div>
      ) : null}

      <div className="mt-4 flex items-center gap-2">
        <Button onClick={() => launch.mutate()} disabled={!canLaunch || launch.isPending}>
          {launch.isPending ? "Launching…" : "Launch campaign"}
        </Button>
        <Button variant="ghost" onClick={onClose} disabled={launch.isPending}>
          Close
        </Button>
      </div>
    </Card>
  );
}

const inputCls =
  "w-full rounded-xl border border-slate-200 bg-surface px-3 py-1.5 text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-xs text-slate-500">{label}</span>
      {children}
    </label>
  );
}

function Select({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className={inputCls}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}
