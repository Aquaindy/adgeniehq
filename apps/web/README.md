# AdGenieHQ — Frontend (Vite + React)

React 18 + TypeScript + Tailwind frontend for the AdGenieHQ Growth Command Center.

## Setup

```bash
# from repo root
pnpm install
cp .env.example .env

# from apps/web (or via root scripts)
pnpm dev
```

Then open http://localhost:5173.

## Scripts

| Command            | Purpose                              |
| ------------------ | ------------------------------------ |
| `pnpm dev`         | Vite dev server with HMR             |
| `pnpm build`       | Type-check + production build        |
| `pnpm preview`     | Serve the production build locally   |
| `pnpm typecheck`   | TypeScript only, no emit             |

The frontend reads `VITE_API_BASE_URL` (defaults to `http://localhost:8000/api/v1`).

## Layout

```
apps/web/src/
├── App.tsx, main.tsx
├── components/
│   ├── layout/    AppShell, Sidebar, Topbar, MobileNav
│   └── ui/        Card, Button, EmptyState
├── features/
│   ├── dashboard/ Command Center page (live API health)
│   └── PlaceholderPage.tsx — used for routes building in later milestones
├── lib/           api-client, constants, utils (cn helper)
└── styles/        globals.css with the Grape Jelly brand layer
```

## Brand

- Primary: Grape Jelly `#3E2F84` (`tailwind: grape-700` / `text-grape`)
- Gradient: `bg-grape-gradient`
- Soft brand surface: `bg-grape-soft`
