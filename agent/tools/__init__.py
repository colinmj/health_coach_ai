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
from agent.tools.nutrition import get_nutrition
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
)

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
]


def build_tools(source_map: dict[str, str] = DEFAULT_SOURCES) -> list:
    """Return tools whose required domains and sources are satisfied by source_map."""
    active_domains = set(source_map.keys())
    return [
        tool_fn
        for tool_fn, required_domains, required_sources in TOOL_REGISTRY
        if required_domains.issubset(active_domains)
        and all(source_map.get(domain) == source for domain, source in required_sources.items())
    ]


# Default: all tools (single-user local mode)
TOOLS = build_tools()
