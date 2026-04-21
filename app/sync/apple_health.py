"""Sync Apple Health XML export into PostgreSQL.

Run:
    python -m sync.apple_health path/to/export.xml

Export from the iPhone Health app: Profile → Export All Health Data → share the zip.
Unzip and point this script at the export.xml inside.

Each run is idempotent — records are upserted by external_id.
"""

import hashlib
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

from db.schema import get_connection, get_request_user_id, set_current_user_id, get_cli_user_id, init_db
from sync.activity_categories import classify_activity

load_dotenv()

# ---------------------------------------------------------------------------
# Constants — HealthKit type identifiers
# ---------------------------------------------------------------------------

_SLEEP_TYPE = "HKCategoryTypeIdentifierSleepAnalysis"
_HRV_TYPE = "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"
_RHR_TYPE = "HKQuantityTypeIdentifierRestingHeartRate"
_BODY_MASS_TYPE = "HKQuantityTypeIdentifierBodyMass"
_BODY_FAT_TYPE = "HKQuantityTypeIdentifierBodyFatPercentage"

_SLEEP_STAGES = {
    "HKCategoryValueSleepAnalysisInBed": "in_bed",
    "HKCategoryValueSleepAnalysisAwake": "awake",
    "HKCategoryValueSleepAnalysisAsleep": "light",        # legacy (pre-iOS 16)
    "HKCategoryValueSleepAnalysisAsleepCore": "light",
    "HKCategoryValueSleepAnalysisAsleepDeep": "deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "rem",
}

_WORKOUT_ENERGY_STAT = "HKQuantityTypeIdentifierActiveEnergyBurned"
_WORKOUT_DISTANCE_STAT = "HKQuantityTypeIdentifierDistanceWalkingRunning"
_WORKOUT_DISTANCE_CYCLING = "HKQuantityTypeIdentifierDistanceCycling"
_WORKOUT_DISTANCE_SWIMMING = "HKQuantityTypeIdentifierDistanceSwimming"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_hk_date(val: str) -> datetime | None:
    """Parse HealthKit date strings like '2024-01-01 22:30:00 +0100'."""
    if not val:
        return None
    try:
        return datetime.strptime(val, "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            return None


def _duration_secs(start: datetime | None, end: datetime | None) -> int | None:
    if start and end:
        return max(0, int((end - start).total_seconds()))
    return None


def _short_hash(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()[:12]


def _strip_prefix(activity_type: str) -> str:
    return activity_type.replace("HKWorkoutActivityType", "")


# ---------------------------------------------------------------------------
# Sleep — group individual stage records into nightly sessions
# ---------------------------------------------------------------------------

def _process_sleep(
    records: list[ET.Element],
    user_id: int,
    conn: psycopg.Connection[dict[str, Any]],
) -> int:
    """Group sleep stage records into nightly sessions and upsert."""
    # Group by source + calendar date of end_time
    # Using the date on which sleep ended (morning) as the session date
    sessions: dict[str, dict] = defaultdict(lambda: {
        "start": None, "end": None,
        "in_bed_ms": 0, "awake_ms": 0, "light_ms": 0, "deep_ms": 0, "rem_ms": 0,
    })

    for rec in records:
        value = rec.get("value", "")
        stage = _SLEEP_STAGES.get(value)
        if stage is None:
            continue

        start = _parse_hk_date(rec.get("startDate", ""))
        end = _parse_hk_date(rec.get("endDate", ""))
        if not start or not end:
            continue

        duration_ms = int((end - start).total_seconds() * 1000)
        # Use end date as the session key (night-of)
        session_date = end.astimezone(timezone.utc).strftime("%Y-%m-%d")
        key = session_date

        s = sessions[key]
        if s["start"] is None or start < s["start"]:
            s["start"] = start
        if s["end"] is None or end > s["end"]:
            s["end"] = end

        if stage == "in_bed":
            s["in_bed_ms"] += duration_ms
        elif stage == "awake":
            s["awake_ms"] += duration_ms
        elif stage == "light":
            s["light_ms"] += duration_ms
        elif stage == "deep":
            s["deep_ms"] += duration_ms
        elif stage == "rem":
            s["rem_ms"] += duration_ms

    count = 0
    for session_date, s in sessions.items():
        start = s["start"]
        end = s["end"]
        external_id = _short_hash(f"apple_health_sleep_{session_date}")

        total_sleep_ms = s["light_ms"] + s["deep_ms"] + s["rem_ms"]
        in_bed_ms = s["in_bed_ms"] or (total_sleep_ms + s["awake_ms"]) or None

        existing = conn.execute(
            "SELECT id FROM sleep WHERE source = 'apple_health' AND external_id = %s AND user_id = %s",
            (external_id, user_id),
        ).fetchone()

        values = (
            session_date,
            False,
            None,
            start.isoformat() if start else None,
            end.isoformat() if end else None,
            in_bed_ms or None,
            s["awake_ms"] or None,
            s["light_ms"] or None,
            s["deep_ms"] or None,
            s["rem_ms"] or None,
            None,   # disturbance_count
            None,   # sleep_performance_percentage
            None,   # sleep_efficiency_percentage
            None,   # respiratory_rate
        )

        if existing:
            conn.execute(
                """
                UPDATE sleep
                SET date=%s, is_nap=%s, score_state=%s, start_time=%s, end_time=%s,
                    total_in_bed_time_milli=%s, total_awake_time_milli=%s,
                    total_light_sleep_milli=%s, total_slow_wave_sleep_milli=%s,
                    total_rem_sleep_milli=%s, disturbance_count=%s,
                    sleep_performance_percentage=%s, sleep_efficiency_percentage=%s,
                    respiratory_rate=%s
                WHERE source='apple_health' AND external_id=%s AND user_id=%s
                """,
                (*values, external_id, user_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO sleep
                    (user_id, external_id, date, source, is_nap, score_state,
                     start_time, end_time, total_in_bed_time_milli, total_awake_time_milli,
                     total_light_sleep_milli, total_slow_wave_sleep_milli, total_rem_sleep_milli,
                     disturbance_count, sleep_performance_percentage,
                     sleep_efficiency_percentage, respiratory_rate)
                VALUES (%s, %s, %s, 'apple_health', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id, external_id, *values),
            )
        count += 1

    return count


# ---------------------------------------------------------------------------
# Recovery (HRV + RHR) — one row per day
# ---------------------------------------------------------------------------

def _process_recovery(
    hrv_records: list[ET.Element],
    rhr_records: list[ET.Element],
    user_id: int,
    conn: psycopg.Connection[dict[str, Any]],
) -> int:
    # Aggregate to daily averages
    hrv_by_date: dict[str, list[float]] = defaultdict(list)
    for rec in hrv_records:
        dt = _parse_hk_date(rec.get("startDate", ""))
        if dt:
            date = dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
            try:
                hrv_by_date[date].append(float(rec.get("value", 0)))
            except ValueError:
                pass

    rhr_by_date: dict[str, list[float]] = defaultdict(list)
    for rec in rhr_records:
        dt = _parse_hk_date(rec.get("startDate", ""))
        if dt:
            date = dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
            try:
                rhr_by_date[date].append(float(rec.get("value", 0)))
            except ValueError:
                pass

    all_dates = set(hrv_by_date) | set(rhr_by_date)
    count = 0
    for date in all_dates:
        external_id = _short_hash(f"apple_health_recovery_{date}")
        avg_hrv = sum(hrv_by_date[date]) / len(hrv_by_date[date]) if hrv_by_date.get(date) else None
        avg_rhr = sum(rhr_by_date[date]) / len(rhr_by_date[date]) if rhr_by_date.get(date) else None

        existing = conn.execute(
            "SELECT id FROM recovery WHERE source = 'apple_health' AND external_id = %s AND user_id = %s",
            (external_id, user_id),
        ).fetchone()

        values = (date, None, None, avg_hrv, avg_rhr, None, None, None, None)

        if existing:
            conn.execute(
                """
                UPDATE recovery
                SET date=%s, score_state=%s, recovery_score=%s, hrv_rmssd_milli=%s,
                    resting_heart_rate=%s, spo2_percentage=%s, skin_temp_celsius=%s,
                    strain=%s, daily_energy_kcal=%s
                WHERE source='apple_health' AND external_id=%s AND user_id=%s
                """,
                (*values, external_id, user_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO recovery
                    (user_id, external_id, date, source, score_state, recovery_score,
                     hrv_rmssd_milli, resting_heart_rate, spo2_percentage,
                     skin_temp_celsius, strain, daily_energy_kcal)
                VALUES (%s, %s, %s, 'apple_health', %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id, external_id, *values),
            )
        count += 1

    return count


# ---------------------------------------------------------------------------
# Body measurements
# ---------------------------------------------------------------------------

def _process_body_measurements(
    mass_records: list[ET.Element],
    fat_records: list[ET.Element],
    user_id: int,
    conn: psycopg.Connection[dict[str, Any]],
) -> int:
    # Index fat percentage by date for joining with weight
    fat_by_date: dict[str, float] = {}
    for rec in fat_records:
        dt = _parse_hk_date(rec.get("startDate", ""))
        if dt:
            date = dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
            try:
                fat_by_date[date] = float(rec.get("value", 0)) * 100  # decimal → %
            except ValueError:
                pass

    count = 0
    for rec in mass_records:
        dt = _parse_hk_date(rec.get("startDate", ""))
        if not dt:
            continue

        date = dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
        external_id = _short_hash(f"apple_health_body_{rec.get('startDate', '')}")

        unit = rec.get("unit", "kg")
        try:
            raw_weight = float(rec.get("value", 0))
        except ValueError:
            continue

        weight_kg = raw_weight if unit == "kg" else round(raw_weight * 0.453592, 3)
        fat_ratio = fat_by_date.get(date)

        existing = conn.execute(
            "SELECT id FROM body_measurements WHERE source = 'apple_health' AND external_id = %s AND user_id = %s",
            (external_id, user_id),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE body_measurements
                SET measured_at=%s, date=%s, weight_kg=%s, fat_ratio=%s
                WHERE source='apple_health' AND external_id=%s AND user_id=%s
                """,
                (dt.isoformat(), date, weight_kg, fat_ratio, external_id, user_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO body_measurements
                    (user_id, external_id, measured_at, date, source, weight_kg, fat_ratio)
                VALUES (%s, %s, %s, %s, 'apple_health', %s, %s)
                """,
                (user_id, external_id, dt.isoformat(), date, weight_kg, fat_ratio),
            )
        count += 1

    return count


# ---------------------------------------------------------------------------
# Cardio workouts
# ---------------------------------------------------------------------------

def _process_workouts(
    workout_elements: list[ET.Element],
    user_id: int,
    conn: psycopg.Connection[dict[str, Any]],
) -> int:
    count = 0
    for workout in workout_elements:
        start = _parse_hk_date(workout.get("startDate", ""))
        end = _parse_hk_date(workout.get("endDate", ""))
        if not start:
            continue

        date = start.astimezone(timezone.utc).strftime("%Y-%m-%d")
        external_id = _short_hash(f"apple_health_workout_{workout.get('startDate', '')}")
        sport_name = _strip_prefix(workout.get("workoutActivityType", ""))
        activity_category = classify_activity(sport_name, "apple_health")

        # Duration: attribute is in minutes, convert to seconds
        try:
            duration_s = int(float(workout.get("duration", 0)) * 60)
        except ValueError:
            duration_s = _duration_secs(start, end)

        # Energy and distance from attributes (older exports) or WorkoutStatistics
        energy_kcal: float | None = None
        distance_m: float | None = None

        raw_energy = workout.get("totalEnergyBurned")
        if raw_energy:
            try:
                energy_kcal = float(raw_energy)
                if workout.get("totalEnergyBurnedUnit", "kcal").lower() == "kj":
                    energy_kcal /= 4.184
            except ValueError:
                pass

        raw_dist = workout.get("totalDistance")
        if raw_dist:
            try:
                d = float(raw_dist)
                unit = workout.get("totalDistanceUnit", "m").lower()
                distance_m = d if "m" in unit and "km" not in unit else d * 1000
            except ValueError:
                pass

        # WorkoutStatistics override attributes
        for stat in workout.findall("WorkoutStatistics"):
            stat_type = stat.get("type", "")
            if stat_type == _WORKOUT_ENERGY_STAT:
                try:
                    energy_kcal = float(stat.get("sum", 0))
                except ValueError:
                    pass
            elif stat_type in (_WORKOUT_DISTANCE_STAT, _WORKOUT_DISTANCE_CYCLING, _WORKOUT_DISTANCE_SWIMMING):
                try:
                    d = float(stat.get("sum", 0))
                    unit = stat.get("unit", "m").lower()
                    distance_m = d if unit == "m" else d * 1000
                except ValueError:
                    pass

        existing = conn.execute(
            "SELECT id FROM activities WHERE source = 'apple_health' AND external_id = %s AND user_id = %s",
            (external_id, user_id),
        ).fetchone()

        values = (
            date, sport_name, None, activity_category, None,
            start.isoformat() if start else None,
            end.isoformat() if end else None,
            duration_s, distance_m, None, energy_kcal,
            None, None, None, None, None, None, None, None,
        )

        if existing:
            conn.execute(
                """
                UPDATE activities
                SET date=%s, sport_name=%s, sport_id=%s, activity_category=%s,
                    score_state=%s, start_time=%s, end_time=%s, duration_seconds=%s,
                    distance_meters=%s, strain=%s, energy_kcal=%s,
                    avg_heart_rate=%s, max_heart_rate=%s,
                    zone_zero_milli=%s, zone_one_milli=%s, zone_two_milli=%s,
                    zone_three_milli=%s, zone_four_milli=%s, zone_five_milli=%s
                WHERE source='apple_health' AND external_id=%s AND user_id=%s
                """,
                (*values, external_id, user_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO activities
                    (user_id, source, external_id, date, sport_name, sport_id, activity_category,
                     score_state, start_time, end_time, duration_seconds, distance_meters,
                     strain, energy_kcal, avg_heart_rate, max_heart_rate,
                     zone_zero_milli, zone_one_milli, zone_two_milli,
                     zone_three_milli, zone_four_milli, zone_five_milli)
                VALUES (%s, 'apple_health', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id, external_id, *values),
            )
        count += 1

    return count


# ---------------------------------------------------------------------------
# Main sync function (called by API upload endpoint and CLI)
# ---------------------------------------------------------------------------

def sync_apple_health_xml(
    content: bytes,
    user_id: int,
    conn: psycopg.Connection[dict[str, Any]],
) -> dict[str, int]:
    """Parse Apple Health export.xml and upsert all supported data types.

    Returns a dict of {data_type: row_count}.
    """
    root = ET.fromstring(content)

    # Bucket records by type for a single pass
    sleep_recs: list[ET.Element] = []
    hrv_recs: list[ET.Element] = []
    rhr_recs: list[ET.Element] = []
    mass_recs: list[ET.Element] = []
    fat_recs: list[ET.Element] = []
    workout_elements: list[ET.Element] = []

    for elem in root:
        tag = elem.tag
        if tag == "Record":
            t = elem.get("type", "")
            if t == _SLEEP_TYPE:
                sleep_recs.append(elem)
            elif t == _HRV_TYPE:
                hrv_recs.append(elem)
            elif t == _RHR_TYPE:
                rhr_recs.append(elem)
            elif t == _BODY_MASS_TYPE:
                mass_recs.append(elem)
            elif t == _BODY_FAT_TYPE:
                fat_recs.append(elem)
        elif tag == "Workout":
            workout_elements.append(elem)

    counts = {
        "sleep": _process_sleep(sleep_recs, user_id, conn),
        "recovery": _process_recovery(hrv_recs, rhr_recs, user_id, conn),
        "body_measurements": _process_body_measurements(mass_recs, fat_recs, user_id, conn),
        "activities": _process_workouts(workout_elements, user_id, conn),
    }
    return counts


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m sync.apple_health path/to/export.xml")
        sys.exit(1)

    init_db()
    user_id = get_request_user_id()
    content = Path(sys.argv[1]).read_bytes()

    with get_connection() as conn:
        counts = sync_apple_health_xml(content, user_id, conn)
        conn.commit()

    print("Apple Health sync complete:")
    for domain, n in counts.items():
        print(f"  {domain}: {n} rows")


if __name__ == "__main__":
    set_current_user_id(get_cli_user_id())
    main()
