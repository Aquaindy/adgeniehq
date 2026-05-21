# AppSumo lifetime deal

AdVanta AI supports AppSumo lifetime codes alongside Stripe subscriptions. Codes
are **uniform** (no per-code tier) and **stack**: a workspace's tier is the
number of redeemed codes, capped at 3.

| Codes redeemed | Tier | Lifetime plan | Limits |
|---|---|---|---|
| 1 | 1 | `appsumo_tier1` | Starter |
| 2 | 2 | `appsumo_tier2` | Pro |
| 3 | 3 | `appsumo_tier3` | Agency (unlimited runs/pages) |

Redemption writes the workspace's `billing_subscriptions` row with
`source=appsumo`, `status=active`, and the matching plan — no Stripe customer,
no recurring charge. Plan-limit enforcement is identical to Stripe plans. To
change the ladder, edit `appsumo_tier*` in
[`app/integrations/stripe/__init__.py`](../apps/api/app/integrations/stripe/__init__.py).

## Buyer flow

Buyers redeem at **https://getadvanta.app/appsumo/redeem** (public, outside the
dashboard). They create an account / sign in, pick a workspace, and enter the
code. Stacking additional codes bumps the tier in place.

## Listing checklist

1. **Mint codes** (superuser). Generate as many as your AppSumo unit count, then
   export and upload the CSV to AppSumo:
   ```bash
   curl -X POST https://api.getadvanta.app/api/v1/appsumo/admin/codes \
     -H "Authorization: Bearer <superuser-token>" \
     -H "Content-Type: application/json" \
     -d '{"count": 1000, "batch": "launch-2026", "prefix": "ADV"}'
   ```
   The response's `codes` array is the column to paste into AppSumo's code upload.
2. **Set the redemption URL** in the AppSumo dashboard to `https://getadvanta.app/appsumo/redeem`.
3. **Stacking** is enabled (up to 3 codes / workspace) — reflect this in the deal's tier description.

## Refunds / chargebacks

AppSumo allows a 60-day refund. Deactivate the refunded code to revoke the
grant and downgrade the workspace (drops a tier, or back to free at 0 codes):

```bash
curl -X POST https://api.getadvanta.app/api/v1/appsumo/admin/codes/deactivate \
  -H "Authorization: Bearer <superuser-token>" \
  -H "Content-Type: application/json" \
  -d '{"code": "ADV-XXXX-XXXX-XXXX"}'
```

Code stats: `GET /api/v1/appsumo/admin/codes/stats` → `{total, redeemed, refunded, unredeemed}`.

Every redemption and deactivation is written to the audit log (`appsumo.redeem`),
tagged with actor + workspace.
