import json

from langchain_core.tools import tool

import analytics.whoop as whoop


@tool
def list_activity_sports(since: str = "", until: str = "") -> str:
    """Return the distinct sports the user has logged on Whoop, with session counts and averages.
    Use this first to discover available sport names before calling get_activities.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: sport_name, session_count, first_session, last_session,
    avg_strain, avg_energy_kcal."""
    return json.dumps(whoop.list_activity_sports(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_activities(sport_name: str = "", since: str = "", until: str = "") -> str:
    """Return Whoop activity sessions, optionally filtered by sport name and date range.
    sport_name is matched case-insensitively — e.g. 'hockey' matches 'Ice Hockey'.
    Leave sport_name blank to get all activities across all sports.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: date, sport_name, strain, avg_heart_rate, max_heart_rate,
    energy_kcal, zone_zero_milli through zone_five_milli."""
    return json.dumps(whoop.get_activities(
        sport_name=sport_name.strip() or None,
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_recovery(since: str = "", until: str = "") -> str:
    """Return Whoop recovery scores and HRV data.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list of records with fields: date, recovery_score, hrv_rmssd_milli,
    resting_heart_rate, spo2_percentage, skin_temp_celsius, strain, daily_energy_kcal."""
    return json.dumps(whoop.get_recovery(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_sleep(since: str = "", until: str = "", exclude_naps: bool = True) -> str:
    """Return Whoop sleep performance and architecture data.
    since/until are optional YYYY-MM-DD strings. exclude_naps defaults to True.
    Returns a JSON list of records with fields: date, sleep_performance_percentage,
    sleep_efficiency_percentage, total_rem_sleep_milli, total_slow_wave_sleep_milli,
    total_in_bed_time_milli, respiratory_rate."""
    return json.dumps(whoop.get_sleep(
        since=since.strip() or None,
        until=until.strip() or None,
        exclude_naps=exclude_naps,
    ))
