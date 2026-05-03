# Responsive QA checklist

Manual smoke at three viewports before each release. The app is mobile-first; sidebar collapses below `lg` (1024px) and a sticky bottom nav takes over.

## Viewports

| Width | Device class | Notes |
|---|---|---|
| 375px | iPhone SE / smallest realistic | Worst case for hero copy + form fields |
| 768px | iPad portrait | Tablet — sidebar still hidden |
| 1280px | Laptop | Sidebar + Topbar visible |

## Per-page checklist

For each page, confirm at all three widths:

- [ ] No horizontal scrolling anywhere (use DevTools "Show rulers + element overflow").
- [ ] Tap targets ≥ 36×36 px.
- [ ] Cards stack to one column under 640 px.
- [ ] Sticky bottom mobile nav doesn't cover content (safe-area inset honored).
- [ ] Modal-like UIs (edit recommendation form, delete confirm) fit within the viewport.
- [ ] Focus states visible when tabbing (Grape outline ring).
- [ ] Long text (campaign names, URLs, agent run IDs) truncates with ellipsis or wraps cleanly.

### Pages

- [ ] **Login / Register** — auth forms, error toast.
- [ ] **Workspace Selector** — list + create form.
- [ ] **Command Center** — health cards + onboarding gate / DNA snapshot.
- [ ] **Onboarding wizard** — 5 steps; multi-line textareas; next/back.
- [ ] **Growth DNA** — score cards + 30-day plan grid.
- [ ] **Agents dashboard** — agent cards; run details with collapsible JSON.
- [ ] **Recommendations list + detail** — risk pills, approve/reject buttons, audit log.
- [ ] **Campaigns** — filter selects + summary strip.
- [ ] **SEO & GEO** — issue grid + keyword table.
- [ ] **Website** — landing page cards with score tiles.
- [ ] **Reports** — generate buttons + downloads.
- [ ] **Integrations** — provider cards.
- [ ] **Billing** — plan cards + usage bars.
- [ ] **Profile** — account details + sign-out.
- [ ] **Admin** (superuser only) — overview tiles + tables.

## Network failures

Test with DevTools "Offline":

- [ ] Cached pages render the last data they had.
- [ ] Mutations show a friendly error, not a stack trace.
- [ ] Re-enabling network triggers normal retries.

## Auth edge cases

- [ ] Hard refresh on a protected page restores the session via the refresh-cookie flow.
- [ ] Manually deleting `localStorage` then refreshing redirects to `/login`.
- [ ] Signing out clears all React Query caches (workspace data shouldn't leak to the next sign-in).
