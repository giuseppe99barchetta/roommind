"""Mold risk detection utilities.

Calculates mold risk based on indoor temperature, humidity, and outdoor
temperature using building-physics methods (DIN 4108-2, ISO 13788).

The core approach: estimate the coldest wall surface temperature using the
temperature factor f_Rsi (default 0.80 for standard existing buildings), then compute
the relative humidity at that surface from the dew point.  Mold growth becomes
likely when surface RH exceeds ~80 %.
"""

from __future__ import annotations

import math

from ..const import (
    AIRING_ABS_HUMIDITY_OFF,
    AIRING_ABS_HUMIDITY_ON,
    AIRING_MIN_INDOOR_RH,
    DEFAULT_MOLD_F_RSI,
    DEFAULT_MOLD_PREVENTION_DRY_MIN_TEMPERATURE,
    MIN_MOLD_GROWTH_TEMP,
    MOLD_PREVENTION_DELTAS,
    MOLD_RISK_CRITICAL,
    MOLD_RISK_OK,
    MOLD_RISK_WARNING,
    MOLD_SURFACE_RH_CRITICAL,
    MOLD_SURFACE_RH_EARLY,
    MOLD_SURFACE_RH_WARNING,
)

# Magnus formula constants (Alduchov & Eskridge 1996, widely used approximation)
_A = 17.271
_B = 237.7  # °C


def dew_point(temp: float, rh: float) -> float:
    """Calculate dew point temperature using the Magnus formula.

    Args:
        temp: Air temperature in °C.
        rh: Relative humidity in % (0-100).

    Returns:
        Dew point temperature in °C.
    """
    rh_clamped = max(1.0, min(rh, 100.0))
    gamma = (_A * temp) / (_B + temp) + math.log(rh_clamped / 100.0)
    return (_B * gamma) / (_A - gamma)


def surface_rh(t_dew: float, t_surface: float) -> float:
    """Calculate relative humidity at a surface.

    Args:
        t_dew: Dew point temperature in °C.
        t_surface: Surface temperature in °C.

    Returns:
        Estimated surface relative humidity in % (clamped to 0-100).
    """
    e_dew = math.exp((_A * t_dew) / (_B + t_dew))
    e_surface = math.exp((_A * t_surface) / (_B + t_surface))
    return min(100.0, max(0.0, 100.0 * e_dew / e_surface))


def estimate_surface_temp(
    t_room: float,
    t_outdoor: float,
    f_rsi: float = 0.80,
) -> float:
    """Estimate coldest wall surface temperature using temperature factor.

    Based on DIN 4108-2.  f_Rsi = 0.80 is a realistic value for standard
    existing buildings (DIN minimum is 0.70, modern buildings 0.85+).

    Args:
        t_room: Indoor air temperature in °C.
        t_outdoor: Outdoor temperature in °C.
        f_rsi: Temperature factor (0-1).  Higher = better insulated.

    Returns:
        Estimated surface temperature in °C.
    """
    return t_outdoor + f_rsi * (t_room - t_outdoor)


def calculate_mold_risk(
    t_room: float,
    rh_room: float,
    t_outdoor: float | None,
    f_rsi: float = DEFAULT_MOLD_F_RSI,
) -> tuple[str, float]:
    """Calculate mold risk level and estimated surface RH.

    Uses the full dew-point / surface-temperature method when *t_outdoor* is
    available, otherwise falls back to a conservative room-air-RH assessment.

    Args:
        t_room: Indoor air temperature in °C.
        rh_room: Indoor relative humidity in % (0-100).
        t_outdoor: Outdoor temperature in °C, or None if unavailable.
        f_rsi: Temperature factor of the room's coldest wall spot.

    Returns:
        Tuple of (risk_level, surface_rh_percent).
        risk_level is one of MOLD_RISK_OK / MOLD_RISK_WARNING / MOLD_RISK_CRITICAL.
    """
    if t_outdoor is not None:
        t_surface = estimate_surface_temp(t_room, t_outdoor, f_rsi)

        # Below MIN_MOLD_GROWTH_TEMP mold growth is negligible
        if t_surface < MIN_MOLD_GROWTH_TEMP:
            return MOLD_RISK_OK, 0.0

        t_dew = dew_point(t_room, rh_room)
        srh = surface_rh(t_dew, t_surface)
    else:
        # Fallback: no outdoor temp → use room air RH with conservative offsets.
        # Typical wall surface is 3-5 °C colder → surface RH is ~10-15 % higher
        # than room air RH.  We approximate by shifting thresholds down.
        srh = rh_room + 10.0  # conservative estimate

    return _risk_from_surface_rh(srh), round(srh, 1)


def _risk_from_surface_rh(srh: float) -> str:
    """Map surface RH to risk level."""
    if srh >= MOLD_SURFACE_RH_CRITICAL:
        return MOLD_RISK_CRITICAL
    if srh >= MOLD_SURFACE_RH_WARNING:
        return MOLD_RISK_WARNING
    return MOLD_RISK_OK


def mold_exposure_hours(
    rows: list[dict],
    f_rsi: float = DEFAULT_MOLD_F_RSI,
    max_gap_seconds: float = 15 * 60,
) -> float:
    """Hours with estimated surface RH at or above the critical 80 %.

    *rows* are RoomMind history rows (timestamp, room_temp, current_humidity,
    outdoor_temp).  Each sample counts until the next one, capped at
    *max_gap_seconds* so outages are not counted as exposure.
    """
    samples = []
    for row in rows:
        try:
            ts = float(row["timestamp"])
            t_room = float(row["room_temp"])
            rh = float(row["current_humidity"])
        except (KeyError, TypeError, ValueError):
            continue
        try:
            t_out: float | None = float(row.get("outdoor_temp"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            t_out = None
        samples.append((ts, t_room, rh, t_out))
    samples.sort()
    seconds = 0.0
    for current, following in zip(samples, samples[1:], strict=False):
        ts, t_room, rh, t_out = current
        if calculate_mold_risk(t_room, rh, t_out, f_rsi)[1] >= MOLD_SURFACE_RH_CRITICAL:
            seconds += min(following[0] - ts, max_gap_seconds)
    return round(seconds / 3600, 1)


def absolute_humidity(temp: float, rh: float) -> float:
    """Return water vapour density in g/m³ (Magnus saturation pressure)."""
    e_sat = 6.112 * math.exp((_A * temp) / (_B + temp))  # hPa
    return 216.7 * (max(0.0, min(rh, 100.0)) / 100.0) * e_sat / (273.15 + temp)


def airing_recommended(
    t_room: float | None,
    rh_room: float | None,
    t_outdoor: float | None,
    rh_outdoor: float | None,
    surface_rh: float | None,
    was_recommended: bool = False,
) -> bool:
    """Return True when opening windows would remove indoor moisture.

    Relative humidity cannot be compared across temperatures: cold outdoor
    air at 90 % usually holds far less water than warm indoor air at 60 %.
    Airing is suggested only when there is moisture worth removing, the
    outdoor air is clearly drier in absolute terms and not warmer than the
    room.  A hysteresis band avoids flapping on sensor noise.
    """
    if None in (t_room, rh_room, t_outdoor, rh_outdoor):
        return False
    humid = rh_room >= AIRING_MIN_INDOOR_RH or (surface_rh or 0.0) >= MOLD_SURFACE_RH_EARLY
    if not humid or t_outdoor >= t_room:
        return False
    gap = absolute_humidity(t_room, rh_room) - absolute_humidity(t_outdoor, rh_outdoor)
    return gap >= (AIRING_ABS_HUMIDITY_OFF if was_recommended else AIRING_ABS_HUMIDITY_ON)


def dry_start_temperature(settings: dict) -> float:
    """Room temperature from which mold-prevention DRY may start."""
    return max(
        DEFAULT_MOLD_PREVENTION_DRY_MIN_TEMPERATURE,
        float(settings.get("mold_prevention_dry_min_temperature", DEFAULT_MOLD_PREVENTION_DRY_MIN_TEMPERATURE)),
    )


def mold_prevention_delta(intensity: str) -> float:
    """Return temperature-raise delta for a prevention intensity level.

    Args:
        intensity: One of "light", "medium", "strong".

    Returns:
        Temperature increase in °C.
    """
    return MOLD_PREVENTION_DELTAS.get(intensity, 2.0)
