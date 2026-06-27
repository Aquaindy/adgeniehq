import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { AuthLayout } from "@/features/auth/AuthLayout";
import { GoogleSignInButton } from "@/features/auth/GoogleSignInButton";
import { ApiError } from "@/lib/api-client";
import { registerRequest } from "@/lib/auth";
import { useAuthStore } from "@/stores/auth-store";

export function RegisterPage() {
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const response = await registerRequest({
        email,
        password,
        full_name: fullName.trim() || undefined,
      });
      setSession(response);
      navigate("/workspaces", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-up failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title="Create your AdGenieHQ account"
      subtitle="Free to start. Connect real accounts to activate your AI growth team."
      footer={
        <span>
          Already have an account?{" "}
          <Link className="font-medium text-grape-700 hover:text-grape-800" to="/login">
            Sign in
          </Link>
        </span>
      }
    >
      <div className="flex flex-col gap-3">
        <GoogleSignInButton label="Sign up with Google" />
        <div className="relative my-1 flex items-center">
          <div className="flex-1 border-t border-slate-200" />
          <span className="px-2 text-xs uppercase tracking-wider text-slate-400">
            or
          </span>
          <div className="flex-1 border-t border-slate-200" />
        </div>
      </div>
      <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
        <label className="flex flex-col gap-1.5 text-sm" htmlFor="register-name">
          <span className="font-medium text-slate-text">Name</span>
          <input
            id="register-name"
            type="text"
            autoComplete="name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm" htmlFor="register-email">
          <span className="font-medium text-slate-text">Work email</span>
          <input
            id="register-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm" htmlFor="register-password">
          <span className="font-medium text-slate-text">Password</span>
          <input
            id="register-password"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
          />
          <span className="text-xs text-slate-400">Minimum 8 characters.</span>
        </label>
        {error ? (
          <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
            {error}
          </div>
        ) : null}
        <Button type="submit" disabled={submitting}>
          {submitting ? "Creating account…" : "Create account"}
        </Button>
      </form>
    </AuthLayout>
  );
}
