# Security

Status snapshot at the end of M12 (production hardening). The required controls are listed in [CLAUDE.md §15](../CLAUDE.md#15-security-requirements).

## Implemented

### Authentication
- JWT access tokens (HS256, signed with `APP_SECRET_KEY`, 30-min default expiry).
- Refresh tokens delivered as **httpOnly + SameSite=Lax** cookies, scoped to `/api/v1/auth`. `Secure` flag set automatically when `APP_ENV=production`.
- Passwords hashed with **bcrypt** (rounds = library default). Long inputs SHA-256-prehashed to avoid bcrypt's 72-byte truncation.
- `/auth/refresh` rotates the refresh token on every call.
- `/auth/logout` clears the refresh cookie.

### Authorization
- Workspace isolation enforced on every authenticated route via `get_current_member`. Cross-workspace access returns `404 workspace_not_found`, never the resource.
- Five fixed roles (Owner / Admin / Marketer / Analyst / Viewer) with `require_role(min)` factory + `require_owner` + `require_superuser` dependencies.
- Recommendation approval is **risk-gated**: low → Marketer+, medium → Admin+, high → Owner only.

### Encryption at rest
- OAuth access + refresh tokens encrypted with **Fernet** before persistence. Key from `ENCRYPTION_KEY` env. Decryption errors fail closed and never leak ciphertext.
- Tokens never appear in API response bodies or log lines.

### Audit log
- Append-only `audit_logs` table records every approve / reject / edit on a recommendation, plus `integration.connected` / `connect_failed` / `disconnected` / `synced`.
- Each row captures actor type + UUID, IP (with `X-Forwarded-For` honored), user agent (truncated), and a JSON metadata blob.

### Rate limiting (M12)
- Redis-backed fixed-window counters per `(IP, endpoint group)` via `RateLimitMiddleware`.
- Tighter buckets on auth (30/min), agent runs (30/min), landing-page audits (30/min), Stripe checkout (10/min), Stripe portal (10/min), provider syncs (20/min).
- Default bucket is 600/min/IP for everything else.
- Returns `429 rate_limited` with `Retry-After` and `X-RateLimit-*` headers. Fails open if Redis is unreachable.

### Webhook integrity
- Stripe webhook validates `Stripe-Signature` via `stripe.Webhook.construct_event` against `STRIPE_WEBHOOK_SECRET`. Mismatched signatures → `400 invalid_webhook_signature`. Missing secret → `503 billing_not_configured`.

### CORS
- Origins driven from `CORS_ORIGINS` env var (JSON list). Credentials enabled. `X-Request-ID`, `X-RateLimit-Limit`, `X-RateLimit-Remaining` are exposed.

### Logging + observability
- Structured logging via **structlog** (console renderer in dev, JSON in prod).
- Per-request **request ID** middleware (`X-Request-ID` echoed and bound to every log line in scope).
- **Sentry** initialized when `SENTRY_DSN` is set (`send_default_pii=False`, sampled tracing in prod).

### OAuth state (CSRF)
- OAuth `state` parameter is a JWT signed with `APP_SECRET_KEY`, encoding `(workspace_id, user_id, provider)` with a 10-minute expiry. The callback rejects expired / mis-typed / wrong-provider state with a clear redirect to the frontend.

### Secrets handling
- All secrets live in environment variables. `.env` is gitignored. `.env.example` documents every variable without values.
- Never logged. structlog processors do not include the request body. Webhook payloads logged by event type only.

### SQL injection
- All persistence through SQLAlchemy 2.x ORM with parameterized statements. No raw f-string SQL.

### CSRF
- API authentication is JWT-bearer in `Authorization` header (no cookie auth on protected endpoints), so CSRF is not a vector for those routes.
- The refresh cookie carries `SameSite=Lax`. Refresh-rotation works inside same-site app-domain navigation; cross-site form posts can't trigger it.

### Plan-limit enforcement (M11)
- Agent runs and landing-page creation gate on the active plan; `402 plan_limit_exceeded` returned with the plan code, cap, and used count.
- `past_due` / `canceled` / `incomplete` subscriptions auto-revert to free-tier limits.

---

## Recommended pre-launch checklist

- [ ] `APP_SECRET_KEY` rotated to ≥32 random bytes (`openssl rand -hex 32`).
- [ ] `ENCRYPTION_KEY` rotated to a fresh Fernet key.
- [ ] `APP_ENV=production`, `APP_DEBUG=false`.
- [ ] `CORS_ORIGINS` restricted to production hostnames only.
- [ ] `STRIPE_WEBHOOK_SECRET` configured; `stripe listen` removed from production endpoints.
- [ ] OAuth redirect URIs match `${BACKEND_URL}/api/v1/integrations/{provider}/callback` exactly.
- [ ] Postgres + Redis are managed services with automated backups (Render handles both).
- [ ] First superuser promoted via the runbook in [`deployment.md`](deployment.md).
- [ ] `SENTRY_DSN` set; verify with a deliberate exception.
- [ ] HTTPS enforced at the platform layer (Render does this automatically).
- [ ] CSP / HSTS / `X-Content-Type-Options` headers added at the CDN or in nginx (M12.5).

## Known follow-ups

- **CSP / HSTS headers**: not yet enforced in nginx config. Add when serving from advantaai.com.
- **Stripe webhook idempotency**: events are processed live; we don't track event IDs to dedupe replays. Stripe retries the same event ID on failure, so the same `subscription.updated` arriving twice writes the same row twice (idempotent in our case because we upsert by workspace_id). Add a `processed_event_ids` table if Stripe ever introduces a non-idempotent event.
- **Per-user rate limits**: limiter is IP-only today. Per-user buckets land alongside an explicit user header check in M13.
- **Background workers**: agent runs are synchronous in-request. M13 will queue them on Celery and switch the API to return `202 Accepted`.
