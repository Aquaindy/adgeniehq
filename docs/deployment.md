# Deployment

This is the production runbook. AdVanta AI is shaped to run on **Render** out of the box (see [`infra/render/render.yaml`](../infra/render/render.yaml)) and on any **Docker** host via the production compose file.

---

## 1. Components

| Service | Purpose | Port | Image |
|---|---|---|---|
| `api` | FastAPI app + admin + Paddle webhook | 8000 | [`infra/docker/Dockerfile.api`](../infra/docker/Dockerfile.api) |
| `web` | React SPA (nginx) | 80 | [`infra/docker/Dockerfile.web`](../infra/docker/Dockerfile.web) |
| `postgres` | Primary database | 5432 | `postgres:16-alpine` |
| `redis` | Rate limiter + Celery broker (M13+) | 6379 | `redis:7-alpine` |

---

## 2. Quickstart — production-shaped local run

```bash
export APP_SECRET_KEY=$(openssl rand -hex 32)
export ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

docker compose -f docker-compose.prod.yml up --build -d
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
```

Visit `http://localhost:8080` (web) and `http://localhost:8000/api/v1/docs` (API).

---

## 3. Render

The blueprint provisions everything: Postgres, Redis, the API web service, the
Celery worker (with beat), and the nginx-served SPA. Domain wiring for
**getadvanta.app** is baked into [`render.yaml`](../infra/render/render.yaml) —
only secrets are entered by hand.

1. Push the repo to GitHub.
2. Render → **New** → **Blueprint**, point at the repo. It auto-discovers
   [`infra/render/render.yaml`](../infra/render/render.yaml) and provisions the
   database, Redis, the **`advanta-shared`** env-var group, and all four services.
3. Set the secret (`sync: false`) env vars **once on the `advanta-shared`
   environment group** (Render → **Env Groups → advanta-shared**). Because the
   api and worker both reference the group, a value entered here applies to both
   — no per-service copying. `APP_SECRET_KEY` is auto-generated in the group and
   shared automatically. The full list is in **§3.3** below; the must-have ones:
   - `ENCRYPTION_KEY` — `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Tokens encrypted by the api are decrypted by the worker; sharing it via the group keeps them identical.
   - `ANTHROPIC_API_KEY` — agents run on Anthropic Sonnet (provider/model are baked plain values).
   - `OPENAI_API_KEY` — required for the `gpt-5.4-mini` Growth DNA fast model.
   - **Paddle** (subscriptions): `PADDLE_API_KEY`, `PADDLE_CLIENT_TOKEN`, `PADDLE_WEBHOOK_SECRET`, `PADDLE_PRICE_ID_STARTER` / `_PRO` / `_AGENCY`.
   - **Google** (integration + login clients): see [`google-setup.md`](google-setup.md).
   - Optional: `META_*`, `LINKEDIN_*`, `SENTRY_DSN`, `PAGESPEED_API_KEY`, SMTP, inbound email.

   `FRONTEND_URL`, `BACKEND_URL`, `CORS_ORIGINS`, `GOOGLE_LOGIN_REDIRECT_URI`,
   `PADDLE_ENVIRONMENT=production`, the LLM provider/model values, and
   `VITE_API_BASE_URL` are **already set** to the getadvanta.app values in the
   blueprint — no manual entry.
4. `alembic upgrade head` runs as a `preDeployCommand` on both the API and the
   worker, so every release applies pending migrations before traffic shifts.

### 3.1 Domains & DNS (getadvanta.app)

| Host | Render service | Serves |
|---|---|---|
| `getadvanta.app` (apex) | `advanta-web` | SPA — marketing + app |
| `www.getadvanta.app` | `advanta-web` | SPA |
| `api.getadvanta.app` | `advanta-api` | FastAPI |

These are declared under each service's `domains:` in the blueprint. After the
first deploy, open each service → **Settings → Custom Domains** to read the
**exact** DNS target Render assigns, then add these records at your registrar
for `getadvanta.app`:

| Type | Name | Value |
|---|---|---|
| CNAME | `www` | the `*.onrender.com` target Render shows for `advanta-web` |
| CNAME | `api` | the `*.onrender.com` target Render shows for `advanta-api` |
| A / ALIAS | `@` (apex) | the apex target Render shows — use ALIAS/ANAME if your registrar supports it, otherwise Render's A record IP |

Render provisions and auto-renews TLS once DNS verifies. The apex can't use a
CNAME, so use your registrar's ALIAS/ANAME flattening or Render's A record. If
you make `www` (or the apex) canonical with a redirect, keep `FRONTEND_URL` and
`CORS_ORIGINS` consistent with the canonical host.

### 3.2 Uploaded images are not persistent by default

Blog cover/inline images upload to `/app/uploads` on the API container, which is
**ephemeral** on Render — they're lost on every deploy/restart. For production,
use object storage (S3 / Cloudflare R2), or uncomment the `disk:` block in the
blueprint (mind the single-instance + non-root caveats noted there). Everything
else is stored in Postgres and is unaffected.

### 3.3 Services & environment-variable checklist

The blueprint creates these resources:

| Resource | Type | Notes |
|---|---|---|
| `advanta-postgres` | Postgres DB | provides `DATABASE_URL` to api + worker |
| `advanta-redis` | Redis | internal-only; provides `REDIS_URL` |
| `advanta-shared` | Env-var group | shared secrets/config for api + worker |
| `advanta-api` | Web (FastAPI) | `api.getadvanta.app`, health `/api/v1/health/ready` |
| `advanta-worker` | Worker (Celery+beat) | single replica |
| `advanta-web` | Web (nginx SPA) | `getadvanta.app`, `www` |

**Already set by the blueprint — no action:**

| Where | Vars |
|---|---|
| `advanta-shared` | `APP_ENV`, `APP_DEBUG`, `APP_SECRET_KEY` (auto-generated), `FRONTEND_URL`, `BACKEND_URL`, `LLM_PROVIDER`, `ANTHROPIC_MODEL`, `LLM_MODEL`, `LLM_FAST_MODEL`, `PADDLE_ENVIRONMENT`, `GOOGLE_LOGIN_REDIRECT_URI` |
| `advanta-api` | `DATABASE_URL`, `REDIS_URL`, `CORS_ORIGINS`, `WORKERS_ENABLED=1` |
| `advanta-worker` | `DATABASE_URL`, `REDIS_URL` |
| `advanta-web` | `VITE_API_BASE_URL`, `VITE_APP_NAME` |

**You set these by hand on the `advanta-shared` group** (applies to api + worker):

| Group | Var | Required? |
|---|---|---|
| Core | `ENCRYPTION_KEY` | **Required** (app won't boot in prod without it) |
| LLM | `ANTHROPIC_API_KEY` | **Required** (agents) |
| LLM | `OPENAI_API_KEY` | **Required** (Growth DNA fast model) |
| Billing | `PADDLE_API_KEY`, `PADDLE_CLIENT_TOKEN`, `PADDLE_WEBHOOK_SECRET` | Required to sell subscriptions |
| Billing | `PADDLE_PRICE_ID_STARTER`, `PADDLE_PRICE_ID_PRO`, `PADDLE_PRICE_ID_AGENCY` | Required to sell subscriptions |
| Google (integration) | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | For Ads/GA4/Search Console — see [`google-setup.md`](google-setup.md) |
| Google (login) | `GOOGLE_LOGIN_CLIENT_ID`, `GOOGLE_LOGIN_CLIENT_SECRET` | For "Sign in with Google" |
| Meta | `META_APP_ID`, `META_APP_SECRET` | Optional (Meta Ads) |
| LinkedIn | `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` | Optional (LinkedIn Ads) |
| Email | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Optional (outreach/reports/reset emails) |
| Email | `INBOUND_EMAIL_DOMAIN`, `INBOUND_EMAIL_SECRET` | Optional (inbound reply parsing) |
| Observability | `SENTRY_DSN` | Optional |
| Website agent | `PAGESPEED_API_KEY` | Optional (Lighthouse/PageSpeed) |

> The `advanta-web` SPA needs **no secrets** — only the two baked `VITE_*` values.
> Redis and Postgres need no manual env vars.

---

## 4. OAuth callbacks

Each provider's OAuth app must whitelist the **backend** callback exactly
(`BACKEND_URL` = `https://api.getadvanta.app`):

```
https://api.getadvanta.app/api/v1/integrations/{provider}/callback
```

Where `{provider}` is one of `google_ads`, `google_analytics`,
`google_search_console`, `meta_ads`, `linkedin_ads`.

For Google **sign-in** (the separate login client), the registered redirect URI
is the backend callback:

```
https://api.getadvanta.app/api/v1/auth/google/callback
```

(The backend then redirects the browser to the frontend finish page
`/auth/google/finish` — that page is **not** a Google-registered redirect URI.)
Full Google walkthrough: [`google-setup.md`](google-setup.md).

---

## 5. Paddle webhook (subscriptions)

Recurring billing runs on **Paddle** (Merchant of Record). In the Paddle
dashboard → **Developer Tools → Notifications**, add a destination:

```
https://api.getadvanta.app/api/v1/billing/paddle/webhook
```

Subscribe to the subscription + transaction events:

- `subscription.activated`, `subscription.updated`, `subscription.canceled`, `subscription.past_due`
- `transaction.completed` (confirms Paddle-billed fee invoices)

Copy the destination's **secret key** into `PADDLE_WEBHOOK_SECRET`. The handler
verifies the `Paddle-Signature` HMAC over the raw body and is idempotent
(replayed/out-of-order events are no-ops). Also set `PADDLE_API_KEY`,
`PADDLE_CLIENT_TOKEN`, and the three `PADDLE_PRICE_ID_*` values. Use
`PADDLE_ENVIRONMENT=sandbox` against the Paddle sandbox while testing.

> **Stripe** subscription code remains as a dormant fallback. To use it instead,
> set `STRIPE_SECRET_KEY` + `STRIPE_PRICE_ID_*` and point a Stripe webhook at
> `/api/v1/billing/webhook` (events: `checkout.session.completed`,
> `customer.subscription.created/updated/deleted`, `invoice.payment_failed`).
> When Paddle is configured it takes precedence.

---

## 6. CORS

`CORS_ORIGINS` is a JSON array of the production frontend origins, already set in
the blueprint:

```env
CORS_ORIGINS=["https://getadvanta.app","https://www.getadvanta.app"]
```

Add/remove origins here if you change the canonical host. Cookies
(`advanta_refresh`) require `credentials: include` from the browser; CORS allows
credentials, which it already does in [`main.py`](../apps/api/main.py). Origins
must be exact (scheme + host, no trailing slash).

---

## 7. Migrations

Migrations live in [`apps/api/alembic/versions/`](../apps/api/alembic/versions/) and run with:

```bash
alembic upgrade head    # apply pending
alembic current         # show current revision
alembic downgrade -1    # roll back the most recent migration
```

In production, this is the `preDeployCommand` on Render and the manual step in the Docker quickstart.

---

## 8. Promoting a superuser

The first superuser must be created out-of-band. On Render, open the
`advanta-api` service → **Shell** and run the snippet below (drop the
`docker compose … run --rm api` prefix — you're already inside the container).
On a Docker host, run it as a one-off:

```bash
docker compose -f docker-compose.prod.yml run --rm api python -c "
from sqlalchemy import update
from app.db.session import SessionLocal
from app.models.user import User

with SessionLocal() as db:
    db.execute(update(User).where(User.email=='you@example.com').values(is_superuser=True))
    db.commit()
"
```

After that, the **Admin** page becomes visible in the sidebar for that user.
