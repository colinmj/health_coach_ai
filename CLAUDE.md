# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Personal health analytics app that syncs data from three APIs into a local SQLite database, then uses a LangChain ReAct agent to generate cross-domain insights.

**Data sources (in order of priority):**
- **Hevy** — workouts (exercises, sets, reps, weight) ✅ implemented
- **Whoop** — recovery scores, sleep, HRV 🔜
- **Cronometer** — nutrition/macros 🔜

**Agent layer** — LangChain ReAct agent for cross-domain queries (e.g. "did my sleep affect my strength this week?") 🔜

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in API keys
```

## Running syncs

```bash
# Sync Hevy workouts
python -m sync.hevy
```

All sync scripts are idempotent — safe to re-run. They process workouts oldest-first so performance comparisons are accurate at insert time.

## Project structure

```
clients/    # Thin API clients (httpx, pagination only — no business logic)
db/         # schema.py: SQLite init and get_connection()
sync/       # One module per data source; fetches, transforms, and upserts into SQLite
analytics/  # Query functions over SQLite views; returns list[dict] for agent consumption
agent/      # (future) LangChain ReAct agent and tools
```

## Database

Single file: `health_coach.db` (auto-created on first sync, gitignored).

Schema: `workouts → exercises → sets` (cascade deletes).

Key fields on `sets`:
- `estimated_1rm` — Epley formula: `weight_kg × (1 + reps/30)`, NULL for reps=0 or missing weight
- `performance_tag` — `PR | Better | Neutral | Worse`, computed at insert time by comparing the set's 1RM to the previous session's best 1RM for the same `exercise_template_id`

## Performance tagging logic (`sync/hevy.py`)

Tags are assigned per set at sync time:
- **PR** — beats all-time best (or first time ever doing the exercise)
- **Better** — >2.5% above previous session's best
- **Neutral** — within ±2.5% of previous session's best
- **Worse** — >2.5% below previous session's best

Baselines query only already-committed rows, which is why workouts must be processed oldest-first.

## Adding a new data source

1. Add credentials to `.env.example`
2. Create `clients/<source>.py` — pagination + auth only
3. Create `sync/<source>.py` — fetch → transform → upsert pattern matching `sync/hevy.py`
4. Add new tables to `db/schema.py` `_CREATE_TABLES`
