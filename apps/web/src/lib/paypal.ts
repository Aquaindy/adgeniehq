import type { PayPalCheckout } from "@/types/api";

/**
 * PayPal subscriptions are created server-side; the server returns an approval
 * URL. Unlike Paddle's client-side overlay, checkout is a full-page redirect to
 * PayPal — the buyer approves there and PayPal redirects back to
 * /billing?checkout=success. Activation is confirmed by the webhook.
 */
export function redirectToPayPalCheckout(cfg: PayPalCheckout): void {
  window.location.assign(cfg.approval_url);
}
