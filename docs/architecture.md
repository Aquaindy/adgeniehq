# Architecture

AdVanta AI is a multi-tenant SaaS built around a **Master Growth Orchestrator + AI Skill Agents** model. See [CLAUDE.md §4–§5](../CLAUDE.md) for the canonical product spec — this doc is the engineering view.

## High-level shape

```
┌──────────────┐     HTTPS      ┌────────────────────────┐
│  React (Vite)│ ─────────────▶ │  FastAPI (apps/api)    │
│  apps/web    │ ◀────────────  │  /api/v1/*             │
└──────────────┘                │                        │
                                │  Master Orchestrator   │
                                │  ├ Skill Agents        │
                                │  └ Skill Registry      │
                                ├────────────────────────┤
                                │  SQLAlchemy 2.x        │
                                │  Alembic migrations    │
                                └─┬──────────────────┬───┘
                                  │                  │
                            ┌─────▼─────┐      ┌─────▼─────┐
                            │ Postgres  │      │   Redis   │
                            │           │      │ (Celery)  │
                            └───────────┘      └───────────┘
                                  ▲                  ▲
                                  │                  │
                                  │  OAuth / API     │
                            ┌─────┴──────────────────┴─────┐
                            │ Google Ads · Meta · LinkedIn │
                            │ GA4 · Search Console · Stripe│
                            └──────────────────────────────┘
```

## Tenancy

- A **workspace** is the primary tenancy boundary. Every domain row has a `workspace_id`.
- Authorization always checks: authenticated user → membership in workspace → role permits the action.
- OAuth tokens belong to a `connected_account`, which belongs to a workspace.

## Agent model (M4+)

- The **Master Growth Orchestrator** translates user goals into a task plan.
- **Skill Agents** (Paid Ads, SEO/GEO, Website, Market Intelligence, ICP, Creative, Campaign Builder, Tracking, Budget Guardian, Reporting) each consume one or more **Skills** from the skill registry.
- Every run is logged in `agent_runs`; outputs in `skill_outputs`; downstream `recommendations` flow through `approvals` before any external mutation.

## Approval & Autopilot

- Default mode is **Approval Mode**. **Autopilot** is opt-in per workspace and bounded by max-daily-budget, max-percentage-budget-increase, min-conversion threshold, and stop-loss rules.
- All mutating external calls (campaign launch, budget changes, pauses, tracking edits) require a row in `approvals` and an entry in `audit_logs`.

## Frontend boundaries

- `components/ui/*` — primitives (`Card`, `Button`, `EmptyState`).
- `components/layout/*` — chrome (`AppShell`, `Sidebar`, `Topbar`, `MobileNav`).
- `features/*` — page-level units; they can import from `components/*` and `lib/*` but not vice-versa.
- `lib/api-client.ts` is the only place that calls `fetch`. Throws `ApiError` with structured `code`, `status`, and optional `details`.

## Build status — Milestone 1

- App boots end-to-end: FastAPI → Postgres + Redis → React.
- Health probes (`/api/v1/health`, `/health/db`, `/health/redis`) prove wiring.
- All later modules (auth, agents, integrations, billing) drop into the existing folder structure without restructuring.
