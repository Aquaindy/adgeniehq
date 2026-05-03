# Deployment

This is the production runbook. AdVanta AI is shaped to run on **Render** out of the box (see [`infra/render/render.yaml`](../infra/render/render.yaml)) and on any **Docker** host via the production compose file.

---

## 1. Components

| Service | Purpose | Port | Image |
|---|---|---|---|
| `api` | FastAPI app + admin + Stripe webhook | 8000 | [`infra/docker/Dockerfile.api`](../infra/docker/Dockerfile.api) |
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

1. Push the repo to GitHub.
2. From Render: **New** → **Blueprint**, point at the repo. Render auto-discovers [`infra/render/render.yaml`](../infra/render/render.yaml).
3. Set the `sync: false` env vars in the dashboard:
   - `ENCRYPTION_KEY` — generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
   - `FRONTEND_URL`, `BACKEND_URL`, `CORS_ORIGINS` — production URLs.
   - Stripe: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID_*`.
   - Provider OAuth credentials (Google / Meta / LinkedIn) per [`integrations.md`](integrations.md).
   - Optional: `SENTRY_DSN`, `PAGESPEED_API_KEY`, SMTP (`SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM`).
4. The blueprint runs `alembic upgrade head` as a `preDeployCommand` so each release applies pending migrations before traffic shifts.

---

## 4. OAuth callbacks

Each provider's OAuth app must whitelist exactly:

```
${BACKEND_URL}/api/v1/integrations/{provider}/callback
```

Where `{provider}` is one of `google_ads`, `google_analytics`, `google_search_console`, `meta_ads`, `linkedin_ads`.

---

## 5. Stripe webhook

In the Stripe dashboard add a webhook endpoint at:

```
${BACKEND_URL}/api/v1/billing/webhook
```

Events to enable:

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`

Copy the signing secret into `STRIPE_WEBHOOK_SECRET`.

For local development:

```bash
stripe listen --forward-to localhost:8000/api/v1/billing/webhook
```

---

## 6. CORS

Set `CORS_ORIGINS` to a JSON array of your production frontend hostnames:

```env
CORS_ORIGINS=["https://app.advantaai.com","https://advantaai.com"]
```

Cookies (`advanta_refresh`) require `credentials: include` from the browser; CORS must allow credentials, which it already does in [`main.py`](../apps/api/main.py).

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

The first superuser must be created out-of-band. From a one-off shell:

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
