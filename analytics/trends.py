"""Weekly trend summaries for injection into the agent system prompt.

Compares the last 7 days against the prior 7 days for key health metrics.
Returns a markdown block; returns an empty string if no data is available.
"""

from datetime import date, timedelta

from db.schema import get_connection


def _arrow(now, prev, lower_is_better: bool = False) -> str:
    if prev is None or prev == 0 or now is None:
        return "→"
    pct = (now - prev) / abs(prev) * 100
    if lower_is_better:
        pct = -pct
    if pct > 5:
        return "↑"
    if pct < -5:
        return "↓"
    return "→"


def build_trends_block(user_id: int, as_of: date | None = None) -> str:
    """Return a markdown trends block comparing the last 7 days to the prior 7 days.

    as_of defaults to today. Pass an explicit date in tests.
    """
    today = as_of or date.today()
    week_start = today - timedelta(days=7)
    prior_start = today - timedelta(days=14)

    lines: list[str] = []

    with get_connection() as conn:
        # --- Recovery & HRV ---
        rec = conn.execute(  # type: ignore[call-overload]
            """
            SELECT
                AVG(CASE WHEN date >= %s THEN recovery_score     END) AS rec_now,
                AVG(CASE WHEN date <  %s THEN recovery_score     END) AS rec_prev,
                AVG(CASE WHEN date >= %s THEN hrv_rmssd_milli    END) AS hrv_now,
                AVG(CASE WHEN date <  %s THEN hrv_rmssd_milli    END) AS hrv_prev
            FROM recovery
            WHERE user_id = %s AND date >= %s AND date < %s
            """,
            (week_start, week_start, week_start, week_start,
             user_id, prior_start, today),
        ).fetchone()  # type: ignore[index]

        # --- Sleep ---
        slp = conn.execute(  # type: ignore[call-overload]
            """
            SELECT
                AVG(CASE WHEN date >= %s THEN sleep_performance_percentage END) AS slp_now,
                AVG(CASE WHEN date <  %s THEN sleep_performance_percentage END) AS slp_prev
            FROM sleep
            WHERE user_id = %s AND date >= %s AND date < %s AND is_nap = FALSE
            """,
            (week_start, week_start, user_id, prior_start, today),
        ).fetchone()  # type: ignore[index]

        # --- Workouts ---
        wrk = conn.execute(  # type: ignore[call-overload]
            """
            SELECT
                COUNT(CASE WHEN start_time::date >= %s THEN 1 END) AS wrk_now,
                COUNT(CASE WHEN start_time::date <  %s THEN 1 END) AS wrk_prev
            FROM hevy_workouts
            WHERE user_id = %s AND start_time::date >= %s AND start_time::date < %s
            """,
            (week_start, week_start, user_id, prior_start, today),
        ).fetchone()  # type: ignore[index]

        # --- Nutrition ---
        nut = conn.execute(  # type: ignore[call-overload]
            """
            SELECT
                AVG(CASE WHEN date >= %s THEN protein_g    END) AS prot_now,
                AVG(CASE WHEN date <  %s THEN protein_g    END) AS prot_prev,
                AVG(CASE WHEN date >= %s THEN energy_kcal  END) AS kcal_now,
                AVG(CASE WHEN date <  %s THEN energy_kcal  END) AS kcal_prev
            FROM nutrition_daily
            WHERE user_id = %s AND date >= %s AND date < %s
            """,
            (week_start, week_start, week_start, week_start,
             user_id, prior_start, today),
        ).fetchone()  # type: ignore[index]

        # --- Weight (latest reading vs latest reading before the window) ---
        bdy_now = conn.execute(  # type: ignore[call-overload]
            "SELECT weight_kg FROM body_measurements "
            "WHERE user_id = %s AND date < %s ORDER BY date DESC LIMIT 1",
            (user_id, today),
        ).fetchone()  # type: ignore[index]
        bdy_prev = conn.execute(  # type: ignore[call-overload]
            "SELECT weight_kg FROM body_measurements "
            "WHERE user_id = %s AND date < %s ORDER BY date DESC LIMIT 1",
            (user_id, week_start),
        ).fetchone()  # type: ignore[index]

    # --- Build lines ---
    if rec["rec_now"] is not None:
        arrow = _arrow(rec["rec_now"], rec["rec_prev"])
        prev_str = f", prev {round(rec['rec_prev'], 1)}" if rec["rec_prev"] is not None else ""
        lines.append(f"- Recovery score: {round(rec['rec_now'], 1)}/100 {arrow}{prev_str}")

    if rec["hrv_now"] is not None:
        arrow = _arrow(rec["hrv_now"], rec["hrv_prev"])
        prev_str = f", prev {round(rec['hrv_prev'], 1)}ms" if rec["hrv_prev"] is not None else ""
        lines.append(f"- HRV: {round(rec['hrv_now'], 1)}ms {arrow}{prev_str}")

    if slp["slp_now"] is not None:
        arrow = _arrow(slp["slp_now"], slp["slp_prev"])
        prev_str = f", prev {round(slp['slp_prev'], 1)}%" if slp["slp_prev"] is not None else ""
        lines.append(f"- Sleep performance: {round(slp['slp_now'], 1)}% {arrow}{prev_str}")

    if wrk["wrk_now"] is not None and (wrk["wrk_now"] > 0 or wrk["wrk_prev"] > 0):
        arrow = _arrow(wrk["wrk_now"], wrk["wrk_prev"])
        prev_str = f", prev {wrk['wrk_prev']}" if wrk["wrk_prev"] is not None else ""
        lines.append(f"- Workouts: {wrk['wrk_now']} this week {arrow}{prev_str}")

    if nut["prot_now"] is not None:
        arrow = _arrow(nut["prot_now"], nut["prot_prev"])
        prev_str = f", prev {round(nut['prot_prev'], 1)}g" if nut["prot_prev"] is not None else ""
        lines.append(f"- Avg protein: {round(nut['prot_now'], 1)}g/day {arrow}{prev_str}")

    if nut["kcal_now"] is not None:
        arrow = _arrow(nut["kcal_now"], nut["kcal_prev"])
        prev_str = f", prev {round(nut['kcal_prev'], 1)} kcal" if nut["kcal_prev"] is not None else ""
        lines.append(f"- Avg calories: {round(nut['kcal_now'], 1)} kcal/day {arrow}{prev_str}")

    if bdy_now is not None:
        w_now = bdy_now["weight_kg"]
        if bdy_prev is not None:
            delta = w_now - bdy_prev["weight_kg"] 
            lines.append(f"- Weight: {w_now:.1f} kg ({delta:+.1f} kg vs 7 days ago)")
        else:
            lines.append(f"- Weight: {w_now:.1f} kg")

    if not lines:
        return ""

    header = f"## Trends (last 7 days vs prior 7 days, as of {today})\n"
    return header + "\n".join(lines)
