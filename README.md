# Health Coach AI

Personal health analytics app that syncs data from wearables and fitness APIs into PostgreSQL, then uses a LangChain ReAct agent to answer cross-domain questions about your health.

> "Did my sleep affect my strength this week?" "How does my protein intake correlate with recovery?"

## Monorepo structure

```
health_coach_ai/
├── api/            # FastAPI server (HTTP + SSE streaming)
├── agent/          # LangChain ReAct agent + 30+ tools
├── analytics/      # Query functions over Postgres (return list[dict])
├── clients/        # Thin API clients — auth + pagination only
├── sync/           # Fetch → transform → upsert per data source
├── db/             # Schema, migrations, connection helper
├── tests/          # pytest suite
└── ui/             # React + TypeScript frontend (Vite)
```

## Data sources

| Source | Domain | Status |
|---|---|---|
| Hevy | Workouts, sets, 1RM, PRs | ✅ |
| Whoop | Recovery, HRV, sleep, strain | ✅ |
| Withings | Weight, body composition | ✅ |
| Cronometer | Nutrition, macros, micros | ✅ |

## Setup

### Prerequisites
- Python 3.11+
- Node 18+
- Docker (for PostgreSQL)
- API keys for each data source (see `.env.example`)

### First time

```bash
# 1. Start the database
docker compose up -d db

# 2. Python backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in API keys and DATABASE_URL

# 3. Init database schema
python -c "from db.schema import init_db; init_db()"

# 4. Frontend
cd ui && npm install
```

## Running locally

**Terminal 1 — API server**
```bash
source .venv/bin/activate
uvicorn api.main:app --reload
# → http://localhost:8000
```

**Terminal 2 — UI**
```bash
cd ui
npm run dev
# → http://localhost:5173
```

Vite proxies `/api/*` → `http://localhost:8000`. Open `http://localhost:5173` in your browser.

## Syncing data

```bash
python -m sync.hevy
python -m sync.whoop
python -m sync.withings
python -m sync.cronometer path/to/dailysummary.csv
```

See `COMMANDS.md` for the full command reference.

## Tech stack

| Layer | Technology |
|---|---|
| API | FastAPI + uvicorn |
| Agent | LangChain ReAct |
| Database | PostgreSQL (psycopg3) |
| UI | React 19 + TypeScript + Vite |
| Styling | Tailwind v4 + shadcn/ui |
| State | Zustand + TanStack Query |
| Streaming | Server-Sent Events (SSE) |
