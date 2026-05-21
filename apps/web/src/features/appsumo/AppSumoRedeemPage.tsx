import { useEffect, useState } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Logomark } from "@/components/Logomark";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ApiError } from "@/lib/api-client";
import {
  getAppSumoStatus,
  redeemAppSumoCode,
  type AppSumoStatus,
} from "@/lib/appsumo";
import { listWorkspaces } from "@/lib/workspaces";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";
import { useWorkspaceStore } from "@/stores/workspace-store";

/**
 * Public AppSumo redemption page, intentionally OUTSIDE the dashboard shell so
 * AppSumo can link buyers straight to getadvanta.app/appsumo/redeem. Requires
 * an account + workspace to actually grant the lifetime plan; unauthenticated
 * visitors get a clear sign-up/sign-in path.
 */
export function AppSumoRedeemPage() {
  const user = useAuthStore((s) => s.user);
  const isAuthed = !!user;

  return (
    <div className="min-h-screen bg-cloud">
      <header className="border-b border-slate-200 bg-surface/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-3xl items-center justify-between px-4 sm:px-6">
          <Link to="/" className="flex items-center gap-2">
            <Logomark />
            <span className="text-sm font-semibold text-ink">AdVanta AI</span>
          </Link>
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto max-w-xl px-4 py-12 sm:px-6 sm:py-16">
        <div className="inline-flex items-center gap-2 rounded-full border border-grape-200 bg-grape-100 px-3 py-1 text-xs font-medium uppercase tracking-wider text-grape-700">
          <span className="h-1.5 w-1.5 rounded-full bg-grape-700" />
          AppSumo · Lifetime Deal
        </div>
        <h1 className="mt-4 text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
          Redeem your AppSumo code
        </h1>
        <p className="mt-3 text-base text-slate-600">
          Enter the code from your AppSumo purchase to unlock AdVanta AI for
          life. Stack up to three codes to climb tiers — more agent runs,
          landing pages, and seats at each level.
        </p>

        <div className="mt-8">
          {isAuthed ? <Redeemer /> : <SignedOutCta />}
        </div>

        <p className="mt-8 text-center text-xs text-slate-400">
          Already redeemed? Manage your plan in{" "}
          <Link to="/settings/billing" className="text-grape-700 hover:underline">
            Billing
          </Link>
          .
        </p>
      </main>
    </div>
  );
}


function SignedOutCta() {
  return (
    <div className="card p-6 sm:p-8">
      <h2 className="text-lg font-semibold text-ink">
        Create your account to redeem
      </h2>
      <p className="mt-2 text-sm text-slate-600">
        Redemption attaches the lifetime plan to a workspace, so you'll need an
        AdVanta account first. It takes under a minute — then come back here and
        enter your code.
      </p>
      <div className="mt-6 flex flex-wrap gap-3">
        <Link
          to="/register"
          className="rounded-xl bg-grape px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-grape-800"
        >
          Create account
        </Link>
        <Link
          to="/login"
          className="rounded-xl border border-slate-200 bg-surface px-5 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
        >
          Sign in
        </Link>
      </div>
    </div>
  );
}


function Redeemer() {
  const storeWorkspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();

  const workspaces = useQuery({
    queryKey: ["workspaces"],
    queryFn: listWorkspaces,
  });

  const [workspaceId, setWorkspaceId] = useState<string | null>(
    storeWorkspaceId,
  );
  const [code, setCode] = useState("");
  const [success, setSuccess] = useState<string | null>(null);

  // Default the selected workspace once the list loads.
  useEffect(() => {
    if (workspaceId) return;
    const list = workspaces.data;
    if (list && list.length > 0) {
      const fallback = list[0]?.id ?? null;
      setWorkspaceId(storeWorkspaceId ?? fallback);
    }
  }, [workspaces.data, workspaceId, storeWorkspaceId]);

  const status = useQuery({
    queryKey: ["appsumo-status", workspaceId],
    queryFn: () => getAppSumoStatus(workspaceId as string),
    enabled: !!workspaceId,
  });

  const redeem = useMutation({
    mutationFn: (value: string) =>
      redeemAppSumoCode(workspaceId as string, value),
    onSuccess: (data: AppSumoStatus) => {
      setSuccess(
        `Redeemed! You're now on ${data.plan_display_name ?? "your lifetime plan"} (Tier ${data.tier}).`,
      );
      setCode("");
      queryClient.setQueryData(["appsumo-status", workspaceId], data);
      queryClient.invalidateQueries({ queryKey: ["billing", workspaceId] });
    },
  });

  if (workspaces.isLoading) {
    return <div className="card p-6 text-sm text-slate-500">Loading…</div>;
  }

  if (!workspaces.data || workspaces.data.length === 0) {
    return (
      <div className="card p-6 sm:p-8">
        <h2 className="text-lg font-semibold text-ink">
          Create a workspace first
        </h2>
        <p className="mt-2 text-sm text-slate-600">
          Lifetime plans attach to a workspace. Create one, then return here to
          redeem your code.
        </p>
        <Link
          to="/workspaces"
          className="mt-6 inline-block rounded-xl bg-grape px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-grape-800"
        >
          Create a workspace
        </Link>
      </div>
    );
  }

  const s = status.data;
  const atMax = s ? !s.can_stack_more : false;
  const errorMessage =
    redeem.error instanceof ApiError
      ? redeem.error.message
      : redeem.error
        ? "Something went wrong. Please try again."
        : null;

  return (
    <div className="card p-6 sm:p-8">
      {workspaces.data.length > 1 ? (
        <label className="block">
          <span className="text-xs font-medium uppercase tracking-wider text-slate-400">
            Redeem into workspace
          </span>
          <select
            value={workspaceId ?? ""}
            onChange={(e) => {
              setWorkspaceId(e.target.value);
              setSuccess(null);
              redeem.reset();
            }}
            className="mt-1 w-full rounded-xl border border-slate-200 bg-surface px-3 py-2 text-sm text-ink"
          >
            {workspaces.data.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <p className="text-sm text-slate-600">
          Redeeming into{" "}
          <span className="font-semibold text-ink">
            {workspaces.data[0]?.name}
          </span>
          .
        </p>
      )}

      {s ? <TierMeter status={s} className="mt-5" /> : null}

      {atMax ? (
        <div className="mt-5 rounded-xl border border-grape-200 bg-grape-100 px-4 py-3 text-sm font-medium text-grape-700">
          🎉 You're at the top tier ({s?.max_tier} codes). Nothing more to
          stack on this workspace.
        </div>
      ) : (
        <form
          className="mt-5"
          onSubmit={(e) => {
            e.preventDefault();
            setSuccess(null);
            if (code.trim()) redeem.mutate(code.trim());
          }}
        >
          <label className="block">
            <span className="text-xs font-medium uppercase tracking-wider text-slate-400">
              AppSumo code
            </span>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="ADV-XXXX-XXXX-XXXX"
              autoComplete="off"
              spellCheck={false}
              className="mt-1 w-full rounded-xl border border-slate-200 bg-surface px-3 py-2.5 font-mono text-sm uppercase tracking-wide text-ink placeholder:text-slate-400"
            />
          </label>

          {errorMessage ? (
            <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-500/15 dark:text-red-300">
              {errorMessage}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={redeem.isPending || !code.trim() || !workspaceId}
            className="mt-4 w-full rounded-xl bg-grape px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-grape-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {redeem.isPending ? "Redeeming…" : "Redeem code"}
          </button>
        </form>
      )}

      {success ? (
        <p className="mt-4 rounded-lg bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
          {success}
        </p>
      ) : null}

      {s && s.can_stack_more && s.codes_redeemed > 0 ? (
        <p className="mt-4 text-xs text-slate-500">
          Got more codes? Redeem them above to stack up to Tier {s.max_tier}.
        </p>
      ) : null}
    </div>
  );
}


function TierMeter({
  status,
  className,
}: {
  status: AppSumoStatus;
  className?: string;
}) {
  const steps = Array.from({ length: status.max_tier }, (_, i) => i + 1);
  return (
    <div className={className}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-ink">
          {status.tier > 0
            ? `${status.plan_display_name ?? `Tier ${status.tier}`}`
            : "No codes redeemed yet"}
        </span>
        <span className="text-xs text-slate-400">
          {status.codes_redeemed} / {status.max_tier} codes
        </span>
      </div>
      <div className="mt-2 flex gap-1.5">
        {steps.map((step) => (
          <span
            key={step}
            className={cn(
              "h-2 flex-1 rounded-full",
              step <= status.tier ? "bg-grape" : "bg-slate-200",
            )}
          />
        ))}
      </div>
    </div>
  );
}
