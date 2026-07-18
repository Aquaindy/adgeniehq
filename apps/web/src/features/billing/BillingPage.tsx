import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import {
  createCheckoutSession,
  createPortalSession,
  getBillingStatus,
} from "@/lib/billing";
import { getWorkspaceFees, getWorkspaceInvoices } from "@/lib/fees";
import { redirectToPayPalCheckout } from "@/lib/paypal";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type {
  BillingStatus,
  FeeInvoice,
  FeeInvoiceStatus,
  Plan,
  SubscriptionStatusValue,
  WorkspaceFeeSummary,
} from "@/types/api";

type Interval = "month" | "year";

const money = (cents: number) => `$${(cents / 100).toFixed(2)}`;

export function BillingPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<{ kind: "success" | "warning"; text: string } | null>(null);
  const [interval, setInterval] = useState<Interval>("month");

  const status = useQuery({
    queryKey: ["billing", workspaceId],
    queryFn: () => getBillingStatus(workspaceId!),
    enabled: !!workspaceId,
  });

  const fees = useQuery({
    queryKey: ["billing-fees", workspaceId],
    queryFn: () => getWorkspaceFees(workspaceId!),
    enabled: !!workspaceId,
  });

  const invoices = useQuery({
    queryKey: ["billing-invoices", workspaceId],
    queryFn: () => getWorkspaceInvoices(workspaceId!),
    enabled: !!workspaceId,
  });

  // Surface the PayPal checkout outcome (?checkout=success|cancelled).
  useEffect(() => {
    const outcome = searchParams.get("checkout");
    if (!outcome) return;
    setBanner(
      outcome === "success"
        ? { kind: "success", text: "Subscription updated. Webhooks will reconcile shortly." }
        : { kind: "warning", text: "Checkout cancelled. No charges made." },
    );
    queryClient.invalidateQueries({ queryKey: ["billing", workspaceId] });
    const next = new URLSearchParams(searchParams);
    next.delete("checkout");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams, queryClient, workspaceId]);

  const checkout = useMutation({
    mutationFn: (planCode: string) =>
      createCheckoutSession(workspaceId!, planCode, interval),
    onSuccess: (resp) => {
      // PayPal is a full-page redirect to approve; activation lands via webhook
      // when the buyer returns to /billing?checkout=success.
      if (resp.paypal) {
        redirectToPayPalCheckout(resp.paypal);
      }
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not start checkout."),
  });

  const portal = useMutation({
    mutationFn: () => createPortalSession(workspaceId!),
    onSuccess: (resp) => {
      window.location.href = resp.url;
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not open billing portal."),
  });

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold text-ink sm:text-3xl">Plan & usage</h1>
        <p className="mt-2 text-sm text-slate-500">
          Subscriptions are billed by PayPal; webhook updates land here within seconds.
          Platform fees on your ad activity are shown below.
        </p>
        <p className="mt-2 text-sm text-slate-500">
          Have an AppSumo code?{" "}
          <a href="/appsumo/redeem" className="font-medium text-grape-700 hover:underline">
            Redeem it here
          </a>
          .
        </p>
      </header>

      {banner ? (
        <div
          className={cn(
            "rounded-lg px-3 py-2 text-sm",
            banner.kind === "success" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700",
          )}
          role="status"
        >
          {banner.text}
        </div>
      ) : null}

      {error ? (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </div>
      ) : null}

      {status.isLoading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : status.data ? (
        <CurrentPlanCard
          status={status.data}
          onPortal={() => portal.mutate()}
          portalPending={portal.isPending}
        />
      ) : null}

      <FeeDashboard
        summary={fees.data}
        invoices={invoices.data}
        loading={fees.isLoading || invoices.isLoading}
      />

      {status.data ? (
        <section>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
              All plans
            </h2>
            <IntervalToggle interval={interval} onChange={setInterval} />
          </div>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {status.data.available_plans.map((plan) => (
              <PlanCard
                key={plan.code}
                plan={plan}
                interval={interval}
                current={plan.code === status.data!.plan.code}
                onCheckout={(code) => checkout.mutate(code)}
                checkoutPending={checkout.isPending}
              />
            ))}
          </div>
        </section>
      ) : null}

      {status.data && status.data.subscription_provider === "none" ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <strong>Subscription billing isn't configured on this server yet.</strong> Plan
          limits still apply, but Upgrade actions will fail with a clear error until PayPal
          is set (<code>PAYPAL_CLIENT_ID</code> + <code>PAYPAL_CLIENT_SECRET</code> +{" "}
          <code>PAYPAL_WEBHOOK_ID</code> + <code>PAYPAL_PLAN_ID_*</code>).
        </div>
      ) : null}
    </div>
  );
}


function IntervalToggle({
  interval,
  onChange,
}: {
  interval: Interval;
  onChange: (i: Interval) => void;
}) {
  return (
    <div className="inline-flex items-center rounded-full border border-slate-200 bg-surface p-0.5 text-sm">
      {(["month", "year"] as const).map((opt) => (
        <button
          key={opt}
          type="button"
          onClick={() => onChange(opt)}
          className={cn(
            "rounded-full px-3 py-1 font-medium transition",
            interval === opt ? "bg-grape text-white" : "text-slate-500 hover:text-slate-700",
          )}
        >
          {opt === "month" ? "Monthly" : "Annual"}
          {opt === "year" ? <span className="ml-1 text-xs opacity-80">save ~2 mo</span> : null}
        </button>
      ))}
    </div>
  );
}


function CurrentPlanCard({
  status,
  onPortal,
  portalPending,
}: {
  status: BillingStatus;
  onPortal: () => void;
  portalPending: boolean;
}) {
  const { plan, usage } = status;
  const isLifetime = status.subscription_source === "appsumo";

  return (
    <Card>
      <CardHeader
        title={`${plan.display_name} plan`}
        subtitle={
          isLifetime
            ? "Lifetime · AppSumo — no recurring charge"
            : plan.monthly_price_usd === 0
              ? "Free tier"
              : plan.monthly_price_usd
                ? `$${plan.monthly_price_usd}/month`
                : undefined
        }
        action={
          isLifetime ? (
            <span className="pill pill-grape">Lifetime · AppSumo</span>
          ) : status.has_billing_customer ? (
            <Button variant="secondary" onClick={onPortal} disabled={portalPending}>
              {portalPending ? "Opening…" : "Manage billing"}
            </Button>
          ) : (
            <StatusPill status={status.subscription_status} />
          )
        }
      />
      <p className="mt-2 text-sm text-slate-500">{plan.description}</p>

      <div className="mt-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-4">
        <UsageBar
          label="AI credits · last 30 days"
          used={usage.credits_used_last_30d ?? 0}
          cap={plan.limits.monthly_credits ?? null}
        />
        <LimitTile label="Landing pages" cap={plan.limits.landing_pages} />
        <LimitTile label="Team members" cap={plan.limits.members} />
        <LlmSpendTile
          tokens={usage.llm_tokens_last_30d ?? 0}
          cents={usage.llm_cost_cents_last_30d ?? 0}
        />
      </div>

      {status.cancel_at_period_end ? (
        <div className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Subscription is set to cancel at the end of the current period.
        </div>
      ) : null}
    </Card>
  );
}


// ---------------------------------------------------------------------------
// Platform fees (the customer-facing view of the fee engine)
// ---------------------------------------------------------------------------

const FEE_TYPE_LABEL: Record<string, string> = {
  listing: "Campaign listing fees",
  run_flat: "Monthly platform fees",
  run_pct: "Spend-based fees",
};

function FeeDashboard({
  summary,
  invoices,
  loading,
}: {
  summary: WorkspaceFeeSummary | undefined;
  invoices: FeeInvoice[] | undefined;
  loading: boolean;
}) {
  const byType = Object.entries(summary?.by_type ?? {}).filter(([, v]) => v > 0);
  const hasInvoices = (invoices?.length ?? 0) > 0;

  return (
    <Card>
      <CardHeader
        title="Platform fees"
        subtitle={summary ? `Accrued this period · ${summary.period}` : "Fees on your ad activity"}
        action={
          <span className="text-2xl font-semibold text-ink">
            {summary ? money(summary.total_cents) : "—"}
          </span>
        }
      />
      <p className="mt-2 text-sm text-slate-500">
        AdGenieHQ charges a platform fee on ad activity managed through the app — a one-time
        listing fee per campaign plus a monthly run fee. Fees accrue here and are billed
        on an invoice.
      </p>

      {loading ? (
        <p className="mt-4 text-sm text-slate-400">Loading fees…</p>
      ) : (
        <>
          {byType.length ? (
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              {byType.map(([type, cents]) => (
                <div key={type} className="rounded-xl border border-slate-100 px-3 py-2">
                  <div className="text-[11px] uppercase tracking-wider text-slate-400">
                    {FEE_TYPE_LABEL[type] ?? type}
                  </div>
                  <div className="mt-1 text-xl font-semibold text-ink">{money(cents)}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-4 rounded-xl border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-400">
              No fees accrued yet. Fees appear here once you launch campaigns through AdGenieHQ.
            </div>
          )}

          {hasInvoices ? (
            <div className="mt-5">
              <div className="mb-2 text-sm font-semibold text-slate-600">Invoices</div>
              <div className="overflow-hidden rounded-xl border border-slate-100">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-left text-[11px] uppercase tracking-wider text-slate-400">
                    <tr>
                      <th className="px-3 py-2 font-medium">Period</th>
                      <th className="px-3 py-2 font-medium">Amount</th>
                      <th className="px-3 py-2 font-medium">Status</th>
                      <th className="px-3 py-2 font-medium" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {invoices!.map((inv) => (
                      <tr key={inv.id}>
                        <td className="px-3 py-2 text-slate-600">{inv.period ?? "—"}</td>
                        <td className="px-3 py-2 font-medium text-ink">{money(inv.amount_cents)}</td>
                        <td className="px-3 py-2">
                          <InvoiceStatusPill status={inv.status} />
                        </td>
                        <td className="px-3 py-2 text-right">
                          {inv.hosted_url ? (
                            <a
                              href={inv.hosted_url}
                              target="_blank"
                              rel="noreferrer"
                              className="font-medium text-grape-700 hover:underline"
                            >
                              {inv.status === "paid" ? "Receipt" : "Pay"}
                            </a>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </>
      )}
    </Card>
  );
}


function InvoiceStatusPill({ status }: { status: FeeInvoiceStatus }) {
  return (
    <span
      className={cn(
        "pill",
        status === "paid" && "pill-success",
        status === "open" && "pill-grape",
        status === "failed" && "pill-danger",
        (status === "void" || status === "draft") && "bg-slate-100 text-slate-600",
      )}
    >
      {status}
    </span>
  );
}


function UsageBar({
  label,
  used,
  cap,
}: {
  label: string;
  used: number;
  cap: number | null;
}) {
  const ratio = cap ? Math.min(1, used / cap) : 0;
  const tone = !cap || ratio < 0.7 ? "bg-grape" : ratio < 0.95 ? "bg-warning" : "bg-danger";

  return (
    <div className="rounded-xl border border-slate-100 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wider text-slate-400">{label}</div>
      <div className="mt-1 flex items-baseline gap-2 text-ink">
        <span className="text-2xl font-semibold">{used}</span>
        <span className="text-sm text-slate-400">/ {cap ?? "∞"}</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div
          className={cn("h-full rounded-full transition-all", tone)}
          style={{ width: cap ? `${Math.max(2, Math.round(ratio * 100))}%` : "100%" }}
        />
      </div>
    </div>
  );
}


function LimitTile({ label, cap }: { label: string; cap: number | null }) {
  return (
    <div className="rounded-xl border border-slate-100 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wider text-slate-400">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-ink">{cap ?? "Unlimited"}</div>
    </div>
  );
}


function LlmSpendTile({ tokens, cents }: { tokens: number; cents: number }) {
  const dollars = (cents / 100).toFixed(2);
  const tokensFormatted =
    tokens >= 1000 ? `${(tokens / 1000).toFixed(1)}k tokens` : `${tokens} tokens`;
  return (
    <div className="rounded-xl border border-slate-100 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wider text-slate-400">
        LLM spend · last 30 days
      </div>
      <div className="mt-1 flex items-baseline gap-2 text-ink">
        <span className="text-2xl font-semibold">${dollars}</span>
        <span className="text-xs text-slate-400">{tokensFormatted}</span>
      </div>
      <div className="mt-1 text-[11px] text-slate-400">
        Estimated; actuals depend on model pricing.
      </div>
    </div>
  );
}


function PlanCard({
  plan,
  interval,
  current,
  onCheckout,
  checkoutPending,
}: {
  plan: Plan;
  interval: Interval;
  current: boolean;
  onCheckout: (planCode: string) => void;
  checkoutPending: boolean;
}) {
  const annual = interval === "year";
  const price = annual ? plan.annual_price_usd : plan.monthly_price_usd;
  const suffix = annual ? "/ year" : "/ month";

  return (
    <Card
      className={cn(
        "flex flex-col gap-3 border",
        current ? "border-grape-200 ring-2 ring-grape-100" : "border-slate-100",
      )}
    >
      <div>
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-base font-semibold text-ink">{plan.display_name}</h3>
          {current ? (
            <span className="pill pill-grape">Current</span>
          ) : plan.is_paid ? (
            <span className="pill bg-slate-100 text-slate-600">Paid</span>
          ) : (
            <span className="pill bg-slate-100 text-slate-600">Default</span>
          )}
        </div>
        <p className="mt-1 text-xs text-slate-500">{plan.description}</p>
      </div>

      <div className="text-2xl font-semibold text-ink">
        {price === 0 ? "Free" : price != null ? `$${price}` : "—"}
        {price && price > 0 ? <span className="ml-1 text-xs text-slate-400">{suffix}</span> : null}
      </div>

      <ul className="flex flex-col gap-1 text-xs text-slate-600">
        <li>{plan.limits.monthly_credits ?? "Unlimited"} AI credits / mo</li>
        <li>{plan.limits.landing_pages ?? "Unlimited"} landing pages</li>
        <li>{plan.limits.members ?? "Unlimited"} team members</li>
      </ul>

      {plan.is_paid && !current ? (
        <Button onClick={() => onCheckout(plan.code)} disabled={checkoutPending}>
          {checkoutPending ? "Opening checkout…" : "Upgrade"}
        </Button>
      ) : null}
    </Card>
  );
}


function StatusPill({ status }: { status: SubscriptionStatusValue }) {
  return (
    <span
      className={cn(
        "pill",
        status === "active" && "pill-success",
        status === "trialing" && "pill-grape",
        status === "past_due" && "pill-warning",
        status === "canceled" && "pill-danger",
        status === "none" && "bg-slate-100 text-slate-600",
      )}
    >
      {status}
    </span>
  );
}
