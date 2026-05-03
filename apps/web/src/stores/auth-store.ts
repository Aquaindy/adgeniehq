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
      partialize: (state) => ({ accessToken: state.accessToken, user: state.user }),
    },
  ),
);
