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
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { BillingStatus, Plan, SubscriptionStatusValue } from "@/types/api";


export function BillingPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<{ kind: "success" | "warning"; text: string } | null>(null);

  const status = useQuery({
    queryKey: ["billing", workspaceId],
    queryFn: () => getBillingStatus(workspaceId!),
    enabled: !!workspaceId,
  });

  // Surface Stripe redirect outcome
  useEffect(() => {
    const stripe = searchParams.get("stripe");
    if (!stripe) return;
    setBanner(
      stripe === "success"
        ? { kind: "success", text: "Subscription updated. Webhooks will reconcile shortly." }
        : { kind: "warning", text: "Checkout cancelled. No charges made." },
    );
    queryClient.invalidateQueries({ queryKey: ["billing", workspaceId] });
    const next = new URLSearchParams(searchParams);
    next.delete("stripe");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams, queryClient, workspaceId]);

  const checkout = useMutation({
    mutationFn: (planCode: string) => createCheckoutSession(workspaceId!, planCode),
    onSuccess: (resp) => {
      window.location.href = resp.url;
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not start checkout."),
  });

  const portal = useMutation({
    mutationFn: () => createPortalSession(workspaceId!),
    onSuccess: (resp) => {
      window.location.href = resp.url;
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not open portal."),
  });

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold text-ink sm:text-3xl">Plan & usage</h1>
        <p className="mt-2 text-sm text-slate-500">
          Upgrade to lift agent-run, landing-page, and team-size limits. Plan changes are
          processed by Stripe; webhook updates land here within seconds.
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

      {status.data ? (
        <PlanGrid
          status={status.data}
          onCheckout={(plan) => checkout.mutate(plan)}
          checkoutPending={checkout.isPending}
        />
      ) : null}

      {status.data && !status.data.stripe_configured ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <strong>Stripe is not configured for this server.</strong> Plan limits still apply, but
          Upgrade actions will fail with a clear error until <code>STRIPE_SECRET_KEY</code> and the
          relevant <code>STRIPE_PRICE_ID_*</code> env vars are set.
        </div>
      ) : null}
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
          label="Agent runs · last 30 days"
          used={usage.agent_runs_last_30d}
          cap={plan.limits.agent_runs_per_month}
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
      <div className="mt-1 text-2xl font-semibold text-ink">
        {cap ?? "Unlimited"}
      </div>
    </div>
  );
}


function LlmSpendTile({ tokens, cents }: { tokens: number; cents: number }) {
  // Format: $XX.XX, with the token count as a secondary annotation. We keep
  // the dollar figure prominent because that's the part operators react to.
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


function PlanGrid({
  status,
  onCheckout,
  checkoutPending,
}: {
  status: BillingStatus;
  onCheckout: (planCode: string) => void;
  checkoutPending: boolean;
}) {
  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500">
        All plans
      </h2>
      <div className="grid gap-4 lg:grid-cols-4 md:grid-cols-2">
        {status.available_plans.map((plan) => (
          <PlanCard
            key={plan.code}
            plan={plan}
            current={plan.code === status.plan.code}
            onCheckout={onCheckout}
            checkoutPending={checkoutPending}
          />
        ))}
      </div>
    </section>
  );
}


function PlanCard({
  plan,
  current,
  onCheckout,
  checkoutPending,
}: {
  plan: Plan;
  current: boolean;
  onCheckout: (planCode: string) => void;
  checkoutPending: boolean;
}) {
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
        {plan.monthly_price_usd === 0
          ? "Free"
          : plan.monthly_price_usd != null
            ? `$${plan.monthly_price_usd}`
            : "—"}
        {plan.monthly_price_usd && plan.monthly_price_usd > 0 ? (
          <span className="ml-1 text-xs text-slate-400">/ month</span>
        ) : null}
      </div>

      <ul className="flex flex-col gap-1 text-xs text-slate-600">
        <li>
          {plan.limits.agent_runs_per_month ?? "Unlimited"} agent runs / 30 days
        </li>
        <li>{plan.limits.landing_pages ?? "Unlimited"} landing pages</li>
        <li>{plan.limits.members ?? "Unlimited"} team members</li>
      </ul>

      {plan.is_paid && !current ? (
        <Button
          onClick={() => onCheckout(plan.code)}
          disabled={checkoutPending}
        >
          {checkoutPending ? "Opening Stripe…" : "Upgrade"}
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
