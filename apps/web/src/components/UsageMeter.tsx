import { Link } from "react-router-dom";

import { usePlanStatus } from "@/hooks/usePlanStatus";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";
import type { BillingStatus, PlanLimits, Usage } from "@/types/api";

/**
 * Resource keys that map a feature page to a (cap, used) pair on the
 * billing status. Adding a new gated resource means: add it here, hit
 * the corresponding `assert_within_*_limit` on the backend, and drop
 * `<UsageMeter resource="…" />` at the top of the page.
 */
export type UsageResource =
  | "agent_runs"
  | "content_drafts"
  | "outreach_emails"
  | "ab_tests"
  | "outbound_writes"
  | "llm_tokens";

const COPY: Record<UsageResource, { label: string; unit: string }> = {
  agent_runs: { label: "Agent runs", unit: "runs" },
  content_drafts: { label: "Content drafts", unit: "drafts" },
  outreach_emails: { label: "Outreach emails", unit: "sends" },
  ab_tests: { label: "A/B tests", unit: "tests" },
  outbound_writes: { label: "Provider writes", unit: "writes" },
  llm_tokens: { label: "LLM tokens", unit: "tokens" },
};

function readCap(limits: PlanLimits, resource: UsageResource): number | null {
  switch (resource) {
    case "agent_runs":
      return limits.agent_runs_per_month;
    case "content_drafts":
      return limits.content_drafts_per_month ?? null;
    case "outreach_emails":
      return limits.outreach_emails_per_month ?? null;
    case "ab_tests":
      return limits.ab_tests_per_month ?? null;
    case "outbound_writes":
      return limits.outbound_writes_per_month ?? null;
    case "llm_tokens":
      return limits.llm_tokens_per_month ?? null;
  }
}

function readUsed(usage: Usage, resource: UsageResource): number {
  switch (resource) {
    case "agent_runs":
      return usage.agent_runs_last_30d ?? 0;
    case "content_drafts":
      return usage.content_drafts_last_30d ?? 0;
    case "outreach_emails":
      return usage.outreach_emails_last_30d ?? 0;
    case "ab_tests":
      return usage.ab_tests_last_30d ?? 0;
    case "outbound_writes":
      return usage.outbound_writes_last_30d ?? 0;
    case "llm_tokens":
      return usage.llm_tokens_last_30d ?? 0;
  }
}


/**
 * Subtle usage strip that lives at the top of plan-gated pages. Renders:
 *   - "32 / 100 agent runs · 30-day window"  (with a thin progress bar)
 *   - amber tint at ≥75% used, red at ≥90% — a soft pre-warning before
 *     the user hits the 402.
 *   - "Unlimited" label when cap is null (Agency tier).
 *
 * Resilient to loading + missing billing data (returns null).
 */
export function UsageMeter({ resource }: { resource: UsageResource }) {
  const status = usePlanStatus();
  const isSuperuser = useAuthStore((s) => s.user?.is_superuser ?? false);
  const data: BillingStatus | undefined = status.data;
  if (!data) return null;

  const cap = readCap(data.plan.limits, resource);
  const used = readUsed(data.usage, resource);
  const copy = COPY[resource];

  // Superuser bypass — limits don't apply to interactive sessions for
  // back-office staff, and the UI should reflect that honestly so they
  // know what they're doing. Sits above plan-tier rendering on purpose.
  if (isSuperuser) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-warning/30 bg-warning/5 px-4 py-2.5 text-xs text-warning">
        <span className="inline-flex items-center gap-1 font-semibold">
          <span aria-hidden className="size-1.5 rounded-full bg-warning" />
          Admin
        </span>
        <span className="text-slate-600">·</span>
        <span className="text-slate-700">
          Plan limits bypassed for your session — workspace plan ({data.plan.display_name}) shows {used.toLocaleString()}{" "}
          {copy.unit} used in the last 30 days.
        </span>
      </div>
    );
  }

  // Unlimited tier — show a quiet "Unlimited" badge instead of a bar.
  if (cap === null) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs text-slate-500">
        <span className="font-semibold text-grape-700">{data.plan.display_name}</span>
        <span>·</span>
        <span>{copy.label}: unlimited this period</span>
      </div>
    );
  }

  const pct = cap === 0 ? 100 : Math.min(100, Math.round((used / cap) * 100));
  const tone =
    pct >= 90
      ? { bar: "bg-red-500", text: "text-red-700", border: "border-red-200", bg: "bg-red-50" }
      : pct >= 75
        ? { bar: "bg-amber-500", text: "text-amber-800", border: "border-amber-200", bg: "bg-amber-50" }
        : { bar: "bg-grape", text: "text-slate-600", border: "border-slate-200", bg: "bg-white" };

  return (
    <div
      className={cn(
        "flex flex-col gap-1.5 rounded-xl border px-4 py-2.5",
        tone.border,
        tone.bg,
      )}
    >
      <div className={cn("flex items-center justify-between text-xs", tone.text)}>
        <span>
          <span className="font-semibold">{used.toLocaleString()}</span>
          <span className="text-slate-400"> / </span>
          <span>{cap.toLocaleString()}</span>{" "}
          <span>
            {copy.label.toLowerCase()} · 30-day window · {data.plan.display_name}
          </span>
        </span>
        {pct >= 75 ? (
          <Link
            to="/settings/billing"
            className="font-semibold underline-offset-2 hover:underline"
          >
            Upgrade
          </Link>
        ) : (
          <Link
            to="/settings/billing"
            className="text-slate-400 hover:text-slate-600"
          >
            Manage plan
          </Link>
        )}
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className={cn("h-full rounded-full transition-all", tone.bar)}
          style={{ width: `${pct}%` }}
          aria-label={`${pct}% used`}
        />
      </div>
    </div>
  );
}
