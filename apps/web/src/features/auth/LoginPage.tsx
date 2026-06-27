import { type FormEvent, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { AuthLayout } from "@/features/auth/AuthLayout";
import { GoogleSignInButton } from "@/features/auth/GoogleSignInButton";
import { ApiError } from "@/lib/api-client";
import { loginRequest } from "@/lib/auth";
import { useAuthStore } from "@/stores/auth-store";

type LocationState = { from?: { pathname: string } } | null;

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const setSession = useAuthStore((s) => s.setSession);

  const googleErrorCode = params.get("error");
  const googleError = googleErrorCode?.startsWith("google_")
    ? GOOGLE_ERROR_MESSAGES[googleErrorCode] ?? "Google sign-in failed."
    : null;

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [otpRequired, setOtpRequired] = useState(false);
  const [remember, setRemember] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(googleError);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await loginRequest({
        email,
        password,
        otp_code: otpCode || undefined,
        remember_me: remember,
      });
      setSession(response);
      const next = (location.state as LocationState)?.from?.pathname ?? "/dashboard";
      navigate(next, { replace: true });
    } catch (err) {
      // The backend signals 2FA-required with a `two_factor_required` code.
      // First time we see it, just unhide the OTP field — don't surface a
      // scary error.
      if (err instanceof ApiError && err.code === "two_factor_required") {
        setOtpRequired(true);
        setError(null);
      } else if (err instanceof ApiError && err.code === "two_factor_invalid_code") {
        setOtpRequired(true);
        setError("That 2FA code didn't work — try the next one.");
      } else {
        setError(err instanceof ApiError ? err.message : "Sign-in failed.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title="Sign in to AdGenieHQ"
      subtitle="Connect your accounts and let your AI growth team get to work."
      footer={
        <span>
          Don't have an account?{" "}
          <Link className="font-medium text-grape-700 hover:text-grape-800" to="/register">
            Create one
          </Link>
          {" · "}
          <Link className="font-medium text-grape-700 hover:text-grape-800" to="/forgot-password">
            Forgot password
          </Link>
        </span>
      }
    >
      <div className="flex flex-col gap-3">
        <GoogleSignInButton />
        <div className="relative my-1 flex items-center">
          <div className="flex-1 border-t border-slate-200" />
          <span className="px-2 text-xs uppercase tracking-wider text-slate-400">
            or
          </span>
          <div className="flex-1 border-t border-slate-200" />
        </div>
      </div>
      <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
        <Field
          id="email"
          label="Work email"
          type="email"
          value={email}
          onChange={setEmail}
          autoComplete="email"
          required
        />
        <Field
          id="password"
          label="Password"
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
          required
        />
        {otpRequired ? (
          <Field
            id="otp_code"
            label="2FA code"
            value={otpCode}
            onChange={setOtpCode}
            autoComplete="one-time-code"
            required
          />
        ) : null}
        <label className="flex items-center gap-2 text-sm text-slate-text">
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
            className="h-4 w-4 rounded border-slate-300 text-grape focus:ring-2 focus:ring-grape-200"
          />
          Keep me signed in
        </label>
        {error ? (
          <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
            {error}
          </div>
        ) : null}
        <Button type="submit" disabled={submitting}>
          {submitting
            ? "Signing in…"
            : otpRequired
              ? "Verify code"
              : "Sign in"}
        </Button>
      </form>
    </AuthLayout>
  );
}

// Surface human-readable copy for the `error=google_*` query params that
// the backend appends when /auth/google/callback can't complete the round-trip.
const GOOGLE_ERROR_MESSAGES: Record<string, string> = {
  google_invalid_state: "Google sign-in expired. Try again.",
  google_no_code: "Google didn't return an authorization code. Try again.",
  google_exchange_failed:
    "We couldn't verify the response from Google. Try again or use email + password.",
  google_access_denied: "Google sign-in was cancelled.",
};


function Field({
  id,
  label,
  value,
  onChange,
  type = "text",
  autoComplete,
  required,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  autoComplete?: string;
  required?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1.5 text-sm" htmlFor={id}>
      <span className="font-medium text-slate-text">{label}</span>
      <input
        id={id}
        type={type}
        value={value}
        autoComplete={autoComplete}
        required={required}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
      />
    </label>
  );
}
