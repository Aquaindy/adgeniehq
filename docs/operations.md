# Operations

Runbook for the running production system: backups, observability, on-call.

---

## Backups

### Postgres

- **Render**: managed Postgres has automated daily backups with point-in-time recovery. No app-level work required.
- **Self-hosted**: nightly cron of `pg_dump -Fc` to S3-compatible storage:

  ```bash
  pg_dump -Fc "$DATABASE_URL" > "adgeniehq_$(date -u +%Y%m%d).dump"
  aws s3 cp adgeniehq_$(date -u +%Y%m%d).dump s3://your-bucket/postgres/
  ```

- Test restore quarterly: `pg_restore -d adgeniehq_ai_restore -j 4 adgeniehq_*.dump`.

### Redis

Redis state is **ephemeral** — rate-limit counters only. No backup required. Losing Redis just resets rate-limit windows.

### Encrypted OAuth tokens

The `oauth_tokens` table is encrypted at rest with `ENCRYPTION_KEY`. **If the key changes, every connected account must reconnect.** Treat this key like a database password:

- Rotate via dual-write migration: temporarily decrypt with old key, re-encrypt with new key, update the env. (Build this when needed.)
- Loss of the key → users have to reconnect every provider. Billing/subscription records survive (not encrypted).

---

## Observability

### Logs

- **structlog** with JSON renderer in production. Each line carries `request_id`, `method`, `path`, plus per-event fields.
- Render: tail logs with `render logs --service adgeniehq-api --tail`.
- Self-hosted: pipe stdout to your aggregator (Loki, Datadog, etc.).
- Correlate with the `X-Request-ID` response header from a failing client request.

### Errors (Sentry)

- Set `SENTRY_DSN` to enable. The init in [`main.py`](../apps/api/main.py) sends release tags and bounded transaction sampling (`traces_sample_rate=0.1` in prod).
- `send_default_pii=False`. PII (email, IP) only attaches via explicit context bindings in code.

### Metrics

- Out-of-the-box: rate-limit hits are logged at `INFO` (`rate_limit.exceeded`). Aggregate in your log layer.
- Useful future signals (M13): per-agent latency histogram, per-provider sync error rate, Paddle webhook lag.

### Health checks

- `GET /api/v1/health` — app heartbeat, no DB.
- `GET /api/v1/health/db` — Postgres `SELECT 1`.
- `GET /api/v1/health/redis` — Redis `PING`.

Render uses `/api/v1/health` per `render.yaml`. nginx proxies `/healthz` for the SPA.

---

## On-call playbook

| Symptom | Likely cause | Action |
|---|---|---|
| `POST /agents/run` returns 402 with `plan_limit_exceeded` | Workspace at quota | Owner upgrades via Billing → Paddle checkout |
| Many `429 rate_limited` from one IP | Crawler / abusive client | Block at CDN; increase bucket if legitimate |
| `503 billing_not_configured` on Upgrade button | Paddle not configured (`PADDLE_API_KEY` / `PADDLE_WEBHOOK_SECRET` missing) | Set in Render dashboard, re-deploy |
| `503 provider_not_configured` on Connect | Missing OAuth client ID/secret | Set the provider's `GOOGLE_CLIENT_ID` / `META_APP_ID` etc. |
| Paddle webhook 400s | `PADDLE_WEBHOOK_SECRET` mismatch or replay attack | Re-copy secret from Paddle dashboard; check `Paddle-Signature` header |
| Audits hang | Real PageSpeed Insights call to `googleapis.com` rate-limited | Set `PAGESPEED_API_KEY`; lift rate ceiling |

---

## Migrations in production

Migrations are gated through `alembic upgrade head`, run as Render's `preDeployCommand`. If a migration fails, the deploy never shifts traffic.

- **Add a column with NOT NULL** → use `server_default` (see [`is_superuser` migration](../apps/api/alembic/versions/20260426_0104_is_superuser_flag.py) for the pattern).
- **Drop a column** → first deploy the code that no longer reads it, then deploy the migration that drops it.
- **Rename** → split into add-new-column → backfill → switch reads → drop old.

---

## Disaster recovery

- **Database loss**: restore latest snapshot. Reconnect any provider integrations whose tokens were rotated post-snapshot.
- **App image regression**: `render rollback` to the previous deploy ID; or `git revert` and push.
- **Encryption key loss**: see "Encrypted OAuth tokens" above. Affected users must reconnect.
