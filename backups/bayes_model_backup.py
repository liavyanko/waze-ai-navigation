"""
Bayesian/Heuristic traffic multiplier model
-------------------------------------------
We attempt to use pgmpy if available. If not, we fall back to a deterministic
weighted-heuristic model. Public API remains:
- predict_travel_multiplier(...)-> float
- predict_travel_with_details(...)-> dict
"""

from typing import Dict, Any
import logging

try:
    from pgmpy.models import DiscreteBayesianNetwork
    from pgmpy.factors.discrete import TabularCPD
    from pgmpy.inference import VariableElimination
    _PGMPY_AVAILABLE = True
except Exception:
    _PGMPY_AVAILABLE = False

from config import MULTIPLIER_WEIGHTS

# --- Heuristic tables ---
_WEATHER_W = {
    "clear": 0.00,
    "cloudy": 0.03,
    "rain": 0.12,
    "storm": 0.25,
    "snow": 0.35,
}
_TIME_W = {
    "night": -0.05,
    "morning_peak": 0.20,
    "midday": 0.00,
    "evening_peak": 0.22,
}
_DAY_W = {
    "weekday": 0.06,
    "weekend": -0.04,
    "holiday": 0.10,
}
_ROAD_W = {
    "none": 0.00,
    "accident": 0.30,
    "construction": 0.18,
    "closure": 0.45,
}
_POLICE_W = {"low": 0.00, "medium": 0.03, "high": 0.06}
_DRIVE_W = {"calm": -0.03, "normal": 0.00, "aggressive": 0.05}


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _heuristic_multiplier(inputs: Dict[str, str]) -> Dict[str, Any]:
    contribs = {
        "weather": _WEATHER_W.get(inputs["weather"], 0.0),
        "time_of_day": _TIME_W.get(inputs["time_of_day"], 0.0),
        "day_type": _DAY_W.get(inputs["day_type"], 0.0),
        "road_problem": _ROAD_W.get(inputs["road_problem"], 0.0),
        "police_activity": _POLICE_W.get(inputs["police_activity"], 0.0),
        "driving_history": _DRIVE_W.get(inputs["driving_history"], 0.0),
    }
    score = sum(contribs.values())
    multiplier = round(_clip(1.0 + score, 0.7, 3.0), 2)

    rows = [
        {
            "factor": k,
            "value": inputs[k],
            "weight": round(v, 3),
            "contribution": round(v, 3),
        }
        for k, v in contribs.items()
    ]

    # Simple marginals explanation bucketized by score
    if score < 0.02:
        traffic = "light"
        cond = "good"
        route_bias = "shortest"
    elif score < 0.25:
        traffic = "moderate"
        cond = "mixed"
        route_bias = "balanced"
    else:
        traffic = "heavy"
        cond = "bad"
        route_bias = "fastest"

    marginals = {
        "traffic": {"top": traffic, "dist": {"light": 0.2, "moderate": 0.4, "heavy": 0.4}},
        "conditions_severity": {"top": cond, "dist": {"good": 0.3, "mixed": 0.4, "bad": 0.3}},
        "route_choice": {"top": "main_roads", "dist": {"main_roads": 0.7, "shortcuts": 0.3}},
        "route_bias": {"top": route_bias, "dist": {"shortest": 0.3, "balanced": 0.4, "fastest": 0.3}},
    }

    return {"multiplier": multiplier, "rows": rows, "marginals": marginals}


def predict_travel_with_details(
    weather: str,
    time_of_day: str,
    day_type: str,
    road_problem: str,
    police_activity: str,
    driving_history: str,
) -> Dict[str, Any]:
    """
    Returns:
      {"multiplier": float, "rows": list[dict], "marginals": dict}
    """
    inputs = {
        "weather": weather,
        "time_of_day": time_of_day,
        "day_type": day_type,
        "road_problem": road_problem,
        "police_activity": police_activity,
        "driving_history": driving_history,
    }

    # For this MVP we use the heuristic always; pgmpy path can be added later
    try:
        return _heuristic_multiplier(inputs)
    except Exception as e:
        logging.error(f"Multiplier computation failed; returning neutral. Error={e}")
        return {"multiplier": 1.0, "rows": [], "marginals": {}}


def predict_travel_multiplier(
    weather: str,
    time_of_day: str,
    day_type: str,
    road_problem: str,
    police_activity: str,
    driving_history: str,
) -> float:
    return predict_travel_with_details(
        weather, time_of_day, day_type, road_problem, police_activity, driving_history
    )["multiplier"]
