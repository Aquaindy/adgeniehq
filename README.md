# AdVanta AI

**Turn ad chaos into intelligent growth.**

AdVanta AI is an AI Growth Command Center where businesses connect real ad accounts, analytics, websites, and search data. Specialized AI Skill Agents — coordinated by a Master Growth Orchestrator — analyze performance, surface wasted spend, propose optimizations, strengthen SEO/GEO visibility, and improve landing-page conversion across Google, Meta, LinkedIn, and future ad networks.

This is a production-build SaaS, not a prototype. See [CLAUDE.md](CLAUDE.md) for the full product spec, architecture, and milestone plan.

---

## Repo layout

```
advanta-ai/
├── apps/
│   ├── api/          FastAPI backend (Python 3.12+)
│   └── web/          React + Vite + Tailwind frontend
├── packages/
│   ├── shared-types/ Cross-package TS types
│   ├── ui/           Shared UI primitives (placeholder)
│   └── config/       Shared config (placeholder)
├── docs/             Architecture, API, agents, integrations, security, deployment
├── infra/            Render / Docker / nginx deployment artifacts
├── docker-compose.yml  Local Postgres + Redis
└── CLAUDE.md         Master product + build spec
```

---

## Local development

See [docs/local-development.md](docs/local-development.md) for the full guide.

### 1. Prerequisites

- Node.js ≥ 20
- pnpm ≥ 9
- Python ≥ 3.12
- Docker (for Postgres + Redis)

### 2. Bootstrap

```bash
# Copy env template
cp .env.example .env

# Start Postgres + Redis
docker compose up -d

# Backend
cd apps/api
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn main:app --reload --port 8000

# Frontend (in another terminal, from repo root)
pnpm install
pnpm dev:web
```

The frontend runs at http://localhost:5173 and proxies API calls to http://localhost:8000.

Health checks:

- http://localhost:8000/api/v1/health
- http://localhost:8000/api/v1/health/db
- http://localhost:8000/api/v1/health/redis

---

## Build status

**Milestones 1–12 — complete.** AdVanta AI ships a production-ready foundation:

| Milestone | Highlights |
|---|---|
| M1 — Foundation | Monorepo, FastAPI + React skeletons, Grape Jelly theme, health checks |
| M2 — Auth & Workspaces | JWT + refresh cookie, 5-role RBAC, workspace switcher |
| M3 — Onboarding & Growth DNA | 5-step wizard, deterministic readiness engine |
| M4 — Agents & Skills | `BaseAgent` + 5 real agents, skill registry, run history |
| M5 — Recommendations & Approvals | Risk-gated approve / reject / edit, audit log with IP + UA |
| M6 — Integrations | Fernet-encrypted OAuth tokens, 5 provider shells |
| M7 — Paid Ads MVP | Real campaign sync (Google Ads / Meta / LinkedIn), Budget Guardian |
| M8 — SEO & GEO MVP | Sitemap + crawler, GSC sync, opportunity scoring |
| M9 — Website MVP | Landing-page audit with real PageSpeed Insights |
| M10 — Reports | PDF + CSV with reportlab, email-report foundation |
| M11 — Billing | Stripe Checkout + Portal + signature-verified webhook, plan limits |
| M12 — Production Hardening | Rate limiting, request IDs, Sentry hook, admin dashboard, Docker + Render |

Backend: **163 tests passing** · Frontend: typecheck + production build clean.

See [CLAUDE.md §19](CLAUDE.md#19-milestone-based-development-plan) for the milestone spec, [docs/deployment.md](docs/deployment.md) for the production runbook, and [docs/security.md](docs/security.md) for the security posture.
