# Health Coach AI — UI

React + TypeScript frontend for the health analytics agent.

## Stack

- **React 19 + TypeScript + Vite**
- **Tailwind v4 + shadcn/ui** — styling and components
- **Zustand** — UI state (streaming, active session)
- **TanStack Query** — server state (sessions, messages, sync status)
- **@microsoft/fetch-event-source** — POST-based SSE streaming

## Dev workflow

Requires the backend API running first (see root `COMMANDS.md`).

```bash
# From the ui/ directory
npm install       # first time only
npm run dev       # starts at http://localhost:5173
```

API requests are proxied to `http://localhost:8000` via the Vite dev server — no CORS config needed locally.

## Other commands

```bash
npm run build     # production bundle → dist/
npm run lint      # ESLint
```
