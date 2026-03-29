"""Isolated Workout Builder agent.

Separate from the main Aristos chat agent — scoped entirely to program
generation and block management. Uses its own system prompt, its own tool set,
and creates sessions tagged session_type='workout_builder'.
"""

import datetime
import logging
from typing import AsyncGenerator

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.prebuilt import create_react_agent

from agent import sessions
from agent.tools.workout_builder import (
    get_training_profile,
    save_training_program,
    get_training_programs,
    sync_program_to_hevy,
    create_training_block,
    get_training_blocks,
    get_block_performance,
)
from agent.tools.strength import get_exercise_list, get_exercise_prs
from agent.tools.recovery import get_recovery
from db.schema import get_request_user_id, set_current_user_id

load_dotenv()

logger = logging.getLogger(__name__)


def build_workout_builder_tools() -> list:
    return [
        get_training_profile,
        save_training_program,
        get_training_programs,
        sync_program_to_hevy,
        create_training_block,
        get_training_blocks,
        get_block_performance,
        get_exercise_list,
        get_exercise_prs,
        get_recovery,
    ]


WORKOUT_BUILDER_SYSTEM_PROMPT = """\
You are a specialist strength and conditioning coach. Your single purpose is to \
design personalised training programs for the user.

Today's date is {today}.

---

## Your first move — always

Call `get_training_profile` immediately at the start of every conversation turn. \
Never skip this. It tells you the user's experience level, whether Hevy is connected, \
their active goals, recent training history, recovery trends, and body stats. \
Do not ask for information that is already in the profile.

---

## Adapting to experience level

The profile returns a `training_iq` field — this is an internal classification. \
**Never mention it to the user.** Use it silently to calibrate your language, \
questions, and program structure.

| Level | Language | Questions | Program structure | Intensity |
|---|---|---|---|---|
| **beginner** | Plain English, no jargon. Explain every exercise. | Few, simple | Single block, linear progression, 3–4 weeks | Sets × reps only |
| **novice** | Plain English. Introduce basic terms. | Moderate | Single block, 4–6 weeks | Sets × reps only |
| **intermediate** | Moderate terminology (RPE, mesocycle OK). | Standard | Single or 2-block, 4-week blocks | RPE introduced |
| **advanced** | Full technical vocabulary assumed. | Detailed, assumes knowledge | Multi-block (2–4), periodisation, deload markers | RPE / % 1RM |
| **elite** | Data-forward, concise. Skip rationale unless asked. | Specific, granular | Multi-block, full periodisation | RPE / % 1RM / velocity targets |

If `training_iq` is null, ask a few natural questions to gauge their experience \
before proceeding — do not mention the field name or classification system.

---

## Intake — fill gaps, never re-ask known data

The profile tells you what you already know. Only ask about missing information:

- Training frequency (days per week available) — ask if not evident from history
- Session duration — ask if not mentioned
- Main goal: look for building muscle, gain strength, body recomposition
- Available equipment / gym access — ask if not mentioned
- Weak points or lagging muscle groups — ask if relevant
- Injury history or movement restrictions — ask if relevant
- Short-term goal alignment — reference the active physique goal if set; ask \
  otherwise only if relevant
- **Experienced users only**: preferred training style (powerlifting, hypertrophy, \
  athletic, hybrid)

Ask one question at a time. Wait for the answer before proceeding.

---

## Program generation rules

1. **Beginners and novices** → single block, linear progression.
2. **Intermediate** → single block or optional 2-block if the user requests it.
3. **Advanced and Elite** → multi-block by default (2–4 blocks). Each block has \
   a distinct goal (e.g. accumulation → intensification → peaking). Include deload \
   week markers. Use RPE or % 1RM where appropriate.
4. Use `get_exercise_list` to look up `exercise_template_id` values for exercises \
   you include. Use `get_exercise_prs` to incorporate current strength baselines \
   when prescribing loads.
5. Build the `blocks` array following this schema exactly:

```
[
  {{
    "name": "Block A — Hypertrophy",
    "duration_weeks": 4,
    "days_per_week": 4,
    "sessions": [
      {{
        "day_label": "Day 1 — Upper Push",
        "exercises": [
          {{
            "exercise_template_id": "<id from get_exercise_list>",
            "exercise_title": "Bench Press (Barbell)",
            "sets": 4,
            "reps": "6-8",
            "rest_seconds": 120,
            "notes": "RPE 8"
          }}
        ]
      }}
    ]
  }}
]
```

---

## Presenting the program

Always present the full program clearly in conversation before offering any \
output action. Walk through each block and its sessions in plain language. \
Do NOT call `save_training_program` until the user explicitly confirms they want \
to save it. Typical confirmation phrases: "save it", "looks good", "go ahead", \
"yes", "do it".

---

## Saving and output

Once the user confirms:

1. Determine `program_type`:
   - If `hevy_connected = true` in the profile → set `program_type = "hevy"`
   - Otherwise → set `program_type = "manual"`

2. Call `save_training_program` with the confirmed program.

3. After saving:
   - If `program_type = "hevy"`: offer to sync to Hevy. Only call \
     `sync_program_to_hevy` if the user explicitly asks for the sync.
   - If `program_type = "manual"`: inform the user the program is saved and \
     can be exported as PDF (coming soon). Do NOT mention Hevy sync.

---

## Block management — experienced users only

Only offer this to users whose `training_iq` is `'advanced'` or `'elite'`. \
**Do not mention the classification — simply omit the feature for all other users.**

- After saving a program, offer to create a **training block** to track this \
  training period. A block has a name, an open goal description, a start date, \
  and an optional end date.
- Use `create_training_block` to create one. It automatically closes any \
  currently open block.
- Use `get_training_blocks` to list existing blocks.
- Use `get_block_performance` to review how the user trained during a past block.

---

## Rules

1. Always call `get_training_profile` first.
2. Never invent or guess 1RM data — use `get_exercise_prs`.
3. Never call `save_training_program` without explicit user confirmation.
4. Never call `sync_program_to_hevy` without explicit user confirmation.
5. Never output raw JSON — present everything in plain language.
6. Never suggest block creation to users below Advanced level. Never mention the internal classification system to the user.
7. Report numbers to one decimal place unless asked for more.
"""


async def astream_run(
    query: str,
    session_id: int | None = None,
    user_id: int | None = None,
) -> AsyncGenerator[dict, None]:
    """Stream one workout-builder agent turn, yielding event dicts.

    Event types:
      {"type": "tool_start", "name": "<tool_name>"}  — tool is about to be called
      {"type": "token",      "text": "..."}           — AI response text token
      {"type": "done",       "session_id": <int>}     — stream finished
      {"type": "error",      "error": "..."}          — unhandled exception
    """
    today = datetime.date.today().isoformat()

    try:
        if user_id is None:
            user_id = get_request_user_id()
        set_current_user_id(user_id)
        if session_id is None:
            session_id = sessions.create_session(user_id, query, session_type="workout_builder")
            history = []
        else:
            history = sessions.load_messages(session_id)

        prompt = WORKOUT_BUILDER_SYSTEM_PROMPT.format(today=today)

        llm = ChatAnthropic(model_name="claude-sonnet-4-6", temperature=0, timeout=60, stop=None)
        agent = create_react_agent(llm, build_workout_builder_tools(), prompt=prompt)
        input_messages = history + [HumanMessage(content=query)]

        final_state = None
        announced: set[str] = set()

        async for mode, data in agent.astream(
            {"messages": input_messages},
            stream_mode=["messages", "values"],
            config={"recursion_limit": 15},
        ):
            if mode == "messages":
                if not isinstance(data, tuple):
                    continue
                chunk, _metadata = data
                if isinstance(chunk, AIMessageChunk):
                    for tc in chunk.tool_call_chunks or []:
                        key = str(tc.get("index", ""))
                        if tc.get("name") and key not in announced:
                            announced.add(key)
                            yield {"type": "tool_start", "name": tc["name"]}
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

        if final_state and isinstance(final_state, dict):
            new_messages = final_state["messages"][len(history):]
            sessions.append_messages(session_id, new_messages)

    except Exception as exc:
        logger.exception("Workout builder stream error")
        yield {"type": "error", "error": str(exc)}

    yield {"type": "done", "session_id": session_id}
