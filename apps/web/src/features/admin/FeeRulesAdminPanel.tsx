import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import {
  deleteFeeRule,
  getFeeRevenue,
  listFeeRules,
  upsertFeeRule,
} from "@/lib/fees";
import { cn } from "@/lib/utils";
import type { FeeRule } from "@/types/api";

const PROVIDERS = [
  { value: "", label: "Any platform" },
  { value: "meta_ads", label: "Meta Ads" },
  { value: "google_ads", label: "Google Ads" },
  { value: "linkedin_ads", label: "LinkedIn Ads" },
  { value: "tiktok_ads", label: "TikTok Ads" },
  { value: "microsoft_ads", label: "Microsoft Ads" },
];

const CAMPAIGN_TYPES = [
  { value: "", label: "Any type" },
  { value: "leads", label: "Leads" },
  { value: "sales", label: "Sales" },
  { value: "traffic", label: "Traffic" },
  { value: "awareness", label: "Awareness" },
  { value: "engagement", label: "Engagement" },
  { value: "app", label: "App" },
  { value: "other", label: "Other" },
];

const money = (cents: number) =>
  new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(
    cents / 100,
  );

export function FeeRulesAdminPanel() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const [provider, setProvider] = useState("");
  const [campaignType, setCampaignType] = useState("");
  const [label, setLabel] = useState("");
  const [listing, setListing] = useState("25");
  const [flat, setFlat] = useState("0");
  const [pct, setPct] = useState("10");

  const rules = useQuery({ queryKey: ["admin", "fee-rules"], queryFn: listFeeRules });
  const revenue = useQuery({ queryKey: ["admin", "fee-revenue"], queryFn: () => getFeeRevenue() });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["admin", "fee-rules"] });
    queryClient.invalidateQueries({ queryKey: ["admin", "fee-revenue"] });
  };

  const save = useMutation({
    mutationFn: () =>
      upsertFeeRule({
        provider: provider || null,
        campaign_type: campaignType || null,
        label: label.trim() || "Untitled rule",
        listing_fee_cents: Math.round(parseFloat(listing || "0") * 100),
        run_flat_fee_cents: Math.round(parseFloat(flat || "0") * 100),
        run_pct_basis_points: Math.round(parseFloat(pct || "0") * 100),
      }),
    onSuccess: () => {
      setError(null);
      setLabel("");
      refresh();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not save rule."),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteFeeRule(id),
    onSuccess: refresh,
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not delete rule."),
  });

  return (
    <Card>
      <CardHeader
        title="Platform fees"
        subtitle="Fee schedule charged for ad activity (listing + flat + % of spend). Most specific rule wins; an Any/Any rule is the global default."
      />

      {revenue.data ? (
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <RevenueTile label={`Accrued · ${revenue.data.period}`} cents={revenue.data.period_total_cents} tone="grape" />
          <RevenueTile label="Accrued · all time" cents={revenue.data.all_time_total_cents} tone="success" />
          <div className="rounded-2xl border border-slate-100 bg-surface px-4 py-3 shadow-card">
            <div className="text-[11px] uppercase tracking-wider text-slate-400">Ledger entries</div>
            <div className="mt-1 text-2xl font-semibold text-ink">
              {revenue.data.accrual_count.toLocaleString()}
            </div>
          </div>
        </div>
      ) : null}

      {/* Add / update form */}
      <div className="mt-4 rounded-2xl border border-slate-100 p-4">
        <div className="text-sm font-semibold text-ink">Add or update a rule</div>
        <p className="mt-0.5 text-xs text-slate-500">
          Saving a rule with the same platform + type updates it.
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Platform">
            <Select value={provider} onChange={setProvider} options={PROVIDERS} />
          </Field>
          <Field label="Campaign type">
            <Select value={campaignType} onChange={setCampaignType} options={CAMPAIGN_TYPES} />
          </Field>
          <Field label="Label">
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. Meta Leads"
              className={inputCls}
            />
          </Field>
          <Field label="Listing fee ($, one-time)">
            <input type="number" min="0" step="0.01" value={listing} onChange={(e) => setListing(e.target.value)} className={inputCls} />
          </Field>
          <Field label="Run flat fee ($/mo)">
            <input type="number" min="0" step="0.01" value={flat} onChange={(e) => setFlat(e.target.value)} className={inputCls} />
          </Field>
          <Field label="Run fee (% of spend)">
            <input type="number" min="0" max="100" step="0.1" value={pct} onChange={(e) => setPct(e.target.value)} className={inputCls} />
          </Field>
        </div>
        <div className="mt-3">
          <Button onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save rule"}
          </Button>
        </div>
      </div>

      {error ? (
        <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      {/* Rules table */}
      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-100 text-xs uppercase tracking-wider text-slate-400">
              <th className="px-3 py-2">Platform</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Label</th>
              <th className="px-3 py-2">Listing</th>
              <th className="px-3 py-2">Flat/mo</th>
              <th className="px-3 py-2">% spend</th>
              <th className="px-3 py-2">Active</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {(rules.data ?? []).length === 0 ? (
              <tr>
                <td colSpan={8} className="px-3 py-4 text-slate-500">
                  No rules yet — the default ($25 listing + 10% of spend) applies until you add one.
                </td>
              </tr>
            ) : (
              (rules.data ?? []).map((r: FeeRule) => (
                <tr key={r.id} className="hover:bg-slate-50">
                  <td className="px-3 py-2 text-slate-700">
                    {PROVIDERS.find((p) => p.value === (r.provider ?? ""))?.label ?? r.provider}
                  </td>
                  <td className="px-3 py-2 text-slate-700">{r.campaign_type ?? "Any"}</td>
                  <td className="px-3 py-2 font-medium text-ink">{r.label}</td>
                  <td className="px-3 py-2 text-slate-700">{money(r.listing_fee_cents)}</td>
                  <td className="px-3 py-2 text-slate-700">{money(r.run_flat_fee_cents)}</td>
                  <td className="px-3 py-2 text-slate-700">{(r.run_pct_basis_points / 100).toFixed(1)}%</td>
                  <td className="px-3 py-2">
                    {r.is_active ? (
                      <span className="pill pill-success">yes</span>
                    ) : (
                      <span className="pill bg-slate-100 text-slate-500">no</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => remove.mutate(r.id)}
                      disabled={remove.isPending}
                      className="text-xs font-medium text-danger hover:underline disabled:opacity-50"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
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

function RevenueTile({
  label,
  cents,
  tone,
}: {
  label: string;
  cents: number;
  tone?: "grape" | "success";
}) {
  return (
    <div className="rounded-2xl border border-slate-100 bg-surface px-4 py-3 shadow-card">
      <div className="text-[11px] uppercase tracking-wider text-slate-400">{label}</div>
      <div
        className={cn(
          "mt-1 text-2xl font-semibold",
          tone === "grape" && "text-grape-700",
          tone === "success" && "text-success",
          !tone && "text-ink",
        )}
      >
        {money(cents)}
      </div>
    </div>
  );
}
