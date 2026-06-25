import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { TokenResponse, User } from "@/types/api";

type AuthState = {
  accessToken: string | null;
  user: User | null;
  hydrated: boolean;
  setSession: (response: TokenResponse) => void;
  setUser: (user: User | null) => void;
  setAccessToken: (token: string | null) => void;
  setHydrated: (value: boolean) => void;
  clear: () => void;
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      user: null,
      hydrated: false,
      setSession: (response) =>
        set({ accessToken: response.access_token, user: response.user }),
      setUser: (user) => set({ user }),
      setAccessToken: (token) => set({ accessToken: token }),
      setHydrated: (value) => set({ hydrated: value }),
      clear: () => set({ accessToken: null, user: null }),
    }),
    {
      name: "advanta.auth",
      // SECURITY: the access token is kept in MEMORY ONLY (never persisted to
      // localStorage) so an XSS payload can't exfiltrate a live bearer token.
      // We persist only the non-sensitive `user` for an instant UI hydrate; on
      // boot, bootstrapAuth() re-mints the access token from the httpOnly
      // refresh cookie. The refresh token itself is never visible to JS.
      partialize: (state) => ({ user: state.user }),
    },
  ),
);
