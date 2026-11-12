"""Small, deterministic helpers for RoomMind comfort features."""

from __future__ import annotations

from typing import Any

from ..const import MOLD_SURFACE_RH_EARLY

HUMIDITY_FALLBACK_LIMIT = 60.0  # RH % above which air counts as damp when no humidity target is set

DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    "work": {"heat_target": 21.0, "cool_target": 25.0, "humidity_target": 55.0, "fan_mode": "auto"},
    "sleep": {"heat_target": 19.5, "cool_target": 26.0, "humidity_target": 55.0, "fan_mode": "low"},
    "guests": {"heat_target": 21.5, "cool_target": 24.5, "humidity_target": 50.0, "fan_mode": "auto"},
    "away": {"heat_target": 17.0, "cool_target": 28.0, "humidity_target": 60.0, "fan_mode": "low"},
}
_PROFILE_TARGET_KEYS = ("heat_target", "cool_target", "humidity_target")


def _effective_profiles(room: dict) -> dict[str, dict[str, Any]]:
    """Return the default profiles merged with the room's customisations."""
    profiles = {key: dict(value) for key, value in DEFAULT_PROFILES.items()}
    for key, value in (room.get("comfort_profiles") or {}).items():
        if isinstance(value, dict):
            profiles[key] = {**profiles.get(key, {}), **value}
    return profiles


def active_profile(room: dict) -> dict[str, Any] | None:
    """Return the selected profile, including safe defaults for old rooms."""
    profile_id = room.get("active_profile", "")
    if not profile_id:
        return None
    profile = _effective_profiles(room).get(profile_id)
    return profile if isinstance(profile, dict) else None


def profile_targets(room: dict) -> dict[str, dict[str, float]]:
    """Return the numeric targets each built-in profile applies to this room."""
    return {
        profile_id: {key: profile[key] for key in _PROFILE_TARGET_KEYS if key in profile}
        for profile_id, profile in _effective_profiles(room).items()
        if profile_id in DEFAULT_PROFILES
    }


def calculate_comfort_score(
    *,
    current_temp: float | None,
    heat_target: float | None,
    cool_target: float | None,
    humidity: float | None,
    humidity_target: float | None,
    window_open: bool,
    mold_risk_level: str | None,
    anomalies: list[dict[str, str]] | None = None,
    mold_surface_rh: float | None = None,
) -> dict[str, Any]:
    """Score a room from 0 to 100 using only available measurements."""
    score = 100.0
    factors: dict[str, int] = {}
    breakdown: dict[str, dict[str, int | str]] = {}
    if current_temp is None:
        penalty = 25
        score -= penalty
        factors["temperature"] = 0
        breakdown["temperature"] = {"penalty": penalty, "status": "unavailable"}
    else:
        distance = 0.0
        status = "on_target"
        if heat_target is not None and current_temp < heat_target:
            distance = heat_target - current_temp
            status = "below_target"
        elif cool_target is not None and current_temp > cool_target:
            distance = current_temp - cool_target
            status = "above_target"
        penalty = min(45, round(distance * 18))
        score -= penalty
        factors["temperature"] = 100 - penalty
        breakdown["temperature"] = {"penalty": penalty, "status": status}
    if humidity is not None and humidity_target is not None:
        penalty = min(25, round(abs(humidity - humidity_target) * 2.5))
        score -= penalty
        factors["humidity"] = 100 - penalty
        breakdown["humidity"] = {
            "penalty": penalty,
            "status": "below_target"
            if humidity < humidity_target
            else "above_target"
            if humidity > humidity_target
            else "on_target",
        }
    elif humidity is not None and humidity > HUMIDITY_FALLBACK_LIMIT:
        # No comfort target: still penalise clearly damp air.
        penalty = min(25, round((humidity - HUMIDITY_FALLBACK_LIMIT) * 2.5))
        score -= penalty
        factors["humidity"] = 100 - penalty
        breakdown["humidity"] = {"penalty": penalty, "status": "above_target"}
    else:
        breakdown["humidity"] = {"penalty": 0, "status": "unavailable"}
    if window_open:
        score -= 15
        factors["window"] = 0
    breakdown["window"] = {"penalty": 15 if window_open else 0, "status": "open" if window_open else "closed"}
    risk_penalty = {"warning": 10, "critical": 25}.get(mold_risk_level or "", 0)
    status = mold_risk_level or "ok"
    if not risk_penalty and mold_surface_rh is not None and mold_surface_rh >= MOLD_SURFACE_RH_EARLY:
        risk_penalty, status = 5, "elevated"  # walls approaching warning, before the level flips
    score -= risk_penalty
    if risk_penalty:
        factors["air_quality"] = 100 - risk_penalty
    breakdown["air_quality"] = {"penalty": risk_penalty, "status": status}
    anomaly_penalty = min(20, 5 * len(anomalies or []))
    score -= anomaly_penalty
    breakdown["anomalies"] = {"penalty": anomaly_penalty, "status": "active" if anomaly_penalty else "none"}
    return {
        "score": max(0, min(100, round(score))),
        "label": "excellent" if score >= 85 else "good" if score >= 70 else "fair" if score >= 50 else "poor",
        "factors": factors,
        "breakdown": breakdown,
    }


def energy_suggestions(
    *,
    heating_minutes: float,
    cooling_minutes: float,
    target_error_c: float | None,
    has_power_sensor: bool,
) -> list[str]:
    """Return concise, evidence-based energy suggestions for one room."""
    suggestions: list[str] = []
    if not has_power_sensor:
        suggestions.append("Aggiungi un sensore di potenza per misurare consumi e costi reali.")
    if heating_minutes + cooling_minutes >= 8 * 60:
        suggestions.append("Molte ore di climatizzazione: prova un profilo Eco o un setpoint meno estremo.")
    if target_error_c is not None and abs(target_error_c) >= 1.5:
        suggestions.append(
            "Il setpoint viene raggiunto con difficolta: controlla finestre, sensore e potenza del climatizzatore."
        )
    return suggestions
