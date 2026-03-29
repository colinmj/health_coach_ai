"""Video form analysis via Claude vision.

Pipeline:
  1. Extract ~15 frames from the video using OpenCV.
  2. Retrieve exercise-specific form standards from the knowledge base (document_chunks).
  3. Send frames + standards to Claude vision and request a structured JSON critique.
  4. Persist the result in the form_analyses table.

Public API:
  analyze_video(file_bytes, exercise_name, conn) -> dict
  save_form_analysis(result, user_id, exercise_name, frame_count, conn)
"""

import base64
import json
import os
import tempfile

import anthropic

SUPPORTED_EXERCISES: set[str] = {
    "barbell_squat",
    "deadlift",
    "bench_press",
    "overhead_press",
}

_GENERIC_STANDARDS = (
    "Evaluate the lift for safe joint alignment, controlled movement throughout the "
    "range of motion, stable spine position, and appropriate bar path. Identify any "
    "technique faults that could increase injury risk or reduce performance."
)

_ANALYSIS_PROMPT = """You are an expert strength and conditioning coach reviewing a lifting video.

Exercise: {exercise_name}

Form standards to evaluate against:
{standards}

You are looking at {frame_count} sequential frames from the video.

Return ONLY a valid JSON object with this exact shape — no prose, no markdown fences:
{{
  "overall_rating": "good" | "needs_work" | "safety_concern",
  "findings": [
    {{"aspect": "<what was evaluated>", "severity": "ok" | "warning" | "error", "note": "<specific observation>"}}
  ],
  "cues": ["<actionable coaching cue>"]
}}

Guidelines:
- "good": solid technique with minor or no issues
- "needs_work": clear technique faults that will limit progress
- "safety_concern": faults that meaningfully raise injury risk
- Include 3-6 findings covering the key aspects of this lift
- Include 1-4 concrete, actionable coaching cues
- Be specific to what you can observe in the frames"""


def _get_form_standards(exercise_name: str, conn) -> str:
    """Return form standards text from the knowledge base, or a generic fallback."""
    doc_name = f"form_standards_{exercise_name}"
    rows = conn.execute(
        "SELECT content FROM document_chunks WHERE document_name = %s ORDER BY chunk_index",
        (doc_name,),
    ).fetchall()
    if rows:
        return "\n\n".join(row["content"] for row in rows)
    return _GENERIC_STANDARDS


def _extract_frames(file_bytes: bytes, max_frames: int = 15) -> list[str]:
    """Extract up to max_frames evenly-spaced frames from video bytes.

    Returns a list of base64-encoded JPEG strings.
    Raises RuntimeError if OpenCV cannot open the file.
    """
    import cv2  # local import — only needed when processing videos

    # Write to a temp file because cv2.VideoCapture requires a file path
    suffix = ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            raise RuntimeError("Could not open video file. Ensure it is a valid MP4 or MOV.")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

        # Sample every ~0.5s, but cap at max_frames
        step = max(1, int(fps * 0.5))
        sample_positions = list(range(0, total_frames, step))[:max_frames]

        frames_b64: list[str] = []
        for pos in sample_positions:
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ret, frame = cap.read()
            if not ret:
                continue
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                frames_b64.append(base64.standard_b64encode(buf.tobytes()).decode())

        cap.release()
    finally:
        os.unlink(tmp_path)

    if not frames_b64:
        raise RuntimeError("No frames could be extracted from the video.")

    return frames_b64


def analyze_video(file_bytes: bytes, exercise_name: str, conn) -> dict:
    """Extract frames, retrieve form standards, and return a structured critique dict."""
    if exercise_name not in SUPPORTED_EXERCISES:
        raise ValueError(
            f"Unsupported exercise '{exercise_name}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXERCISES))}"
        )

    standards = _get_form_standards(exercise_name, conn)
    frames_b64 = _extract_frames(file_bytes)

    display_name = exercise_name.replace("_", " ").title()
    prompt_text = _ANALYSIS_PROMPT.format(
        exercise_name=display_name,
        standards=standards,
        frame_count=len(frames_b64),
    )

    # Build the message content: all frames first, then the text prompt
    content: list[dict] = []
    for b64 in frames_b64:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": b64,
            },
        })
    content.append({"type": "text", "text": prompt_text})

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": content}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Claude returned non-JSON response: {exc}\n\nResponse:\n{raw[:500]}") from exc

    result["frame_count"] = len(frames_b64)
    return result


def save_form_analysis(
    result: dict,
    user_id: int,
    exercise_name: str,
    conn,
) -> int:
    """Persist a form analysis result to the database. Returns the new row id."""
    # Snapshot today's recovery score if available
    recovery_row = conn.execute(
        """
        SELECT score FROM recovery
        WHERE user_id = %s AND date = CURRENT_DATE
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    recovery_score = float(recovery_row["score"]) if recovery_row else None

    row = conn.execute(
        """
        INSERT INTO form_analyses
            (user_id, exercise_name, frame_count, overall_rating, findings, cues, recovery_score_day_of)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
        RETURNING id
        """,
        (
            user_id,
            exercise_name,
            result.get("frame_count"),
            result.get("overall_rating"),
            json.dumps(result.get("findings", [])),
            json.dumps(result.get("cues", [])),
            recovery_score,
        ),
    ).fetchone()
    return row["id"]
