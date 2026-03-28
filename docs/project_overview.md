# Aristos — Project Overview for Claude Code

Aristos is a personal health analytics and AI coaching platform that correlates data from
strength training, recovery, nutrition, and body composition to generate insights, set goals,
and provide actionable coaching. The agent is built with LangChain + ReAct using Claude as
the LLM backbone.

---

## Tech Stack

- **Backend:** Python, FastAPI, SQLite (raw SQL, no ORM)
- **Frontend:** React + TypeScript
- **Agent:** LangChain ReAct agent, Claude (claude-sonnet-4-6)
- **Module structure:** /models, /repositories, /services, /tools, /sync

---

## Core Concept

Hevy (workout sessions) is the **anchor** of the data model. All other data sources
(recovery, nutrition, body composition) are correlated against workout sessions.

Key mechanic: Each lift session is tagged with a performance result vs the previous session
for the same exercise using the **Epley formula** for estimated 1RM:

```
estimated_1rm = weight × (1 + reps / 30)
performance_tag = 'pr' | 'better' | 'neutral' | 'worse'
```

---

## Data Sources & Tool Registry

The platform uses an **integration-agnostic tool registry** that maps domains to providers.
Each domain supports multiple providers — the agent queries data without knowing the source.

### Domains & Providers

| Domain | Providers | Method |
|---|---|---|
| Strength | Hevy, Strong, Manual (photo/CSV) | API, CSV, Vision |
| Nutrition | Cronometer, MyFitnessPal, MacroFactor | CSV upload, OAuth |
| Recovery & Sleep | Whoop, Oura, Garmin | OAuth |
| Cardio & Endurance | Strava, Garmin | OAuth |
| Body Composition | Withings, Fitbit, Manual | OAuth, Manual |
| Bloodwork | PDF/photo upload | Vision extraction |
| Genetics | Raw DNA file, Genetic report PDF | File upload, Vision |
| Progress Photos | User upload | Photo upload |
| Form Analysis | Video upload | Frame extraction + Vision |

### user_integrations table
```
user_integrations
├── id
├── user_id
├── domain          -- 'strength' | 'nutrition' | 'recovery' | 'cardio' | 'body_composition' | 'bloodwork'
├── provider        -- 'hevy' | 'cronometer' | 'whoop' | 'withings' | 'strava' etc
├── method          -- 'oauth' | 'api_key' | 'csv_upload' | 'photo' | 'manual'
├── status          -- 'active' | 'disconnected' | 'error' | 'pending'
├── credentials     -- encrypted
└── last_synced_at
```

### Nutrition provider notes
- **Cronometer** — no public API, uses CSV export pipeline. Provides 84 nutrients including
  micronutrients — richer than other providers. Capability flag: `micronutrients: true`
- **MyFitnessPal / MacroFactor** — macro-level data only
- Each provider has a capability map so the agent knows what data is available

---

## Key Database Tables

### workout_sessions
```
├── id, user_id, date, source ('hevy' | 'strong' | 'manual_photo')
├── exercise_name, sets, reps, weight
├── estimated_1rm   -- Epley: weight × (1 + reps/30)
└── raw_data        -- JSON blob of original source data
```

### lift_performance
```
├── id, user_id, date, exercise_name
├── estimated_1rm, total_volume
├── prev_session_date, prev_estimated_1rm
├── performance_delta   -- % change
└── performance_tag     -- 'pr' | 'better' | 'neutral' | 'worse'
```

### nutrition_daily
```
├── id, user_id, date, source, sync_method
├── calories, protein_g, carbs_g, fat_g, fiber_g
├── micronutrients (nullable) -- sodium_mg, vitamin_d_mcg, magnesium_mg etc
├── raw_data        -- JSON blob
└── synced_at
```

### recovery_daily
```
├── id, user_id, date, source ('whoop' | 'oura' | 'garmin')
├── recovery_score, hrv, sleep_duration_hrs
├── sleep_performance, resting_hr
└── raw_data
```

### biomarkers (bloodwork)
```
├── id, user_id, test_date
├── marker_name     -- 'testosterone' | 'ferritin' | 'vitamin_d' etc
├── value, unit
├── reference_low, reference_high   -- from lab report
├── status          -- 'low' | 'normal' | 'high' | 'optimal'
└── source          -- 'pdf_upload' | 'photo' | 'manual'
```

---

## Feature: Goals

User describes a goal in natural language. LLM parses into structured fields.

```
goals
├── id, user_id
├── raw_input        -- original natural language string, always preserved
├── goal_text        -- LLM-parsed summary
├── domains          -- JSON array e.g. ['body_composition', 'strength']
├── target_date
└── status           -- 'active' | 'achieved' | 'abandoned'
```

- **Cap: 3 active goals per user**
- Compound goals (multiple domains) appear as ONE goal to the user
- LLM parses domain array automatically from natural language
- **Simple goals** can have Actions attached directly — no Protocol required
- **Complex goals** follow the full Goal → Protocol → Actions chain

```
Goal (complex)
└── Protocol (LLM generated)
    └── Actions (max 3)

Goal (simple)
└── Actions (max 3, attached directly)
```

The LLM determines whether a goal is simple or complex at creation time.
Simple example: "Drink more water" → direct action, no protocol needed
Complex example: "Hit 8% body fat while maintaining strength" → protocol required

---

## Feature: Insights

Derived by the LLM when a correlative query produces a conclusive result.

```
insights
├── id, user_id
├── correlative_tool   -- e.g. 'nutrition_vs_performance'
├── insight            -- text describing the finding
├── effect             -- 'positive' | 'negative' | 'neutral'
├── confidence         -- 'strong' | 'moderate'
├── date_derived, session_id
├── status             -- 'active' | 'superseded' | 'dismissed'
├── superseded_by      -- FK to newer insight
└── pinned             -- boolean, max 3 pinned
```

### Derivation logic
- LLM includes optional `insight` field in response object when data is conclusive
- UI shows **"Save Insight"** button only when this field is present
- Hovering over button shows insight preview text

### Superseding logic
- New confidence >= existing → **auto-supersede** (old becomes `superseded`)
- New confidence < existing → **prompt user** to confirm

### Caps
- **Max 7 active insights per user**
- **Max 3 pinned** — pinned always appear first in system prompt
- At cap: user must dismiss before saving new one

---

## Feature: Protocols

LLM-generated strategy tied to a goal, informed by insights.

```
protocols
├── id, user_id
├── goal_id            -- required FK, must be active goal
├── insight_ids        -- JSON array of influencing insight ids (optional)
├── protocol_text      -- natural language description
├── start_date
├── review_date        -- when user should assess effectiveness
├── status             -- 'active' | 'completed' | 'abandoned'
└── outcome            -- 'effective' | 'ineffective' | 'inconclusive'
```

- **LLM generated** when a goal is created — not user defined
- Uses active insights to inform the strategy
- **Cap: 1 active protocol per goal (3 max total)**
- `review_date` prompts user to return and assess → may generate new insight

---

## Feature: Actions

Specific, measurable steps LLM generates as part of a protocol or attached directly to a goal.

```
actions
├── id, user_id
├── protocol_id        -- FK to protocol (nullable — null if attached directly to goal)
├── goal_id            -- FK to goal (set when attached directly, without a protocol)
├── action_text        -- e.g. "Eat fewer than 2400 calories per day"
├── metric             -- 'calories' | 'protein_g' | 'workout_frequency' etc
├── condition          -- 'less_than' | 'greater_than' | 'equals'
├── target_value       -- e.g. 2400
├── data_source        -- 'cronometer' | 'hevy' | 'whoop' etc
└── frequency          -- 'daily' | 'weekly'
```

- **LLM generated** — not user defined
- **Cap: 3 actions per protocol or per goal**
- Actions must only reference connected data sources
- Either `protocol_id` OR `goal_id` must be set — not both, not neither
- Examples: "Run 3x per week", "Eat >150g protein/day", "Calories <2400/day"

---

## Feature: Action Compliance

Weekly automated check of each action against real data.

```
action_compliance
├── id, user_id
├── action_id          -- FK to action
├── week_start_date    -- Monday of the week (anchor = action start_date, not rolling 7 days)
├── target_value       -- snapshot at time of check (preserved even if action changes)
├── actual_value       -- what the data showed
├── met                -- boolean
└── checked_at
```

- Runs when user visits the Protocol page
- **1 row per action per week — append only, never overwrite**
- `week_start_date` is based on action's `start_date` Monday anchor — consistent weeks
- Compliance over time is a correlatable dataset

### Protocol page display
```
Protocol: Body Recomposition

Actions this week:
✅ Run 3x per week          3/3 sessions logged
✅ Calories < 2400/day      6/7 days hit
❌ Protein > 150g/day       3/7 days hit

Overall compliance: 78%
```

---

## Cap Hierarchy

```
3 goals max
├── Complex goal → 1 protocol → 3 actions (via protocol)
└── Simple goal  → 3 actions (direct, no protocol)

Either way: max 3 actions per goal
action_compliance: 1 row per action per week, append only

7 insights max
└── 3 pinned
```

---

## System Prompt Structure

```
You are Aristos, a personal health analytics and coaching assistant with access
to the user's workout, recovery, nutrition, and body composition data.

## User Goals (max 3)
- [body_composition, strength] Hit 8% body fat by July 10
  while maintaining current strength (active)

## Active Protocols (1 per goal)
- [goal: 8% body fat] Carb cycling: higher carbs before training days,
  reduce calories on rest days (started March 1, review April 1)

## Active Actions
- Run 3x per week (weekly, hevy) — current compliance: 78%
- Calories < 2400/day (daily, cronometer)
- Protein > 150g/day (daily, cronometer)

## User Insights (max 7, pinned first)
- nutrition_vs_performance: high carb day-before → positive effect
  on lift performance (strong, March 2026) 📌
- sleep_vs_recovery: <7hrs sleep → negative HRV next day (moderate, Feb 2026)

## Instructions
- When answering correlative queries, check if the result confirms,
  contradicts, or is irrelevant to existing insights
- Flag tension between goals when relevant
- Only derive a new insight when data is conclusive
- Set confidence based on sample size and consistency of data
- When active protocols exist, assess whether recent data suggests
  the protocol is working
- Factor compliance data into reasoning when available
- Flag when a protocol review_date is approaching
- Only generate actions measurable by the user's connected data sources
- Always recommend consulting a doctor for anything related to bloodwork
```

---

## Feature: Regression Service

Linear regression sits between raw data and the correlation tools, quantifying
relationships and feeding statistically grounded confidence scores into the
insight system. This removes subjective LLM judgment from insight derivation
and replaces it with math.

### Architecture

```
Raw data (SQLite)
      ↓
Regression service (/services/regression_service.py)
      ↓
Correlation tools (/tools)
      ↓
ReAct agent → insight confidence assessment → insight derivation
```

### Simple linear regression

```python
from scipy import stats

def run_regression(x_values: list, y_values: list) -> dict:
    if len(x_values) < 5:
        return {"error": "insufficient_data", "min_required": 5}

    slope, intercept, r_value, p_value, std_err = stats.linregress(
        x_values, y_values
    )

    return {
        "slope": slope,
        "r_squared": r_value ** 2,
        "p_value": p_value,
        "intercept": intercept,
        "significant": p_value < 0.05,
        "sample_size": len(x_values),
        "direction": "positive" if slope > 0 else "negative"
    }
```

### Insight confidence mapping

Regression results map directly to insight confidence levels.
The LLM does not judge data conclusiveness — the statistics do.

```python
def assess_insight_confidence(regression_result: dict) -> str | None:
    """
    Returns 'strong', 'moderate', or None (don't derive insight).
    """
    if not regression_result.get("significant"):
        return None  # p > 0.05 — not statistically significant

    r_squared = regression_result["r_squared"]
    sample_size = regression_result["sample_size"]

    if r_squared > 0.5 and sample_size >= 20:
        return "strong"
    elif r_squared > 0.25 and sample_size >= 10:
        return "moderate"
    else:
        return None  # not conclusive enough
```

### What the agent receives

```json
{
  "x": "carbs_previous_day",
  "y": "estimated_1rm_delta",
  "slope": 0.08,
  "r_squared": 0.61,
  "p_value": 0.003,
  "significant": true,
  "direction": "positive",
  "sample_size": 24,
  "insight_confidence": "strong",
  "interpretation": "Each additional 10g carbs the day before is associated
                     with a 0.8% improvement in estimated 1RM"
}
```

### Key correlation pairs

| X variable | Y variable | Question answered |
|---|---|---|
| Carbs day before | Estimated 1RM delta | Does carb loading improve strength? |
| Sleep duration | Recovery score | How much does sleep move the needle? |
| Training volume | Next day HRV | How hard is too hard? |
| Protein intake | Performance delta | What's the optimal protein target? |
| Days since last session | Performance delta | What's the ideal rest period per lift? |
| GKI (Keto-Mojo) | Recovery score | Does ketosis help or hurt recovery? |
| Calories | Body composition delta | What surplus/deficit drives recomposition? |

### Multiple regression (future)

Once simple regression is stable, multiple regression identifies which
combination of variables best predicts performance — the most powerful
personalisation layer:

```python
from sklearn.linear_model import LinearRegression

# Predict performance from multiple inputs simultaneously
X = [[sleep, protein, recovery_score], ...]
y = [performance_delta, ...]

model = LinearRegression().fit(X, y)
# model.coef_ shows relative importance of each variable per user
```

This enables insights like:
> "For you specifically, sleep quality has 2x the impact on next-day
> performance compared to protein intake."

### Critical language rule

Regression shows correlation, not causation. The agent system prompt must
enforce this framing at all times:

```
ALWAYS use "associated with" not "causes".
NEVER imply causation from correlative data.
Example: "Higher carb intake the day before is associated with better
performance" NOT "Carbs improve your performance".
```

### Dependencies
```
scipy    -- simple linear regression (stats.linregress)
sklearn  -- multiple regression (LinearRegression)
numpy    -- array operations
```

---

## Recommended RAG Sources

These are the planned knowledge base documents for V2 RAG integration.
Organised by domain — ingest all before launching V2.

### Strength Training & Programming
| Title | Author | Format | Covers |
|---|---|---|---|
| Scientific Principles of Strength Training | Dr. Mike Israetel et al. (RP) | eBook | Periodization, volume, intensity, fatigue, recovery |

### Nutrition
| Title | Author | Format | Covers |
|---|---|---|---|
| The Renaissance Diet 2.0 | Dr. Mike Israetel et al. (RP) | eBook / PDF | Calories, macros, nutrient timing, supplements, diet phases |

### Bloodwork & Biomarker Interpretation
| Title | Author | Format | Covers |
|---|---|---|---|
| Bloodwork: On the Edge of Transformation | Dan Garner | Book (Momentous) | Performance bloodwork interpretation, optimal vs normal ranges, athlete-specific biomarker analysis |

### Testosterone Optimization
| Title | Author | Format | Covers |
|---|---|---|---|
| Bloodwork: On the Edge of Transformation | Dan Garner | Book (Momentous) | Testosterone, SHBG, free vs total T, cortisol/T relationship |
| The Testosterone Optimization Therapy Bible | Jay Campbell | Book (Amazon) | Full T optimization framework, natural strategies, TRT overview |
| Testosterone-Optimizing Strategies in Athletes | Lazarev, Pujalte et al. (Mayo Clinic) | Free PDF (PubMed, 2026) | Peer-reviewed, athlete-specific strategies — sleep, resistance training, nutrition, substances to avoid |

### Notes on RAG source selection
- Prioritise athlete-specific and performance-focused sources over general health content
- Dan Garner's bloodwork book is the single most important source — covers the gap between
  "normal" lab ranges and "optimal for performance" which is Aristos's core value proposition
- The Mayo Clinic 2026 review is free, peer-reviewed, and very recent — high credibility for
  the agent to cite when making testosterone-related recommendations
- Add sources incrementally — get quality of retrieval right on a small corpus before scaling
- All sources should be legally obtained PDFs or ebooks owned by the developer

### Future sources to consider (V3+)
- HRV and recovery science literature
- Sleep optimization research (Matthew Walker, etc.)
- Nutrition timing and protein synthesis meta-analyses
- Micronutrient deficiency and athletic performance studies
- Body composition and recomposition research

---

## Feature: Sports Science RAG

Vector database of sports science literature to ground agent reasoning in research.

### Pipeline
```
PDF/Article → parse → chunk (500 words, 50 overlap) → embed → ChromaDB
```

### Stack
- **Vector DB:** ChromaDB (local, open source)
- **Embeddings:** Voyage-3 via Anthropic
- **Integration:** LangChain tool in tool registry

### Tool definition
```python
@tool
def query_sports_science(question: str) -> str:
    """
    Query the sports science knowledge base for evidence-based information.
    Use when: user asks WHY something is happening physiologically,
    a correlation needs scientific context, or a general sports science
    question is asked. Do NOT use for personal data queries.
    """
```

- Agent decides when to call it — not invoked on every query
- Enables source citations in responses
- Suggested initial sources: strength training texts, protein synthesis
  meta-analyses, sleep/HRV research

---

## Feature: Bloodwork Upload

User uploads lab results via PDF or photo. Claude vision extracts biomarkers.

```
biomarkers
├── id, user_id, test_date
├── marker_name     -- 'testosterone' | 'ferritin' | 'vitamin_d' etc
├── value, unit
├── reference_low, reference_high   -- from lab report
├── status          -- 'low' | 'normal' | 'high' | 'optimal'
└── source          -- 'pdf_upload' | 'photo' | 'manual'
```

- Always recommend consulting a doctor for clinical interpretation
- Lab reference ranges stored but optimal performance ranges may differ
- Longitudinal tracking over multiple tests enables trend analysis
- Sensitive data — encrypt at rest

---

## Feature: Genetic Data

Three input types accepted — all optional, all provider-agnostic.

### Input types

**Type 1 — Raw DNA file (.txt)**
Full unprocessed genotype data downloaded from any testing provider (23andMe,
AncestryDNA, MyHeritage etc). Parse out only fitness-relevant SNPs.

**Type 2 — Genetic report PDF**
Interpreted health/traits report. Claude vision extracts findings.
Less raw data but immediately actionable.

**Type 3 — Bloodwork PDF** *(separate feature, same upload flow)*

### Schema
```
user_genetics
├── id, user_id
├── variant         -- 'ACTN3_R577X' | 'PPARGC1A' | 'FTO' | 'MTHFR' etc
├── genotype        -- 'RR' | 'RX' | 'XX' etc
├── trait           -- 'power_vs_endurance' | 'recovery_rate' | 'injury_risk' etc
├── source          -- 'raw_file' | 'report_pdf' | 'manual'
└── notes
```

### Key fitness-relevant SNPs to extract

| SNP | Affects |
|---|---|
| ACTN3 R577X | Power vs endurance muscle fiber ratio |
| PPARGC1A | Aerobic capacity and endurance |
| FTO | Fat mass and obesity association |
| MTHFR | B12/folate metabolism, recovery |
| VDR | Vitamin D receptor, bone health |
| COL5A1 | Connective tissue, injury risk |
| ACE I/D | Cardiovascular endurance |

### Notes
- 23andMe filed for bankruptcy in March 2025 — API deprecated, not viable
- Raw DNA file upload is provider-agnostic and more powerful than any API
- As sports science evolves, same raw file can be re-analysed against new findings
- Genetic data is highly sensitive — encrypt at rest, explicit consent required
- Agent should always frame genetic insights as predispositions, not deterministic

---

## Feature: Video Form Analysis

User uploads a short lifting video. Aristos extracts frames and analyses form
using Claude vision against exercise-specific form standards.

### Pipeline
```
User uploads video (max 30 seconds)
      ↓
Frame extraction via OpenCV (every 0.5s or ~10-15 key frames)
      ↓
Frames sent as base64 image sequence to Claude vision
      ↓
Analysed against exercise form standards prompt
      ↓
Structured critique returned to UI
```

### Form standards approach
Exercise-specific form standards encoded as structured prompts (not RAG).
More reliable than video RAG for current tooling:

```python
FORM_STANDARDS = {
    "barbell_squat": """
    Evaluate against these standards:
    - Depth: hip crease below knee at bottom
    - Knee tracking: over mid-foot, not caving inward
    - Back angle: neutral spine, no excessive forward lean
    - Bar position: stable, not rolling forward
    Common faults: butt wink, knee cave, forward lean, shallow depth
    """,
    "deadlift": "...",
    "bench_press": "..."
}
```

### Output structure
```
📹 Barbell Back Squat Analysis

✅ Depth: Good — hip crease below parallel
✅ Bar position: Stable throughout
⚠️  Knee tracking: Slight valgus on left knee at bottom
❌ Lower back: Mild rounding detected at depth

Key cues:
→ "Push your knees out in the direction of your toes"
→ "Brace your core harder before initiating the descent"

Safety note: Lower back rounding worth monitoring —
consider reducing load until addressed.
```

### Aristos advantage
Agent has context no generic form checker has — correlates form quality
with recovery scores, sleep, and fatigue data:

> *"Your last 3 flagged sessions all followed nights under 6 hours sleep.
> Fatigue may be affecting your stability under load."*

### Schema
```
form_analyses
├── id, user_id
├── exercise_name
├── video_date
├── frame_count
├── overall_rating    -- 'good' | 'needs_work' | 'safety_concern'
├── findings          -- JSON array of findings with severity
├── cues              -- JSON array of coaching cues
└── recovery_score_day_of  -- snapshot for correlation
```

### Notes
- Phase 2/3 feature — build after core coaching loop
- Requires video storage infrastructure (S3 or equivalent)
- Multiple vision API calls per video — latency and cost consideration
- True video RAG (comparing against reference videos) is future tooling

---

## Feature: Progress Photos

Periodic body composition photos for visual progress tracking over time.

### Schema
```
progress_photos
├── id, user_id
├── photo_date
├── angle             -- 'front' | 'side' | 'back'
├── photo_url         -- encrypted storage
├── notes             -- user's own notes
└── comparison_ids    -- JSON array of previous photo ids to compare against
```

### How it works
- User uploads front/side/back photos periodically (e.g. monthly)
- Agent compares against previous photos using Claude vision
- Correlates visible changes with body composition data and protocol compliance

### Example agent output
> *"Comparing your front photos from January to March, there's visible
> reduction in midsection — consistent with your body composition data
> showing 2.1% body fat reduction. Your protocol appears to be working."*

### Sensitivity guidelines — important
- Always encouraging and constructive, never critical
- Focus on performance and health markers, not aesthetics
- Frame as progress tracking, not body evaluation
- Never make negative comments about body shape or appearance
- Highly sensitive data — encrypt at rest, never used for training

---

## Onboarding Flow

Sequential screens, one domain per screen. Skip is always available.

```
1.  Welcome
2.  Strength Training    -- Hevy | Strong | Manual (photo) | Skip
3.  Nutrition            -- Cronometer | MyFitnessPal | MacroFactor | Skip
4.  Recovery & Sleep     -- Whoop | Oura | Garmin | Skip
5.  Cardio & Endurance   -- Strava | Garmin | Skip
6.  Body Composition     -- Withings | Fitbit | Manual | Skip
7.  Bloodwork            -- Upload PDF/photo | Skip for now
8.  Genetic Data         -- Upload raw DNA file | Upload report PDF | Skip
9.  Progress Photos      -- Take/upload first photo set | Skip for now
10. You're all set! 🎉
```

### Provider card types
- **OAuth** — tap starts auth flow immediately
- **API key** — tap expands inline input + test connection button + link to find key
- **CSV upload** — tap opens file picker
- **Photo** — tap opens camera/file for manual logs

### TypeScript provider config pattern
```typescript
type Domain = 'strength' | 'nutrition' | 'recovery' | 'cardio' | 'body_composition' | 'bloodwork'
type ConnectionMethod = 'oauth' | 'api_key' | 'csv_upload' | 'photo' | 'manual'

interface Provider {
  id: string
  name: string
  domain: Domain
  method: ConnectionMethod
  logo: string
  description: string
  setupUrl?: string   // for api_key providers
}
```

Onboarding screens are **data-driven** from the provider config array —
adding a new provider requires only a new array entry, no UI changes.

---

## Product Roadmap

---

### V1 — Core Agent (Current)

**Goal:** Solid foundation — working data pipeline, correlation tools, and agent

**Integrations (4):**
- Hevy or Strong (strength, API key / CSV) — not locked to Hevy
- Manual workout upload (photo of handwritten log, CSV) — always available as fallback
- Whoop (recovery/sleep, OAuth)
- Cronometer (nutrition, CSV upload)
- Withings (body composition, OAuth)

**Features:**
- 29 correlation tools across strength, recovery, nutrition, and body composition domains
- ReAct agent for cross-domain analytics queries
- Lift performance tagging (PR / Better / Neutral / Worse via Epley formula)
- Basic UI for data exploration and agent chat

**Agent capability:** Analytics and insight queries only — no coaching layer yet

---

### V2 — RAG + Bloodwork

**Goal:** Ground the agent in research literature and add clinical context

**New features:**
- Sports science RAG knowledge base (ChromaDB + Voyage-3 embeddings)
  - Strength training literature
  - Nutrition science
  - Bloodwork interpretation documents
  - Recovery and HRV research
- Bloodwork upload (PDF or photo → Claude vision extraction)
- Agent can now cite research when explaining correlations
- Agent can contextualise bloodwork against training and nutrition data

**Agent capability:** Evidence-based reasoning — *"your data shows X, and research suggests Y"*

---

### V3 — Coaching Layer

**Goal:** Evolve from analytics tool to active coach

**New features:**
- Goals (natural language → LLM parsed, max 3 active)
- Protocols (LLM generated per goal, informed by insights, max 1 per goal)
- Actions (LLM generated, measurable via data, max 3 per protocol)
- Action compliance tracking (weekly, Monday-anchored, append only)
- Write routines to Hevy API (AI-generated workout pushed directly to Hevy)
- Progress photo analysis (front/side/back, Claude vision comparison over time)
- Video form analysis (frame extraction → Claude vision → structured critique)
  - Form standards encoded per exercise as reference prompts
  - Correlates form quality with recovery and fatigue data
- Genetic data upload
  - Raw DNA file (.txt) from any provider — parse fitness-relevant SNPs
  - Genetic report PDF — Claude vision extraction
  - Key SNPs: ACTN3, PPARGC1A, FTO, MTHFR, VDR, COL5A1, ACE I/D

**Agent capability:** Full coaching loop — goal → protocol → actions → compliance → insights → refined protocol. Coaching informed by genetics and bloodwork.

---

### V4 — Expanded Client

**Goal:** Broaden the user base with more integrations and richer personal profile

**New integrations:**
- Strong (strength alternative to Hevy)
- Strava (cardio/endurance domain)
- Garmin (recovery + cardio)
- Oura (recovery alternative to Whoop)
- MyFitnessPal (nutrition alternative)
- Others TBD

**New features:**
- Manual workout builder
  - Photo upload of handwritten training log (Claude vision extraction)
  - Natural language program description → structured routine
- Full sequential onboarding flow (one domain per screen, skip available)
- Expanded user profile
  - Body measurements
  - Physical limitations / injury history
  - Genetic predispositions

**Agent capability:** Deeply personalised coaching across a broad range of data sources and user profiles

---

### Capability progression summary

```
V1  Analytics     "Here's what your data shows"
V2  Evidence      "Here's what your data means, backed by research and bloodwork"
V3  Coaching      "Here's what you should do, informed by genetics and your unique profile"
V4  Scale         "Here's your personalised plan, whatever tools and apps you use"
```

---

## Frontend Stack

- **React + TypeScript**
- **State management:** Zustand
- **Styling:** Tailwind CSS
- **Charts:** Recharts
- **API layer:** FastAPI (Python backend)

---

## Naming

The product is named **Aristos** — from the Greek meaning "the best, the elite."
Domain target: aristos.ai
