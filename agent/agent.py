
import datetime
import json
from typing import AsyncGenerator
from dotenv import load_dotenv

from langchain_anthropic import ChatAnthropic

from langchain_core.messages import HumanMessage, AIMessageChunk
from langgraph.prebuilt import create_react_agent

from agent.tools import build_tools
from agent import sessions
import analytics.goals as goals_analytics
import analytics.trends as trends_analytics
from db.schema import get_local_user_id, get_connection

load_dotenv()

def build_context_block(user_id: int, current_session_id: int | None = None) -> str:
    today = datetime.date.today()
    soon = today + datetime.timedelta(days=7)

    goals = goals_analytics.get_goals_with_protocols_and_actions(user_id)
    pinned_insights = [
        i for i in goals_analytics.get_active_insights(user_id) if i.get("pinned")
    ]

    # Latest compliance per action
    with get_connection() as conn:
        compliance_rows = conn.execute(
            """
            SELECT DISTINCT ON (action_id)
                action_id, actual_value, met, week_start_date
            FROM action_compliance
            WHERE user_id = %s
            ORDER BY action_id, week_start_date DESC
            """,
            (user_id,),
        ).fetchall()
    compliance_map = {r["action_id"]: r for r in compliance_rows}

    lines = ["## Current goals, protocols & compliance\n"]

    if not goals:
        lines.append("No active goals.\n")
    else:
        for g in goals:
            lines.append(f"### Goal (id={g['id']}, status={g['status']}): {g['goal_text']}")
            if g.get("target_date"):
                lines.append(f"  Target date: {g['target_date']}")
            for p in g.get("protocols", []):
                lines.append(f"  Protocol (id={p['id']}, status={p['status']}): {p['protocol_text']}")
                review = p.get("review_date")
                if review:
                    lines.append(f"    Review date: {review}")
                    if str(review) <= soon.isoformat():
                        lines.append("    ⚠️ REVIEW DUE WITHIN 7 DAYS")
                for a in p.get("actions", []):
                    comp = compliance_map.get(a["id"])
                    if comp:
                        actual = comp["actual_value"] if comp["actual_value"] is not None else "no data"
                        met_str = {True: "✅", False: "❌", None: "—"}.get(comp["met"], "—")
                        lines.append(
                            f"    Action (id={a['id']}): {a['action_text']} "
                            f"[{met_str} actual={actual}, target={a['target_value']}]"
                        )
                    else:
                        lines.append(f"    Action (id={a['id']}): {a['action_text']} [no compliance data yet]")

    if pinned_insights:
        lines.append("\n## Pinned insights")
        for i in pinned_insights:
            lines.append(f"- [{i['correlative_tool']}] {i['insight']} (effect={i['effect']}, confidence={i['confidence']})")

    # Trends block
    trends_block = trends_analytics.build_trends_block(user_id)
    if trends_block:
        lines.append(f"\n{trends_block}")

    # Recent session context (cross-session memory)
    recent_context = sessions.get_recent_context(user_id, exclude_session_id=current_session_id)
    if recent_context:
        lines.append(f"\n{recent_context}")

    return "\n".join(lines)


SYSTEM_PROMPT = """\
You are a peak performance coach and personal health analytics assistant with access to real health data.

Today's date is {today}.

{context}

## Data sources
- **Strength training (Hevy)**: lifting sessions, per-exercise 1RM history, performance tags \
(PR / Better / Neutral / Worse / performance_score 0–3)
- **Recovery & sleep (Whoop)**: daily recovery score (0–100), HRV (rmssd ms), resting \
heart rate, SpO2; sleep performance %, efficiency %, REM and slow-wave duration; \
individual activity sessions (strain, max/avg HR, calories burned, sport type)
- **Body composition (Withings)**: weight (kg), fat ratio, muscle mass, fat-free mass, bone mass
- **Nutrition (Cronometer)**: daily macros (carbs, protein, fat), calories, and micronutrients

## Terminology — always use these terms consistently
- **"strength session"** or **"lifting session"**: a workout logged in Hevy (barbell, dumbbell, \
machine work). Performance here means PR/Better/Neutral/Worse tags based on estimated 1RM.
- **"activity"** or **"Whoop activity"**: a session logged in Whoop (hockey, running, cycling, \
strength training, etc.). Performance here means strain score and heart rate metrics.
- **"performance score"**: always Hevy-specific (0–3 scale from PR tagging). Never use this \
phrase for Whoop data.
- **"strain"**: always Whoop-specific. Never use this phrase for Hevy data.
- **"recovery"**: the Whoop daily recovery score (0–100). Not related to workout recovery time.

## Disambiguating "workout" and "performance"
"Workout", "session", and "performance" are ambiguous — they could refer to a Hevy strength \
session OR a Whoop activity. You MUST resolve the ambiguity before calling any tool.

Signals that mean **strength session (Hevy)**:
- User names an exercise (e.g. "bench press", "squat", "deadlift")
- User asks about "1RM", "reps", "sets", "PRs", "performance score"

Signals that mean **Whoop activity**:
- User names a sport (e.g. "hockey", "running", "powerlifting", "kickboxing")
- User asks about "heart rate", "strain", "calories burned" during a session

If none of the above signals are present, you MUST ask the user before calling any tool: \
"Are you asking about your strength training (Hevy) or a sport/activity logged in Whoop \
(e.g. powerlifting, kickboxing)?" Do NOT default to Hevy.

## Rules
1. Always call a tool before stating a number — never invent data.
2. "The night before" date D means nutrition/sleep/recovery records for date D-1.
3. When the user names an exercise, call get_exercise_list first to resolve the \
exercise_template_id, then use that ID in subsequent calls.
4. Before querying activities by sport, call list_activity_sports to confirm the sport \
name exists in the data and to get the correct capitalisation.
5. For correlation questions, use the dedicated correlation tools — they return \
pre-aggregated rows. Narrate the pattern; do not compute statistics yourself.
6. Convert milliseconds to hours/minutes when presenting sleep durations.
7. Report numbers to one decimal place unless asked for more.
8. If data is missing for a date, say so clearly.
9. Lead with the direct answer, then supporting data. Keep responses concise.

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

If a domain is missing: "To track [goal], you'd need [source] connected. Without it I \
can't measure progress." Do NOT call create_goal.

**Step 3 — Make it specific and time-bound**
If the goal is vague, ask the minimum questions to make it SMART. Ask one question at a \
time, wait for the answer, then ask the next if needed:
- "What specific outcome are you aiming for?" (e.g. lose X kg, bench X kg, eat Xg protein/day)
- "What's your target timeframe?"
Insights are NOT required — proceed to Step 4 even if the user has no insights yet.

**Step 4 — Confirm before saving**
Summarise the goal in one sentence and ask for confirmation before calling create_goal:
  "Your goal is: lose 9 kg by 2026-06-21, measured via body weight. I'll create a protocol \
with daily calorie and weigh-in actions. Shall I save this?"
Only call create_goal after the user confirms.

## Goals, protocols, and insights

- Active goals, protocols, actions, and compliance are in the context block. Always reference them.
- After calling create_goal, summarise what was saved: goal, protocol, and each action with its \
target. Offer to run check_compliance immediately.
- Insights are optional. A user may have zero insights and still set goals.
- When a correlative tool returns data, check if it confirms or contradicts an existing insight \
for the same tool. If contradicting, offer to call save_insight.
- Only derive a new insight when data is conclusive (≥8 data points, clear trend). Frame the \
insight clearly and ask the user before calling save_insight.
- If a protocol review_date is within 7 days, flag it and offer to run assess_protocol.
- Never invent compliance figures. If actual_value is null, say "No data available."\
"""


def run(query: str, session_id: int | None = None) -> tuple[str, int]:
    """Invoke the agent for one turn.

    If session_id is None, a new session is created.
    Returns (response_text, session_id).
    """
    today = datetime.date.today().isoformat()
    user_id = get_local_user_id()

    # Create or resume session
    if session_id is None:
        session_id = sessions.create_session(user_id, query)
        history = []
    else:
        history = sessions.load_messages(session_id)

    context = build_context_block(user_id, current_session_id=session_id)
    prompt = SYSTEM_PROMPT.format(today=today, context=context)

    llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
    agent = create_react_agent(llm, build_tools(), prompt=prompt)

    input_messages = history + [HumanMessage(content=query)]
    result = agent.invoke({"messages": input_messages})

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
    query: str, session_id: int | None = None
) -> AsyncGenerator[dict, None]:
    """Stream one agent turn, yielding event dicts.

    Event types:
      {"type": "tool_start", "name": "<tool_name>"}  — tool is about to be called
      {"type": "token",      "text": "..."}           — AI response text token
      {"type": "done",       "session_id": <int>}     — stream finished, messages persisted
    """
    today = datetime.date.today().isoformat()
    user_id = get_local_user_id()

    if session_id is None:
        session_id = sessions.create_session(user_id, query)
        history = []
    else:
        history = sessions.load_messages(session_id)

    context = build_context_block(user_id, current_session_id=session_id)
    prompt = SYSTEM_PROMPT.format(today=today, context=context)

    llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
    agent = create_react_agent(llm, build_tools(), prompt=prompt)
    input_messages = history + [HumanMessage(content=query)]

    final_state = None
    announced: set[str] = set()  # track announced tool calls by chunk index

    async for mode, data in agent.astream(
        {"messages": input_messages},
        stream_mode=["messages", "values"],
    ):
        if mode == "messages":
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
                    yield {"type": "token", "text": chunk.content}
                elif isinstance(chunk.content, list):
                    for block in chunk.content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            if text:
                                yield {"type": "token", "text": text}
        elif mode == "values":
            final_state = data

    if final_state:
        new_messages = final_state["messages"][len(history):]
        sessions.append_messages(session_id, new_messages)

    yield {"type": "done", "session_id": session_id}


if __name__ == "__main__":
    import asyncio
    import sys

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
