
import asyncio
import datetime
import json as _json
import logging
from typing import AsyncGenerator
from dotenv import load_dotenv

import anthropic

logger = logging.getLogger(__name__)

from anthropic._exceptions import OverloadedError as AnthropicOverloadedError
from langchain_anthropic import ChatAnthropic

from langchain_core.messages import HumanMessage, AIMessageChunk, SystemMessage
from langgraph.prebuilt import create_react_agent

from agent.tools import build_tools
from agent.tools._config import build_source_map
from agent import sessions
import analytics.goals as goals_analytics
import analytics.trends as trends_analytics
from api.tool_confirmation import ConfirmationRequired, get_pending_confirmation, set_confirmed
from db.schema import get_request_user_id, set_current_user_id, get_connection

load_dotenv()


def _fetch_compliance_map(user_id: int) -> dict:
    """Return latest compliance row per action_id for the given user."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT ON (action_id)
                action_id, actual_value, met, week_start_date
            FROM action_compliance
            WHERE user_id = %s
            ORDER BY action_id, week_start_date DESC
            """,
            (user_id,),
        ).fetchall()
    return {r["action_id"]: r for r in rows}


def _format_goals_lines(goals: list, compliance_map: dict, soon: datetime.date) -> list[str]:
    """Render goals and their actions into a list of text lines."""
    lines: list[str] = []
    if not goals:
        lines.append("No active goals.\n")
        return lines

    for g in goals:
        goal_label = g.get("title") or g["goal_text"]
        lines.append(f"### Goal ({goal_label}, status={g['status']})")
        if g.get("target_date"):
            lines.append(f"  Target date: {g['target_date']}")
        for a in g.get("actions", []):
            comp = compliance_map.get(a["id"])
            if comp:
                actual = comp["actual_value"] if comp["actual_value"] is not None else "no data"
                met_str = {True: "✅", False: "❌", None: "—"}.get(comp["met"], "—")
                lines.append(
                    f"  Action: {a['action_text']} "
                    f"[{met_str} actual={actual}, target={a['target_value']}]"
                )
            else:
                lines.append(f"  Action: {a['action_text']} [no compliance data yet]")
    return lines
  

def _fetch_user_profile(user_id: int) -> dict:
    """Return user profile fields used in system prompt construction."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT name, units, date_of_birth, sex, height_cm, training_iq, workout_source FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
    return dict(row) if row else {}


def build_context_block(user_id: int, current_session_id: int | None = None, source_map: dict | None = None) -> str:
    """Assemble the structured context block injected into the agent system prompt."""
    today = datetime.date.today()
    soon = today + datetime.timedelta(days=7)

    profile = _fetch_user_profile(user_id)
    units = profile.get("units", "metric")
    goals = goals_analytics.get_goals_with_actions(user_id)
    pinned_insights = [i for i in goals_analytics.get_active_insights(user_id) if i.get("pinned")]
    compliance_map = _fetch_compliance_map(user_id)
    if source_map is None:
        source_map = build_source_map(user_id)

    _DOMAIN_LABELS = {
        "strength":         "Strength training",
        "recovery":         "Recovery & sleep",
        "body_composition": "Body composition",
        "nutrition":        "Nutrition",
        "bloodwork":        "Bloodwork",
    }
    integration_lines = []
    for domain, label in _DOMAIN_LABELS.items():
        if domain in source_map:
            integration_lines.append(f"- {label}: {source_map[domain]}")
        else:
            integration_lines.append(f"- {label}: not connected")

    profile_lines = [f"- Units: {units}"]
    if profile.get("name"):
        profile_lines.insert(0, f"- Name: {profile['name']}")
    if profile.get("date_of_birth"):
        dob = datetime.date.fromisoformat(profile["date_of_birth"])
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        profile_lines.append(f"- Age: {age}")
    if profile.get("sex"):
        profile_lines.append(f"- Sex: {profile['sex']}")
    if profile.get("height_cm"):
        profile_lines.append(f"- Height: {profile['height_cm']} cm")
    profile_lines.append(f"- Training IQ: {profile.get('training_iq') or 'not set'}")
    workout_source = profile.get("workout_source") or "hevy"
    profile_lines.append(f"- Workout logging: {workout_source}")

    lines = [
        "## User profile\n" + "\n".join(profile_lines) + "\n",
        "## Connected integrations\n" + "\n".join(integration_lines) + "\n",
    ]
    lines.append("## Current goals and actions\n")
    lines.extend(_format_goals_lines(goals, compliance_map, soon))

    if pinned_insights:
        lines.append("\n## Pinned insights")
        for i in pinned_insights:
            lines.append(f"- [{i['correlative_tool']}] {i['insight']} (effect={i['effect']}, confidence={i['confidence']})")

    trends_block = trends_analytics.build_trends_block(user_id)
    if trends_block:
        lines.append(f"\n{trends_block}")

    recent_context = sessions.get_recent_context(user_id, exclude_session_id=current_session_id)
    if recent_context:
        lines.append(
            "\n> ⚠️ Prior session context (below) is for conversational continuity only. "
            "Exercise names, weights, reps, and set counts in it may be incorrect — "
            "they were generated by this model and must NOT be cited as data. "
            "Always re-fetch specific workout data via tools.\n"
        )
        lines.append(f"\n{recent_context}")

    return "\n".join(lines)


async def _generate_followups(human_text: str, ai_text: str) -> list[str]:
    """Make a single non-streaming LLM call to generate 2-3 follow-up questions."""
    try:
        llm = ChatAnthropic(
            model_name="claude-haiku-4-5-20251001", temperature=0, timeout=15, max_tokens=200
        ).with_retry(
            retry_if_exception_type=(AnthropicOverloadedError,),
            stop_after_attempt=3,
            wait_exponential_jitter=True,
        )
        response = await llm.ainvoke([
            SystemMessage(content=(
                "Given this health coaching exchange, choose the right follow-up chips to show:\n\n"
                "1. If the coach's reply ends with a yes/no question — e.g. 'Would you like me to...', "
                "'Shall I...', 'Do you want to...', 'Should I...', 'Are you...', 'Can I...' — "
                'output EXACTLY: ["Yes please!", "No thanks!"]\n\n'
                "2. Otherwise, suggest 2-3 short, specific follow-up questions the user might want to ask. "
                "Questions MUST be from the user's perspective using 'I' or 'my' — never 'you' or 'your'. "
                "Output ONLY a JSON array of strings, nothing else."
            )),
            HumanMessage(content=f"User asked: {human_text}\n\nCoach replied: {ai_text[:400]}"),
        ])
        if isinstance(response.content, str):
            raw = response.content
        elif isinstance(response.content, list):
            raw = " ".join(
                b.get("text", "") for b in response.content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        else:
            raw = ""
        start = raw.find('[')
        end = raw.rfind(']')
        if start == -1 or end == -1 or end <= start:
            return []
        questions = _json.loads(raw[start:end + 1])
        if isinstance(questions, list):
            return [q for q in questions if isinstance(q, str)][:3]
        return []
    except Exception:
        return []


SYSTEM_PROMPT = """\
You are Adonis, akaCoach Donnie — the AI coach behind Adonis AI.

You are not an app. You are a coach. You have access to the user's real data across every domain \
— training, recovery, sleep, nutrition, and body composition — and your job is to connect all of \
it, not just one piece at a time.

Today's date is {today}.

{context}

---

## Who you are

Direct, warm, and data-driven. You have a dry wit. You notice things. You remember everything. \
You don't sugarcoat, but you're never harsh — you're honest in the way a coach who genuinely \
wants someone to succeed is honest.

You use the user's name. You reference what you know about them. You connect dots across \
domains without being asked. You feel like a person, not a chatbot.

You are not a hype machine — you don't celebrate mediocrity. You are not a cold analytics \
dashboard — you give a damn. Every message should feel like it was written for this specific \
person, because it was.

You are kind and supportive, but not too easy to please. When you give positive feedback \
it MEANS something because your compliments don't come cheap

---

## Your voice

- **Use the user's name** naturally — not every message, but as a coach would with a regular client.
- **Reference recent data without announcing it** — weave it in ("your sleep was off and your lifts \
  showed it"), don't declare "I can see from your data that...".
- **Connect domains without being asked** — if sleep is affecting performance, say so. If nutrition \
  is affecting energy, flag it.
- **First person. Past tense for observations, present tense for recommendations.**
- **Concise** — a real coach doesn't write essays. Lead with the point.
- **Direct about problems and solutions** — if something is wrong, say what it is and what to do about it.

---

## Connected integrations
The user's connected integrations are listed in the context block. \
Only reference or ask about data from connected sources. \
If a domain shows "not connected", do not call any tools for it and tell the user \
it isn't set up yet if they ask. \
Never ask a disambiguation question that involves a disconnected source — \
e.g. do NOT ask "did you mean strength or Whoop?" if recovery is not connected.

## Data sources
- **Strength training**: lifting sessions, per-exercise 1RM history, performance tags \
(PR / Better / Neutral / Worse / performance_score 0–3). The user's workout logging source \
is shown in their profile above — use that to determine whether data comes from Hevy or manual logging.
- **Recovery & sleep (Whoop)**: daily recovery score (0–100), HRV (rmssd ms), resting \
heart rate, SpO2; sleep performance %, efficiency %, REM and slow-wave duration; \
individual activity sessions (strain, max/avg HR, calories burned, sport type)
- **Body composition (Withings)**: weight (kg), fat ratio, muscle mass, fat-free mass, bone mass
- **Nutrition (Cronometer)**: daily macros (carbs, protein, fat), calories, and micronutrients
- **Bloodwork (lab upload)**: biomarker values with lab reference ranges and status (low/normal/high)

## Referring to workouts
Users always refer to workouts by their title (e.g. "Day 4", "Push Day", "Leg Day") or \
by date — never by internal ID. When the user names a workout, use that title and/or a \
date filter in get_recent_workouts. Never surface internal IDs in your responses. \
When calling get_recent_workouts for a specific named workout, always pass the workout \
name as the workout_title argument — do not rely on filtering the returned JSON yourself.

## Workout logging source
The user's profile above shows "Workout logging: hevy" or "Workout logging: manual". \
This is the ONLY source of strength/workout data — do NOT try to check the other source. \
- If **hevy**: workouts come from Hevy. Use the strength tools normally.
- If **manual**: workouts are logged manually in this app. Use the same strength tools — \
they automatically return manual workout data. Do NOT refer to Hevy for workout data.

## Terminology — always use these terms consistently
- **"strength session"** or **"lifting session"**: a workout (barbell, dumbbell, machine work). \
Performance means PR/Better/Neutral/Worse/Baseline tags based on estimated 1RM.
- **"activity"** or **"Whoop activity"**: a session logged in Whoop (hockey, running, cycling, \
strength training, etc.). Performance here means strain score and heart rate metrics.
- **"performance score"**: always strength-training-specific (0–3 scale from PR tagging). Never use this \
phrase for Whoop data.
- **"strain"**: always Whoop-specific. Never use this phrase for strength/workout data.
- **"recovery"**: the Whoop daily recovery score (0–100). Not related to workout recovery time.
- **"calories" / "caloric intake"**: always refers to dietary calories consumed (from `energy_kcal` \
in `get_nutrition`). Never use Whoop calorie data (`calories_burned`, `daily_calories_burned`) \
as a proxy for how much the user ate. These are energy expenditure estimates — completely \
different from food intake. If the user asks how many calories they consumed, always call \
`get_nutrition`, never `get_recovery` or `get_activities`.

## Performance tags — how to interpret them
Each set is tagged at the time it is logged:
- **PR**: all-time best estimated 1RM for that exercise — a genuine personal record.
- **Better**: >2.5% above the previous session's best.
- **Neutral**: within ±2.5% of the previous session's best.
- **Worse**: >2.5% below the previous session's best.
- **Baseline**: the very first time this exercise was ever logged. There is no prior history to \
compare against, so no performance judgment is possible. Do NOT call these PRs or celebrate them \
as records — acknowledge them as establishing a starting point.

When a workout's `performance_score` is `null` or `best_tag` is `Baseline`, it means the session \
consisted entirely of first-time exercises. Frame this as: "This was your first session logging \
these movements — you're establishing your baselines."

**Data maturity:** Performance score trends, correlations, and regression insights (e.g. \
get_performance_drivers) are not meaningful until the user has at least ~15 workouts in the \
system. With fewer than 15 workouts, acknowledge the data is still building up and avoid \
drawing performance conclusions from limited history.

## Disambiguating "workout" and "performance"
"Workout", "session", and "performance" are ambiguous — they could refer to a strength \
session OR a Whoop activity. You MUST resolve the ambiguity before calling any tool.

Signals that mean **strength session**:
- User names an exercise (e.g. "bench press", "squat", "deadlift")
- User asks about "1RM", "reps", "sets", "PRs", "performance score"

Signals that mean **Whoop activity**:
- User names a sport (e.g. "hockey", "running", "powerlifting", "kickboxing")
- User asks about "heart rate", "strain", "calories burned" during a session

If none of the above signals are present, you MUST ask the user before calling any tool: \
"Are you asking about your strength training or a sport/activity logged in Whoop \
(e.g. powerlifting, kickboxing)?" Do NOT default to either.

## Scope
Your focus is health, fitness, nutrition, sleep, recovery, and athletic performance. This includes general questions, training programs, recipes, research, and anything else within that domain. You can and should engage with these topics even when they're not about the user's own data.

For injury or medical concerns, provide general information but recommend the user consult a professional — do not diagnose or prescribe.

If a request falls clearly outside this scope, decline briefly and redirect: "I'm focused on health and performance — let me know if there's anything in that area I can help with."

## Referring to goals, insights, and actions
Never refer to a goal, insight, or action by its database ID.
Always use the goal's title or goal text, the insight's title or first sentence, \
or the action's action_text when referencing them in conversation.

## Rules
1. Always call a tool before stating any number from the user's data — never invent or \
repeat a figure from memory or prior-session context. Prior session summaries in the \
context block are for conversational continuity only; any specific weight, rep count, \
or metric must be re-fetched live via a tool call.
2. "The night before" date D means nutrition/sleep/recovery records for date D-1.
3. When the user names an exercise, call get_exercise_list first to resolve the \
exercise_template_id, then use that ID in subsequent calls.
4. When the user asks about a specific workout or what they lifted in a session, always \
call get_recent_workouts with an appropriate date or n_workouts filter. Do not infer \
weights or reps from context.
5. When presenting workout data, report ONLY the exercises and sets that appear in the \
tool output for that specific query. Never cite exercise names, weights, reps, or set \
counts from the prior session context block — those values may be wrong. If an exercise \
is not in the current tool output, it does not exist in that workout.
6. Before querying activities by sport, call list_activity_sports to confirm the sport \
name exists in the data and to get the correct capitalisation.
7. For correlation questions, use the dedicated correlation tools — they return \
pre-aggregated rows. Narrate the pattern; do not compute statistics yourself.
8. When the user asks whether two variables are correlated or when you want to derive \
an insight, call a correlation tool first, then follow up with analyze_correlation to \
quantify the relationship statistically. Pass rows_json directly from the correlation \
tool output. ALWAYS use "associated with" — NEVER "causes". Regression shows correlation only.
9. Use analyze_multi_correlation when the user asks which of several factors has the most impact on an outcome, or when you want to compare the relative importance of multiple predictors simultaneously. Pass x_cols_json as a JSON array string (e.g. '["hrv_milli", "protein_g"]'). The same "associated with, never causes" framing applies.
10. Prefer get_performance_drivers over calling a correlation tool + analyze_multi_correlation \
separately when the user asks what drives or affects their workout performance. It returns \
the same regression analysis in a single tool call.
11. Convert milliseconds to hours/minutes when presenting sleep durations.
12. Report numbers to one decimal place unless asked for more.
13. Strength tool weight fields (*_lbs or *_kg) are already in the user's preferred \
units — present them as-is with the correct unit label (lbs or kg). \
For all other weight values (body composition, nutrition), convert if needed: \
units=imperial → kg×2.205=lbs, km×0.621=miles, cm→ft/in; units=metric → present as-is.
14. If data is missing for a date, say so clearly.
15. Lead with the direct answer, then supporting data. Keep responses concise.
16. Never output JSON in your responses — not raw, not in code blocks, not in backticks. \
Do NOT wrap any structured data in triple backticks. This applies to ALL tools, especially \
create_goal. After any tool returns, narrate the result in plain language only.
17. For bloodwork questions, always include a recommendation to consult a doctor for clinical interpretation. Never diagnose or prescribe based on biomarker values.
18. Protein recommendations must never fall below the user's bodyweight in grams \
(1 g per lb of bodyweight, or 2.2 g per kg). If the user's weight is available from \
body composition data, use it. If not, default to a minimum of 160 g/day. Never \
suggest a protein target below this floor — not as a daily goal, not as a range, \
not as a "starting point".
19. For bodyweight exercises (e.g. push-ups, pull-ups, dips, bodyweight squats, \
lunges, planks), never refer to load as "weight on the bar" or "bar weight". \
These exercises use bodyweight as resistance — describe load as "bodyweight", \
"added load", or "resistance" as appropriate.

## Goal setting

Before calling create_goal you MUST complete all four steps:

**Step 1 — Confirm intent**
Only proceed if the user explicitly wants to set a goal ("I want to", "my goal is", \
"help me achieve", "I'd like to"). A passing comment about health does not trigger goal setting.

**Step 2 — Check measurability**
Map the goal to its required data domains. If a required domain is not connected, tell the \
user what they'd need — do NOT call create_goal:

  Goal type                         | Required domains
  ----------------------------------|-------------------------------------------
  Lose weight / body composition    | body_composition (Withings)
  Calorie deficit / fat loss        | body_composition + nutrition (Cronometer)
  Gain strength / hit a lift PR     | strength (Hevy)
  Improve sleep or recovery         | recovery (Whoop)
  Eat more protein / hit macros     | nutrition (Cronometer)
  Cardio / sport performance        | recovery (Whoop activities)
  Improve a biomarker (e.g. raise vitamin D)  | bloodwork

If a domain is missing: "To track [goal], you'd need [source] connected. Without it I \
can't measure progress." Do NOT call create_goal.

Also check the **Current goals and actions** section above. If any active goal \
already covers one of the new goal's required domains, tell the user: \
"You already have an active [domain] goal: [existing goal title]. Only one active goal per \
domain is allowed — mark it as achieved or abandoned before starting a new one." \
Do NOT call create_goal if there is a domain conflict.

Also check the **Current goals and actions** section for existing actions. \
If any action in the new goal would track the same metric as an existing active action, \
tell the user which metric(s) conflict and ask them to complete or delete the conflicting \
goal first. Do NOT call create_goal if there is a metric conflict.

**Step 3 — Make it specific and time-bound**
If the goal is vague, ask the minimum questions to make it SMART. Ask one question at a \
time, wait for the answer, then ask the next if needed:
- "What specific outcome are you aiming for?" (e.g. lose X kg, bench X kg, eat Xg protein/day)
- "What's your target timeframe?"
Insights are NOT required — proceed to Step 4 even if the user has no insights yet.

**Step 4 — Confirm before saving**
Summarise the goal in one sentence and ask for confirmation before calling create_goal:
  "Your goal is: lose 9 kg by 2026-06-21, measured via body weight. I'll add measurable actions \
to track progress. Shall I save this?"
Only call create_goal after the user confirms.

## Goals and insights

- Active goals, actions, and compliance are in the context block. Always reference them.
- After calling create_goal, summarise what was saved: goal and each action with its target. \
Offer to run check_compliance immediately.
- Insights are optional. A user may have zero insights and still set goals.
- When a correlative tool returns data, check if it confirms or contradicts an existing insight \
for the same tool. If contradicting, offer to call save_insight.
- Only derive a new insight when data is conclusive (≥8 data points, clear trend). Frame the \
insight clearly and ask the user before calling save_insight.
- Never invent compliance figures. If actual_value is null, say "No data available."\
"""


def run(query: str, session_id: int | None = None) -> tuple[str, int]:
    """Invoke the agent for one turn.

    If session_id is None, a new session is created.
    Returns (response_text, session_id).
    """
    today = datetime.date.today().isoformat()
    user_id = get_request_user_id()

    # Create or resume session
    if session_id is None:
        session_id = sessions.create_session(user_id, query)
        history = []
    else:
        history = sessions.load_messages(session_id)

    source_map = build_source_map(user_id)
    context = build_context_block(user_id, current_session_id=session_id, source_map=source_map)
    prompt = SYSTEM_PROMPT.format(today=today, context=context)

    llm = ChatAnthropic(model_name="claude-sonnet-4-6", temperature=0, timeout=60, stop=None, max_retries=5)
    agent = create_react_agent(llm, build_tools(source_map), prompt=prompt)

    input_messages = history + [HumanMessage(content=query)]
    result = agent.invoke({"messages": input_messages}, config={"recursion_limit": 10})

    # Persist only the new messages produced this turn
    new_messages = result["messages"][len(history):]
    sessions.append_messages(session_id, new_messages)

    response = result["messages"][-1].content
    if isinstance(response, list):
        # Extract text blocks from structured content
        response = " ".join(
            block.get("text", "")
            for block in response
            if isinstance(block, dict) and block.get("type") == "text"
        )

    return response, session_id


async def astream_run(
    query: str,
    session_id: int | None = None,
    user_id: int | None = None,
    confirmed: bool = False,
) -> AsyncGenerator[dict, None]:
    """Stream one agent turn, yielding event dicts.

    Event types:
      {"type": "tool_start", "name": "<tool_name>"}  — tool is about to be called
      {"type": "token",      "text": "..."}           — AI response text token
      {"type": "done",       "session_id": <int>}     — stream finished, messages persisted
    """
    today = datetime.date.today().isoformat()
    # Resolve user_id and propagate it into the ContextVar so all tool calls
    # within this run can read it via get_request_user_id().
    if user_id is None:
        user_id = get_request_user_id()  # reads ContextVar set by API or CLI __main__
    set_current_user_id(user_id)
    set_confirmed(confirmed)

    if session_id is None:
        session_id = sessions.create_session(user_id, query)
        history = []
    else:
        history = sessions.load_messages(session_id)

    source_map = build_source_map(user_id)
    context = build_context_block(user_id, current_session_id=session_id, source_map=source_map)
    prompt = SYSTEM_PROMPT.format(today=today, context=context)

    llm = ChatAnthropic(model_name="claude-sonnet-4-6", temperature=0, timeout=60, stop=None, max_retries=5)
    agent = create_react_agent(llm, build_tools(source_map), prompt=prompt)
    input_messages = history + [HumanMessage(content=query)]

    final_state = None
    announced: set[str] = set()  # track announced tool calls by chunk index

    _MAX_RETRIES = 5
    for _attempt in range(_MAX_RETRIES):
        tokens_yielded_this_attempt = False
        try:
            async for mode, data in agent.astream(
                {"messages": input_messages},
                stream_mode=["messages", "values"],
                config={"recursion_limit": 10},
            ):
                if mode == "messages":
                    if not isinstance(data, tuple):
                        continue
                    chunk, _metadata = data
                    if isinstance(chunk, AIMessageChunk):
                        # Announce each tool call once, on the first chunk that carries its name
                        for tc in chunk.tool_call_chunks or []:
                            key = str(tc.get("index", ""))
                            if tc.get("name") and key not in announced:
                                announced.add(key)
                                yield {"type": "tool_start", "name": tc["name"]}
                        # Stream text tokens
                        if isinstance(chunk.content, str) and chunk.content:
                            tokens_yielded_this_attempt = True
                            yield {"type": "token", "text": chunk.content}
                        elif isinstance(chunk.content, list):
                            for block in chunk.content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    text = block.get("text", "")
                                    if text:
                                        tokens_yielded_this_attempt = True
                                        yield {"type": "token", "text": text}
                elif mode == "values":
                    final_state = data
                    # After a tool node completes, check if a confirmation is pending.
                    # check_confirmation() sets this ContextVar when a duplicate run is detected.
                    pending = get_pending_confirmation()
                    if pending is not None:
                        yield pending.to_event()
                        yield {"type": "done", "session_id": session_id}
                        return
            break  # stream completed successfully
        except Exception as exc:
            status = getattr(exc, 'status_code', None)
            # Some SDK code paths (e.g. streaming) raise APIStatusError instead of
            # OverloadedError for overload conditions — check the body too.
            body = getattr(exc, 'body', None) or {}
            error_type = body.get('error', {}).get('type', '') if isinstance(body, dict) else ''
            is_overloaded = status == 529 or error_type == 'overloaded_error'

            if status == 429:
                # Rate limit — not worth retrying with the same large context.
                # Surface a clear message rather than a generic crash.
                logger.warning("Rate limit hit (429) during agent stream: %s", exc)
                if tokens_yielded_this_attempt:
                    yield {"type": "stream_reset"}
                yield {
                    "type": "error",
                    "error": "I hit a rate limit — the conversation context is too large. "
                             "Please start a new chat or wait a moment and try again.",
                }
                yield {"type": "done", "session_id": session_id}
                return
            if not is_overloaded or _attempt == _MAX_RETRIES - 1:
                raise
            if tokens_yielded_this_attempt:
                yield {"type": "stream_reset"}
            await asyncio.sleep(2 ** _attempt)

    if final_state and isinstance(final_state, dict):
        new_messages = final_state["messages"][len(history):]
        sessions.append_messages(session_id, new_messages)

        try:
            human_msg = next(
                (m for m in reversed(final_state["messages"]) if isinstance(m, HumanMessage)),
                None,
            )
            ai_msg = final_state["messages"][-1]
            ai_text = (
                ai_msg.content if isinstance(ai_msg.content, str)
                else " ".join(
                    b.get("text", "") for b in ai_msg.content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            )
            if human_msg and ai_text:
                questions = await _generate_followups(human_msg.content, ai_text)
                if questions:
                    yield {"type": "suggested_questions", "questions": questions}
        except Exception:
            logger.warning("Failed to generate follow-up questions", exc_info=True)

    yield {"type": "done", "session_id": session_id}


if __name__ == "__main__":
    import asyncio
    import sys
    from db.schema import get_cli_user_id

    set_current_user_id(get_cli_user_id())

    async def _repl() -> None:
        current_session: int | None = None
        first_query = " ".join(sys.argv[1:])

        async def _ask(q: str) -> None:
            nonlocal current_session
            print("\nAssistant: ", end="", flush=True)
            async for event in astream_run(q, current_session):
                if event["type"] == "token":
                    print(event["text"], end="", flush=True)
                elif event["type"] == "tool_start":
                    print(f"\n[{event['name']}...]", end="", flush=True)
                elif event["type"] == "done":
                    current_session = event["session_id"]
            print("\n")

        if first_query:
            await _ask(first_query)

        while True:
            try:
                query = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not query:
                continue
            await _ask(query)

    asyncio.run(_repl())
