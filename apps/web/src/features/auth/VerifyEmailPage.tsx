import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { AuthLayout } from "@/features/auth/AuthLayout";
import { ApiError } from "@/lib/api-client";
import { verifyEmailConfirm } from "@/lib/auth";
import { useAuthStore } from "@/stores/auth-store";

type Status = "verifying" | "success" | "error";

/**
 * Public page reached from the verification email link (`/verify-email?token=`).
 * Confirms the token on mount; if the same user is signed in on this browser,
 * refreshes their cached record so the "verify your email" banner clears.
 */
export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const setUser = useAuthStore((s) => s.setUser);
  const currentUser = useAuthStore((s) => s.user);

  const [status, setStatus] = useState<Status>("verifying");
  const [error, setError] = useState<string | null>(null);
  const ran = useRef(false);

  useEffect(() => {
    // Guard against React 18 StrictMode's double-invoke — the token is
    // single-use, so a second POST would 400.
    if (ran.current) return;
    ran.current = true;

    if (!token) {
      setStatus("error");
      setError("This verification link is missing its token.");
      return;
    }

    verifyEmailConfirm(token)
      .then((user) => {
        setStatus("success");
        if (currentUser && currentUser.id === user.id) {
          setUser(user);
        }
      })
      .catch((err) => {
        setStatus("error");
        setError(
          err instanceof ApiError ? err.message : "Could not verify this email.",
        );
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <AuthLayout
      title="Email verification"
      subtitle="Confirming your email address."
      footer={
        <span>
          <Link
            className="font-medium text-grape-700 hover:text-grape-800"
            to="/dashboard"
          >
            Go to dashboard
          </Link>
        </span>
      }
    >
      {status === "verifying" ? (
        <div className="rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-500">
          Verifying your email…
        </div>
      ) : status === "success" ? (
        <div className="rounded-lg bg-grape-soft px-4 py-3 text-sm text-grape-700">
          Your email is verified — you're all set.
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <div
            className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700"
            role="alert"
          >
            {error}
          </div>
          <p className="text-sm text-slate-500">
            Sign in, then use the “Resend email” link in the banner to get a
            fresh verification link.
          </p>
        </div>
      )}
    </AuthLayout>
  );
}
