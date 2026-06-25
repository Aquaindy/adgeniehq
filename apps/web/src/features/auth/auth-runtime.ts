import { configureApiClient } from "@/lib/api-client";
import { meRequest, refreshRequest } from "@/lib/auth";
import { useAuthStore } from "@/stores/auth-store";
import { useWorkspaceStore } from "@/stores/workspace-store";

let configured = false;

/** Wires the API client to the auth store: attaches Authorization headers and
 *  handles 401-triggered refresh-token rotation. Idempotent. */
export function ensureApiClientConfigured(): void {
  if (configured) return;
  configured = true;

  configureApiClient({
    getAccessToken: () => useAuthStore.getState().accessToken,
    onUnauthorized: async () => {
      try {
        const response = await refreshRequest();
        useAuthStore.getState().setSession(response);
        return response.access_token;
      } catch {
        useAuthStore.getState().clear();
        useWorkspaceStore.getState().setCurrentWorkspaceId(null);
        // Session is unrecoverable — bounce to login deterministically rather
        // than letting in-flight queries surface scattered 401 error states.
        // Guarded so we never loop on the login/register pages. (Bootstrap uses
        // a skipAuth refresh, so it never reaches this handler.)
        const path = window.location.pathname;
        if (!path.startsWith("/login") && !path.startsWith("/register")) {
          window.location.assign("/login?session=expired");
        }
        return null;
      }
    },
  });
}

/** On app boot, attempt to restore a session:
 *  1. If we have an access token, verify it via /auth/me.
 *  2. If that fails (or no token), try /auth/refresh once using the cookie.
 *  3. If both fail, the user is unauthenticated. */
export async function bootstrapAuth(): Promise<void> {
  ensureApiClientConfigured();
  const auth = useAuthStore.getState();

  if (auth.accessToken) {
    try {
      const user = await meRequest();
      auth.setUser(user);
      auth.setHydrated(true);
      return;
    } catch {
      // fall through to refresh
    }
  }

  try {
    const response = await refreshRequest();
    auth.setSession(response);
  } catch {
    auth.clear();
  } finally {
    auth.setHydrated(true);
  }
}
