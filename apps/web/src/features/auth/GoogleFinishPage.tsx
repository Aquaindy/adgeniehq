import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { AuthLayout } from "@/features/auth/AuthLayout";
import { ApiError } from "@/lib/api-client";
import { refreshRequest } from "@/lib/auth";
import { useAuthStore } from "@/stores/auth-store";

/**
 * After /auth/google/callback the backend sets the adgeniehq_refresh cookie
 * and 302-redirects here. We call /auth/refresh to mint an access token,
 * stash the session, and route the user where they were heading.
 */
export function GoogleFinishPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const setSession = useAuthStore((s) => s.setSession);

  const to = params.get("to") || "/";

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const session = await refreshRequest();
        if (cancelled) return;
        setSession(session);
        navigate(to, { replace: true });
      } catch (err) {
        if (cancelled) return;
        const code = err instanceof ApiError ? err.code : null;
        const msg = code ? `google_${code}` : "google_finish_failed";
        navigate(`/login?error=${msg}`, { replace: true });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [navigate, setSession, to]);

  return (
    <AuthLayout title="Signing you in…" subtitle="One moment.">
      <div className="text-sm text-slate-500">
        Finishing Google sign-in. If this takes more than a few seconds,
        refresh the page or try email + password.
      </div>
    </AuthLayout>
  );
}
