"""Dehumidifier drying-rate forecast: pure helpers, no Home Assistant dependency."""

from __future__ import annotations

import math

RH_FLOOR = 30.0  # RH % a household dehumidifier cannot dry below; the decay tends to it
# First-order rate [1/h] per fan level (low, medium, high) until the unit has been observed.
DEFAULT_K = (0.25, 0.35, 0.5)
K_MAX = 2.0  # faster than this is sensor noise, not drying
MAX_MINUTES = 720.0  # beyond 12 h the answer is "not reachable"
# shortcut: heat estimate uses generic room constants (no volume/insulation known); upgrade by learning them.
HEAT_UA_W_PER_K = 100.0  # room + leakage to the rest of the house
HEAT_C_J_PER_K = 150_000.0  # air + furnishings of a small room


def minutes_to_target(rh: float, target: float, k_per_h: float) -> float | None:
    """Minutes for dRH/dt = -k (RH - floor) to fall from rh to target; 0 if already there."""
    if rh <= target:
        return 0.0
    if target <= RH_FLOOR or k_per_h <= 0:
        return None
    minutes = 60.0 * math.log((rh - RH_FLOOR) / (target - RH_FLOOR)) / k_per_h
    return round(minutes) if minutes <= MAX_MINUTES else None


def heat_gain_c(heat_w: float, minutes: float | None) -> float:
    """Room warming from the unit's heat output, with losses; steady state when no finite ETA."""
    steady = heat_w / HEAT_UA_W_PER_K
    if minutes is None:
        return round(steady, 1)
    return round(steady * (1 - math.exp(-minutes * 60 * HEAT_UA_W_PER_K / HEAT_C_J_PER_K)), 1)


def observed_k(rh_start: float, rh_end: float, hours: float) -> float | None:
    """Rate implied by two readings, or None when they cannot be trusted."""
    if hours <= 0 or rh_start <= RH_FLOOR + 2 or rh_end <= RH_FLOOR:
        return None
    k = math.log((rh_start - RH_FLOOR) / (rh_end - RH_FLOOR)) / hours
    return k if 0 < k <= K_MAX else None
