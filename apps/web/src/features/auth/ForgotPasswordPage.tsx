import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { AuthLayout } from "@/features/auth/AuthLayout";
import { ApiError } from "@/lib/api-client";
import { passwordResetRequest } from "@/lib/auth";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await passwordResetRequest(email);
      setSubmitted(true);
    } catch (err) {
      // Backend returns 204 even when the email isn't registered, so this
      // path only fires on transport errors.
      setError(err instanceof ApiError ? err.message : "Could not request reset.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title="Reset your password"
      subtitle="We'll email a single-use link if this account exists."
      footer={
        <span>
          Remembered it?{" "}
          <Link className="font-medium text-grape-700 hover:text-grape-800" to="/login">
            Sign in
          </Link>
        </span>
      }
    >
      {submitted ? (
        <div className="rounded-lg bg-grape-soft px-4 py-3 text-sm text-grape-700">
          If an account exists for <strong>{email}</strong>, a reset link is
          on its way. Check your inbox in the next few minutes.
        </div>
      ) : (
        <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
          <label className="flex flex-col gap-1.5 text-sm" htmlFor="email">
            <span className="font-medium text-slate-text">Work email</span>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
            />
          </label>
          {error ? (
            <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
              {error}
            </div>
          ) : null}
          <Button type="submit" disabled={submitting}>
            {submitting ? "Sending…" : "Email me a reset link"}
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}
