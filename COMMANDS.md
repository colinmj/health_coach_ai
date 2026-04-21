# Commands

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Syncing data
```bash
# Hevy (workouts)
PYTHONPATH=app python -m sync.hevy

# Whoop (recovery, sleep, HRV)
PYTHONPATH=app python -m sync.whoop

# Withings (body composition)
PYTHONPATH=app python -m sync.withings

# Cronometer (nutrition) — export Daily Summary CSV from the app first
PYTHONPATH=app python -m sync.cronometer path/to/dailysummary.csv
#PYTHONPATH=app python -m sync.cronometer ~/Downloads/dailysummary.csv
```

## Auth (if tokens are missing/expired)
```bash
PYTHONPATH=app python -m sync.whoop_auth
PYTHONPATH=app python -m sync.withings_auth
```

## API server

```bash
# Terminal 1 — activate venv first
source .venv/bin/activate
PYTHONPATH=app uvicorn api.main:app --reload
# → http://localhost:8000
```

## UI (dev)

```bash
# Terminal 2
cd ui
npm run dev
# → http://localhost:5173
```

Vite proxies `/api/*` → `http://localhost:8000`, so both must be running.

## RAG / Knowledge base
```bash
# Ingest a PDF or URL into the knowledge base
PYTHONPATH=app python -m sync.documents path/to/file.pdf "Document Name"
PYTHONPATH=app python -m sync.documents https://example.com/article "Document Name"
```

## Agent
```bash
# Interactive prompt
PYTHONPATH=app python -m agent.agent

# Inline question
PYTHONPATH=app python -m agent.agent "how did my sleep affect my lifting this week?"
```

## Database
```bash
# Open psql
psql $DATABASE_URL

# Useful queries
# SELECT date, energy_kcal, protein_g, carbs_g, fat_g FROM nutrition_daily ORDER BY date DESC;
# SELECT * FROM body_measurements ORDER BY date DESC;
```
