import type { PaddleCheckout } from "@/types/api";

/**
 * Minimal Paddle.js (Billing v2) loader + checkout opener. We load the script
 * lazily on first use so the marketing pages don't pay for it, and (re)init
 * with the workspace's client token + environment before opening the overlay.
 */

type PaddleGlobal = {
  Environment: { set: (env: string) => void };
  Initialize: (opts: { token: string }) => void;
  Checkout: {
    open: (opts: {
      items: { priceId: string; quantity: number }[];
      customer?: { email?: string };
      customData?: Record<string, string>;
      settings?: { successUrl?: string };
    }) => void;
  };
};

declare global {
  interface Window {
    Paddle?: PaddleGlobal;
  }
}

const PADDLE_JS = "https://cdn.paddle.com/paddle/v2/paddle.js";
let loader: Promise<PaddleGlobal> | null = null;
let initializedToken: string | null = null;

function loadScript(): Promise<PaddleGlobal> {
  if (window.Paddle) return Promise.resolve(window.Paddle);
  if (loader) return loader;
  loader = new Promise<PaddleGlobal>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${PADDLE_JS}"]`);
    const onReady = () => {
      if (window.Paddle) resolve(window.Paddle);
      else reject(new Error("Paddle.js loaded but window.Paddle is missing."));
    };
    if (existing) {
      existing.addEventListener("load", onReady);
      existing.addEventListener("error", () => reject(new Error("Failed to load Paddle.js")));
      if (window.Paddle) onReady();
      return;
    }
    const script = document.createElement("script");
    script.src = PADDLE_JS;
    script.async = true;
    script.onload = onReady;
    script.onerror = () => reject(new Error("Failed to load Paddle.js"));
    document.head.appendChild(script);
  });
  return loader;
}

/** Load + initialize Paddle (idempotent per token) and open the checkout overlay. */
export async function openPaddleCheckout(cfg: PaddleCheckout): Promise<void> {
  const paddle = await loadScript();
  if (initializedToken !== cfg.client_token) {
    paddle.Environment.set(cfg.environment === "sandbox" ? "sandbox" : "production");
    paddle.Initialize({ token: cfg.client_token });
    initializedToken = cfg.client_token;
  }
  paddle.Checkout.open({
    items: [{ priceId: cfg.price_id, quantity: 1 }],
    customer: cfg.customer_email ? { email: cfg.customer_email } : undefined,
    customData: cfg.custom_data,
    settings: { successUrl: `${window.location.origin}/billing?checkout=success` },
  });
}
