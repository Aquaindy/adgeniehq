# AdVanta AI — Backend (FastAPI)

Python 3.12+ FastAPI backend for the AdVanta AI Growth Command Center.

## Setup

```bash
# from repo root
cp .env.example .env
docker compose up -d   # Postgres + Redis

# in apps/api
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
uvicorn main:app --reload --port 8000
```

Endpoints:

- `GET /` — service info
- `GET /api/v1/health` — app heartbeat
- `GET /api/v1/health/db` — Postgres reachability
- `GET /api/v1/health/redis` — Redis reachability
- `GET /api/v1/docs` — OpenAPI Swagger UI

## Tests

```bash
pytest
```

## Migrations (Alembic)

Once models are added in `app/models/`, register them in `alembic/env.py`, then:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

## Layout

```
apps/api/
├── main.py                    FastAPI app entry
├── pyproject.toml             dependencies + tooling config
├── alembic.ini, alembic/      DB migrations
├── tests/                     pytest suite
└── app/
    ├── core/                  config, logging, exceptions
    ├── db/                    SQLAlchemy session + Base
    ├── api/v1/                versioned HTTP routers
    ├── models/                ORM models (added in M2+)
    ├── schemas/               Pydantic request/response models
    ├── services/              business logic
    ├── agents/                Master Orchestrator + Skill Agents (M4)
    ├── skills/                reusable agent capabilities (M4)
    ├── integrations/          provider adapters (M6)
    ├── workers/               Celery jobs
    ├── security/              auth, encryption, RBAC, rate limit
    └── utils/                 small helpers
```
