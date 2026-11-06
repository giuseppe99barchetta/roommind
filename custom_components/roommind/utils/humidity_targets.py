"""Room humidity targets, including optional per-season values."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .comfort_insights import active_profile

SEASONS = ("winter", "spring", "summer", "autumn")
SEASON_ENTITY = "sensor.season"
DEFAULT_HUMIDITY_TARGET = 55.0
_NORTHERN_MONTHS = {
    12: "winter",
    1: "winter",
    2: "winter",
    3: "spring",
    4: "spring",
    5: "spring",
    6: "summer",
    7: "summer",
    8: "summer",
    9: "autumn",
    10: "autumn",
    11: "autumn",
}
_OPPOSITE = {"winter": "summer", "summer": "winter", "spring": "autumn", "autumn": "spring"}


def current_season(hass: HomeAssistant, now: datetime | None = None) -> str:
    """Use HA's Season sensor when present, otherwise meteorological seasons."""
    state = hass.states.get(SEASON_ENTITY)
    if state is not None and state.state in SEASONS:
        return str(state.state)
    month = (now or dt_util.now()).month
    season = _NORTHERN_MONTHS[month]
    latitude = getattr(getattr(hass, "config", None), "latitude", None)
    southern = isinstance(latitude, (int, float)) and latitude < 0
    return _OPPOSITE[season] if southern else season


def _valid(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and 0 <= number <= 100 else None


def room_humidity_target(room: dict, season: str | None = None) -> float | None:
    """Return the active target: profile, then season, then the room default.

    ``None`` means humidity comfort is off for the room.
    """
    if not room.get("humidity_comfort_enabled", False):
        return None
    profile = active_profile(room)
    if profile:
        return _valid(profile.get("humidity_target"))
    if season:
        seasonal = _valid((room.get("humidity_season_targets") or {}).get(season))
        if seasonal is not None:
            return seasonal
    return _valid(room.get("humidity_target", DEFAULT_HUMIDITY_TARGET))
