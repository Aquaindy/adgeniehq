# Local development

This guide brings AdVanta AI up locally on macOS or Linux.

## Prerequisites

- Node.js ≥ 20 and pnpm ≥ 9
- Python ≥ 3.12 (`/usr/local/opt/python@3.12/bin/python3.12` on Homebrew, or use `python3.13`)
- Docker Desktop (for Postgres + Redis)

## 1. Clone and configure env

```bash
cp .env.example .env
```

Generate a Fernet key for `ENCRYPTION_KEY`:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Replace `APP_SECRET_KEY` with any sufficiently random value (e.g. `openssl rand -hex 32`).

## 2. Start datastores

```bash
docker compose up -d
docker compose ps   # postgres + redis should be healthy
```

## 3. Backend (FastAPI)

```bash
cd apps/api
python3.12 -m venv .venv     # or python3.13
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn main:app --reload --port 8000
```

Verify:

```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/health/db
curl http://localhost:8000/api/v1/health/redis
```

Open Swagger at http://localhost:8000/api/v1/docs.

## 4. Frontend (Vite + React)

In a second terminal, from the repo root:

```bash
pnpm install
pnpm dev:web        # or: cd apps/web && pnpm dev
```

Open http://localhost:5173. The Command Center page polls the three health endpoints and shows live status.

## 5. Tests

```bash
# Backend
cd apps/api && pytest

# Frontend type-check
pnpm typecheck:web
```

## Tearing down

```bash
docker compose down            # stop containers
docker compose down --volumes  # also wipe Postgres + Redis data
```

## Troubleshooting

- **`postgres` health is "Unreachable"** — Docker isn't running, or `DATABASE_URL` doesn't match `docker-compose.yml`. Default is `postgresql+psycopg://advanta:advanta@localhost:5432/advanta_ai`.
- **CORS errors in the browser** — confirm `CORS_ORIGINS` in `.env` includes `http://localhost:5173`.
- **`ModuleNotFoundError` for `app.*`** — make sure you ran `pip install -e ".[dev]"` from `apps/api/` after activating the venv.
