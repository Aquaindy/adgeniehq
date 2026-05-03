# Integrations

> **Status:** placeholder — provider adapters and OAuth flows land in Milestone 6.

## Initial providers

| Provider          | Purpose                              | Milestone |
| ----------------- | ------------------------------------ | --------- |
| Google Ads        | Campaign sync + recommendations      | M6 / M7   |
| Meta Ads          | Campaign sync + recommendations      | M6 / M7   |
| LinkedIn Ads      | Campaign sync + recommendations      | M6 / M7   |
| Google Analytics 4| Conversion + funnel analytics        | M6 / M8   |
| Search Console    | Search visibility data               | M6 / M8   |
| Stripe            | Billing                              | M11       |

## Rules ([CLAUDE.md §13](../CLAUDE.md#13-integration-requirements))

- **No simulated connections.** If an account isn't connected, the UI shows an empty state with a connect CTA.
- OAuth tokens encrypted at rest (Fernet, key from `ENCRYPTION_KEY`).
- Refresh expired tokens where supported.
- Sync attempts and errors are logged.
- Tokens never leave the backend.

## Folder layout

```
apps/api/app/integrations/
├── google_ads/
├── meta_ads/
├── linkedin_ads/
├── google_analytics/
├── google_search_console/
├── stripe/
└── email/
```
