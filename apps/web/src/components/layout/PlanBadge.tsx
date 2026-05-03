import { Link } from "react-router-dom";

import { usePlanStatus } from "@/hooks/usePlanStatus";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";

/**
 * Always-visible plan indicator in the topbar. Clicking it routes to the
 * Billing tab — the natural next destination if a user is wondering
 * about their plan or limits.
 *
 * Hidden for superusers — they see the AdminBadge instead, since plan
 * tier doesn't gate them. (Their workspace's tier is still visible
 * inside Settings → Billing for context.)
 */
export function PlanBadge() {
  const isSuperuser = useAuthStore((s) => s.user?.is_superuser ?? false);
  const status = usePlanStatus();
  if (isSuperuser) return null;
  if (!status.data) return null;

  const code = status.data.plan.code;
  const label = status.data.plan.display_name;

  const tone =
    code === "agency"
      ? "bg-grape text-white"
      : code === "pro"
        ? "bg-grape-100 text-grape-700"
        : code === "starter"
          ? "bg-grape-50 text-grape-700"
          : "bg-slate-100 text-slate-600"; // free / fallback

  return (
    <Link
      to="/settings/billing"
      title={`Plan: ${label}`}
      className={cn(
        "hidden sm:inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold transition hover:opacity-90",
        tone,
      )}
    >
      {label}
    </Link>
  );
}
