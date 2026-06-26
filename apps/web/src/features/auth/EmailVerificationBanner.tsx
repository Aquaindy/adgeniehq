import { useState } from "react";

import { ApiError } from "@/lib/api-client";
import { verifyEmailResend } from "@/lib/auth";
import { useAuthStore } from "@/stores/auth-store";

/**
 * Soft email-verification nudge shown across the app shell until the signed-in
 * user verifies. Verification never blocks access. Google-login users arrive
 * pre-verified, so they never see this.
 */
export function EmailVerificationBanner() {
  const user = useAuthStore((s) => s.user);
  const [dismissed, setDismissed] = useState(false);
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!user || user.email_verified_at || dismissed) return null;

  async function resend() {
    setSending(true);
    setError(null);
    try {
      await verifyEmailResend();
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not resend.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="border-b border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-900 sm:px-6">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2">
        <span>
          {sent
            ? "Verification email sent — check your inbox (and spam)."
            : `Verify your email (${user.email}) to secure your account.`}
        </span>
        <div className="flex items-center gap-3">
          {error ? <span className="text-red-700">{error}</span> : null}
          {!sent ? (
            <button
              type="button"
              onClick={resend}
              disabled={sending}
              className="font-medium text-amber-900 underline underline-offset-2 disabled:opacity-50"
            >
              {sending ? "Sending…" : "Resend email"}
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => setDismissed(true)}
            aria-label="Dismiss"
            className="text-amber-700 hover:text-amber-900"
          >
            ✕
          </button>
        </div>
      </div>
    </div>
  );
}
