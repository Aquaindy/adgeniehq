import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import {
  meRequest,
  twoFactorConfirm,
  twoFactorDisable,
  twoFactorSetup,
} from "@/lib/auth";
import type { TwoFactorSetupResponse } from "@/types/api";
import { useAuthStore } from "@/stores/auth-store";

/**
 * Profile-page card that walks the user through TOTP-2FA enrollment, surfaces
 * recovery codes once, and lets them disable 2FA with a current code.
 *
 * The component covers all three lifecycle states:
 *   - disabled (default for new accounts)        → "Enable 2FA"
 *   - enrolling (after /setup, before /confirm)  → secret + provisioning URI + code form
 *   - enabled (after /confirm)                   → "Disable 2FA"
 *
 * After /confirm, recovery codes are shown ONCE — the backend only stores
 * SHA-256 hashes, so refreshing this page never gets them back.
 */
export function TwoFactorCard() {
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);

  const [enrollment, setEnrollment] =
    useState<TwoFactorSetupResponse | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [code, setCode] = useState("");
  const [disableCode, setDisableCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  if (!user) return null;
  const isEnabled = !!user.two_factor_enabled;

  async function refreshUser() {
    try {
      const me = await meRequest();
      setUser(me);
    } catch {
      // best-effort — the next /me on bootstrap will catch up
    }
  }

  async function onStartEnrollment() {
    setBusy(true);
    setError(null);
    try {
      const resp = await twoFactorSetup();
      setEnrollment(resp);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start setup.");
    } finally {
      setBusy(false);
    }
  }

  async function onConfirmEnrollment(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const resp = await twoFactorConfirm(code);
      setRecoveryCodes(resp.recovery_codes);
      setEnrollment(null);
      setCode("");
      setInfo("2FA is on. Save your recovery codes — we can't show them again.");
      await refreshUser();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not confirm the code.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function onDisable(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await twoFactorDisable(disableCode);
      setDisableCode("");
      setInfo("2FA disabled.");
      await refreshUser();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not disable 2FA.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title="Two-factor authentication"
        subtitle={
          isEnabled
            ? "TOTP-2FA is on. You'll be asked for a 6-digit code each sign-in."
            : "Add a second factor with any TOTP authenticator app (Google Authenticator, 1Password, Authy)."
        }
      />

      {info ? (
        <div className="mt-3 rounded-lg bg-grape-soft px-3 py-2 text-sm text-grape-700">
          {info}
        </div>
      ) : null}

      {recoveryCodes ? (
        <div className="mt-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm">
          <div className="font-medium text-amber-900">Recovery codes</div>
          <p className="mt-1 text-amber-900/80">
            Each code works once if you lose your authenticator. We can't show
            them again — copy them now.
          </p>
          <ul className="mt-2 grid grid-cols-2 gap-1 font-mono text-xs text-amber-900">
            {recoveryCodes.map((rc) => (
              <li key={rc}>{rc}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {error ? (
        <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </div>
      ) : null}

      {enrollment ? (
        <div className="mt-4 flex flex-col gap-3">
          <div className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
            <div className="text-xs uppercase tracking-wider text-slate-400">
              Secret
            </div>
            <code className="mt-1 block break-all font-mono text-sm text-ink">
              {enrollment.secret}
            </code>
            <p className="mt-2 text-xs text-slate-500">
              Add this secret to your authenticator app, or scan the QR for
              this URI:
            </p>
            <code className="mt-1 block break-all font-mono text-[11px] text-slate-500">
              {enrollment.provisioning_uri}
            </code>
          </div>
          <form className="flex flex-col gap-3" onSubmit={onConfirmEnrollment} noValidate>
            <label className="flex flex-col gap-1.5 text-sm" htmlFor="totp-code">
              <span className="font-medium text-slate-text">Enter the 6-digit code</span>
              <input
                id="totp-code"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                pattern="[0-9]*"
                required
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 font-mono text-sm tracking-widest text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
              />
            </label>
            <Button type="submit" disabled={busy}>
              {busy ? "Verifying…" : "Confirm and enable"}
            </Button>
          </form>
        </div>
      ) : isEnabled ? (
        <form className="mt-4 flex flex-col gap-3" onSubmit={onDisable} noValidate>
          <label className="flex flex-col gap-1.5 text-sm" htmlFor="disable-code">
            <span className="font-medium text-slate-text">
              Confirm with a 2FA code (or recovery code) to turn it off
            </span>
            <input
              id="disable-code"
              autoComplete="one-time-code"
              value={disableCode}
              onChange={(e) => setDisableCode(e.target.value)}
              required
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 font-mono text-sm tracking-widest text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
            />
          </label>
          <Button type="submit" variant="secondary" disabled={busy}>
            {busy ? "Disabling…" : "Disable 2FA"}
          </Button>
        </form>
      ) : (
        <div className="mt-4">
          <Button onClick={onStartEnrollment} disabled={busy}>
            {busy ? "Starting…" : "Enable 2FA"}
          </Button>
        </div>
      )}
    </Card>
  );
}
