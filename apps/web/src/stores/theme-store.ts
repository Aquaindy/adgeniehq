import { create } from "zustand";

/**
 * Theme state. `mode` is the user's explicit choice and is persisted; the
 * absence of a stored value means "follow the OS" (system). `resolved` is the
 * concrete light/dark actually applied to <html>.
 *
 * First paint is handled by an inline script in index.html (no FOUC); this
 * store keeps things in sync at runtime and on OS preference changes.
 */
export type ThemeMode = "light" | "dark" | "system";
type Resolved = "light" | "dark";

const STORAGE_KEY = "adgeniehq-theme";

function systemPrefersDark(): boolean {
  return (
    typeof window !== "undefined" &&
    !!window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
}

function readStored(): ThemeMode {
  if (typeof localStorage === "undefined") return "system";
  const v = localStorage.getItem(STORAGE_KEY);
  return v === "light" || v === "dark" ? v : "system";
}

function resolve(mode: ThemeMode): Resolved {
  return mode === "system" ? (systemPrefersDark() ? "dark" : "light") : mode;
}

function apply(resolved: Resolved): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.style.colorScheme = resolved;
}

interface ThemeState {
  mode: ThemeMode;
  resolved: Resolved;
  setMode: (mode: ThemeMode) => void;
  toggle: () => void;
}

const initialMode = readStored();

export const useThemeStore = create<ThemeState>((set, get) => ({
  mode: initialMode,
  resolved: resolve(initialMode),
  setMode: (mode) => {
    if (mode === "system") {
      try {
        localStorage.removeItem(STORAGE_KEY);
      } catch {
        /* ignore */
      }
    } else {
      try {
        localStorage.setItem(STORAGE_KEY, mode);
      } catch {
        /* ignore */
      }
    }
    const resolved = resolve(mode);
    apply(resolved);
    set({ mode, resolved });
  },
  toggle: () => {
    get().setMode(get().resolved === "dark" ? "light" : "dark");
  },
}));

/**
 * Keep the app in sync with OS theme changes while the user is in `system`
 * mode. Call once at startup. Returns a cleanup function.
 */
export function initThemeWatcher(): () => void {
  if (typeof window === "undefined" || !window.matchMedia) return () => {};
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  const handler = () => {
    const { mode } = useThemeStore.getState();
    if (mode === "system") {
      const resolved = resolve("system");
      apply(resolved);
      useThemeStore.setState({ resolved });
    }
  };
  mq.addEventListener("change", handler);
  return () => mq.removeEventListener("change", handler);
}
