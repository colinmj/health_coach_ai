# Commands

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Syncing data
```bash
# Hevy (workouts)
python -m sync.hevy

# Whoop (recovery, sleep, HRV)
python -m sync.whoop

# Withings (body composition)
python -m sync.withings

# Cronometer (nutrition) — export Daily Summary CSV from the app first
python -m sync.cronometer path/to/dailysummary.csv
#python -m sync.cronometer ~/Downloads/dailysummary.csv
```

## Auth (if tokens are missing/expired)
```bash
python -m sync.whoop_auth
python -m sync.withings_auth
```

## API server

```bash
# Terminal 1 — activate venv first
source .venv/bin/activate
uvicorn api.main:app --reload
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

## Agent
```bash
# Interactive prompt
python -m agent.agent

# Inline question
python -m agent.agent "how did my sleep affect my lifting this week?"
"
```

## Database
```bash
# Open psql
psql $DATABASE_URL

# Useful queries
# SELECT date, energy_kcal, protein_g, carbs_g, fat_g FROM nutrition_daily ORDER BY date DESC;
# SELECT * FROM body_measurements ORDER BY date DESC;
```
