import copy as _copy
import json as _json

from agent.tools._config import DEFAULT_SOURCES
from agent.tools.strength import (
    get_exercise_prs,
    get_workout_1rm_history,
    get_workout_performance,
    get_exercise_list,
)
from agent.tools.recovery import (
    list_activity_sports,
    get_activities,
    get_recovery,
    get_sleep,
)
from agent.tools.body_composition import get_body_composition
from agent.tools.nutrition import get_food_entries, get_nutrition
from agent.tools.correlations import (
    get_hrv_vs_performance,
    get_sleep_vs_performance,
    get_sleep_threshold_vs_performance,
    get_body_composition_vs_strength,
    get_nutrition_vs_performance,
    get_protein_vs_strength,
    get_carbs_prior_to_prs,
    get_nutrition_vs_recovery,
    get_nutrition_vs_activity,
    get_activity_vs_strength,
    get_nutrition_vs_body_composition,
    get_energy_balance_vs_weight,
)
from agent.tools.goals import (
    create_goal,
    get_goals,
    save_insight,
    get_insights,
    check_compliance,
    update_goal_status,
    assess_protocol,
    update_action,
    update_training_iq,
)
from agent.tools.analyze_correlation import analyze_correlation
from agent.tools.analyze_multi_correlation import analyze_multi_correlation
from agent.tools.bloodwork import get_biomarkers
from agent.tools.food_correlations import (
    get_food_vs_performance,
    get_food_vs_sleep,
    get_food_vs_recovery,
    get_food_vs_body_composition,
)
from agent.tools.performance_drivers import get_performance_drivers
from agent.tools.knowledge import search_health_knowledge
from agent.tools.form_analysis import get_form_analyses

def _cap_tool_output(result: str, max_rows: int = 150, max_chars: int = 6000) -> str:
    """Truncate large tool results to keep input tokens under control."""
    try:
        data = _json.loads(result)
    except (ValueError, TypeError):
        return result[:max_chars] if len(result) > max_chars else result
    if isinstance(data, list) and len(data) > max_rows:
        data = data[:max_rows]
        out = _json.dumps(data, default=str)
        return out + f'\n[Note: result truncated to {max_rows} rows]'
    serialised = _json.dumps(data, default=str)
    if len(serialised) > max_chars:
        return serialised[:max_chars] + '\n[Note: result truncated]'
    return serialised


TOOL_REGISTRY: list[tuple] = [
    # (tool_fn,                          required_domains,              required_sources)
    (get_exercise_prs,                   {"strength"},                  {"strength": "hevy"}),
    (get_workout_1rm_history,            {"strength"},                  {"strength": "hevy"}),
    (get_workout_performance,            {"strength"},                  {"strength": "hevy"}),
    (get_exercise_list,                  {"strength"},                  {"strength": "hevy"}),
    (list_activity_sports,               {"recovery"},                  {}),
    (get_activities,                     {"recovery"},                  {}),
    (get_recovery,                       {"recovery"},                  {}),
    (get_sleep,                          {"recovery"},                  {}),
    (get_body_composition,               {"body_composition"},          {}),
    (get_nutrition,                      {"nutrition"},                 {}),
    (get_food_entries,                   {"nutrition"},                 {}),
    (get_hrv_vs_performance,             {"recovery", "strength"},      {"strength": "hevy"}),
    (get_sleep_vs_performance,           {"recovery", "strength"},      {"strength": "hevy"}),
    (get_sleep_threshold_vs_performance, {"recovery", "strength"},      {"strength": "hevy"}),
    (get_body_composition_vs_strength,   {"body_composition", "strength"}, {"strength": "hevy"}),
    (get_nutrition_vs_performance,       {"nutrition", "strength"},     {"strength": "hevy"}),
    (get_protein_vs_strength,            {"nutrition", "strength"},     {"strength": "hevy"}),
    (get_carbs_prior_to_prs,             {"nutrition", "strength"},     {"strength": "hevy"}),
    (get_nutrition_vs_recovery,          {"nutrition", "recovery"},     {}),
    (get_nutrition_vs_activity,          {"nutrition", "recovery"},     {}),
    (get_activity_vs_strength,           {"recovery", "strength"},      {"strength": "hevy"}),
    (get_nutrition_vs_body_composition,  {"nutrition", "body_composition"}, {}),
    (get_energy_balance_vs_weight,       {"nutrition", "recovery", "body_composition"}, {}),
    (create_goal,                        set(),                         {}),
    (get_goals,                          set(),                         {}),
    (save_insight,                       set(),                         {}),
    (get_insights,                       set(),                         {}),
    (check_compliance,                   set(),                         {}),
    (update_goal_status,                 set(),                         {}),
    (assess_protocol,                    set(),                         {}),
    (update_action,                      set(),                         {}),
    (update_training_iq,                 set(),                         {}),
    (analyze_correlation,                set(),                         {}),
    (analyze_multi_correlation,          set(),                         {}),
    (get_biomarkers,                     {"bloodwork"},                 {}),
    (get_food_vs_performance,            {"nutrition", "strength"},     {"strength": "hevy"}),
    (get_food_vs_sleep,                  {"nutrition", "recovery"},     {}),
    (get_food_vs_recovery,               {"nutrition", "recovery"},     {}),
    (get_food_vs_body_composition,       {"nutrition", "body_composition"}, {}),
    (get_performance_drivers,            {"strength", "recovery"},          {"strength": "hevy"}),
    (search_health_knowledge,            set(),                             {}),
    (get_form_analyses,                  set(),                             {}),
]


def build_tools(source_map: dict[str, str] = DEFAULT_SOURCES) -> list:
    """Return tools whose required domains and sources are satisfied by source_map."""
    active_domains = set(source_map.keys())
    tools = []
    for tool_fn, required_domains, required_sources in TOOL_REGISTRY:
        if (required_domains.issubset(active_domains)
                and all(source_map.get(domain) == source for domain, source in required_sources.items())):
            orig = tool_fn.func
            wrapped = _copy.copy(tool_fn)
            wrapped.func = lambda *a, _orig=orig, **kw: _cap_tool_output(_orig(*a, **kw))
            tools.append(wrapped)
    return tools


# Default: all tools (single-user local mode)
TOOLS = build_tools()
