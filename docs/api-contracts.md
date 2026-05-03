# API contracts

All routes live under `/api/v1`. OpenAPI is served at `/api/v1/docs`.

## Conventions

- **Auth**: JWT bearer token in `Authorization: Authorization: Bearer <token>` (added in M2). Refresh tokens via `/auth/refresh`.
- **Tenancy**: most non-auth routes are scoped under `/workspaces/{workspace_id}/...`. The backend enforces membership + role.
- **Errors**: every non-2xx response is shaped as

  ```json
  { "error": { "code": "validation_error", "message": "Request validation failed.", "details": [...] } }
  ```

- **IDs**: UUIDs.
- **Timestamps**: ISO-8601, UTC.

## Currently implemented (Milestone 1)

| Method | Path                       | Purpose                          |
| ------ | -------------------------- | -------------------------------- |
| GET    | `/`                        | Service banner                   |
| GET    | `/api/v1/health`           | App heartbeat                    |
| GET    | `/api/v1/health/db`        | Postgres reachability            |
| GET    | `/api/v1/health/redis`     | Redis reachability               |

## Planned (per CLAUDE.md §12)

The full v1 surface is enumerated in [CLAUDE.md §12](../CLAUDE.md#12-required-api-routes) — auth, workspaces, onboarding, agents, recommendations, integrations (OAuth callbacks), campaigns, reports, billing, webhooks. Each lands with its corresponding milestone.
