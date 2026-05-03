import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { TwoFactorCard } from "@/features/settings/TwoFactorCard";
import { logoutRequest } from "@/lib/auth";
import { useAuthStore } from "@/stores/auth-store";
import { useWorkspaceStore } from "@/stores/workspace-store";

export function ProfilePage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const clearAuth = useAuthStore((s) => s.clear);
  const setCurrent = useWorkspaceStore((s) => s.setCurrentWorkspaceId);

  async function onSignOut() {
    try {
      await logoutRequest();
    } catch {
      // ignore — we always clear local state
    }
    clearAuth();
    setCurrent(null);
    navigate("/login", { replace: true });
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold text-ink sm:text-3xl">Your account</h1>
      </header>

      <Card>
        <CardHeader title="Account details" />
        <dl className="mt-4 grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-slate-400">Name</dt>
            <dd className="mt-0.5 font-medium text-ink">{user?.full_name ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-400">Email</dt>
            <dd className="mt-0.5 font-medium text-ink">{user?.email}</dd>
          </div>
          <div>
            <dt className="text-slate-400">Account ID</dt>
            <dd className="mt-0.5 break-all font-mono text-xs text-slate-500">{user?.id}</dd>
          </div>
          <div>
            <dt className="text-slate-400">Joined</dt>
            <dd className="mt-0.5 font-medium text-ink">
              {user?.created_at ? new Date(user.created_at).toLocaleString() : "—"}
            </dd>
          </div>
        </dl>
      </Card>

      <TwoFactorCard />

      <Card>
        <CardHeader
          title="Session"
          subtitle="Sign out of this browser. Your refresh cookie will be cleared."
        />
        <div className="mt-4">
          <Button variant="secondary" onClick={onSignOut}>
            Sign out
          </Button>
        </div>
      </Card>
    </div>
  );
}
