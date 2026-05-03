import { Link } from "react-router-dom";

import { useAuthStore } from "@/stores/auth-store";

/**
 * Always-visible "Admin" pill for superusers. Renders next to the
 * PlanBadge in the topbar so the user-level elevated status is
 * distinct from the workspace-level plan tier.
 *
 * Clicking it routes to `/admin` which is the superuser-only console.
 */
export function AdminBadge() {
  const user = useAuthStore((s) => s.user);
  if (!user?.is_superuser) return null;

  return (
    <Link
      to="/admin"
      title="Superuser — plan limits bypassed for your interactive sessions"
      className="hidden sm:inline-flex items-center gap-1 rounded-full bg-warning/10 px-2.5 py-1 text-xs font-semibold text-warning ring-1 ring-warning/30 transition hover:bg-warning/20"
    >
      <span aria-hidden className="size-1.5 rounded-full bg-warning" />
      Admin
    </Link>
  );
}
