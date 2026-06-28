import { apiFetch } from "@/lib/api-client";
import type {
  TokenResponse,
  TwoFactorConfirmResponse,
  TwoFactorSetupResponse,
  User,
} from "@/types/api";

export function loginRequest(payload: {
  email: string;
  password: string;
  otp_code?: string;
  remember_me?: boolean;
}) {
  return apiFetch<TokenResponse>("/auth/login", {
    method: "POST",
    body: payload,
    skipAuth: true,
  });
}

export function registerRequest(payload: {
  email: string;
  password: string;
  full_name?: string;
}) {
  return apiFetch<TokenResponse>("/auth/register", {
    method: "POST",
    body: payload,
    skipAuth: true,
  });
}

let inFlightRefresh: Promise<TokenResponse> | null = null;

/**
 * Single-flight refresh. Concurrent callers (app `bootstrapAuth`, the Google
 * `/auth/google/finish` page, and the 401-retry handler) share ONE in-flight
 * request. Refresh tokens are single-use and rotated server-side, so two
 * requests carrying the same cookie make the second look like a replay →
 * `RefreshTokenReuseError`, which revokes the whole session (this is what broke
 * Google sign-in with `?error=google_refresh_token_reuse`). Deduping guarantees
 * exactly one rotation; the guard clears once the request settles.
 */
export function refreshRequest(): Promise<TokenResponse> {
  if (inFlightRefresh) return inFlightRefresh;
  inFlightRefresh = apiFetch<TokenResponse>("/auth/refresh", {
    method: "POST",
    skipAuth: true,
  }).finally(() => {
    inFlightRefresh = null;
  });
  return inFlightRefresh;
}

export function logoutRequest() {
  return apiFetch<void>("/auth/logout", {
    method: "POST",
    skipAuth: true,
  });
}

export function meRequest() {
  return apiFetch<User>("/auth/me");
}

export function passwordResetRequest(email: string) {
  return apiFetch<void>("/auth/password-reset/request", {
    method: "POST",
    body: { email },
    skipAuth: true,
  });
}

export function passwordResetConfirm(token: string, newPassword: string) {
  return apiFetch<User>("/auth/password-reset/confirm", {
    method: "POST",
    body: { token, new_password: newPassword },
    skipAuth: true,
  });
}


// ---- Email verification ----

/** Public: confirm an email from the link token. Returns the updated user. */
export function verifyEmailConfirm(token: string) {
  return apiFetch<User>("/auth/verify-email/confirm", {
    method: "POST",
    body: { token },
    skipAuth: true,
  });
}

/** Authenticated: re-send the verification email for the current user. */
export function verifyEmailResend() {
  return apiFetch<void>("/auth/verify-email/resend", {
    method: "POST",
  });
}


// ---- 2FA ----

export function twoFactorSetup() {
  return apiFetch<TwoFactorSetupResponse>("/auth/2fa/setup", {
    method: "POST",
  });
}

export function twoFactorConfirm(code: string) {
  return apiFetch<TwoFactorConfirmResponse>("/auth/2fa/confirm", {
    method: "POST",
    body: { code },
  });
}

export function twoFactorDisable(code: string) {
  return apiFetch<void>("/auth/2fa/disable", {
    method: "POST",
    body: { code },
  });
}
