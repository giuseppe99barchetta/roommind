"""Small, deterministic helpers for RoomMind comfort features."""

from __future__ import annotations

from typing import Any

DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    "work": {"label": "Lavoro", "heat_target": 21.0, "cool_target": 25.0, "humidity_target": 55.0, "fan_mode": "auto"},
    "sleep": {"label": "Sonno", "heat_target": 19.5, "cool_target": 26.0, "humidity_target": 55.0, "fan_mode": "low"},
    "guests": {"label": "Ospiti", "heat_target": 21.5, "cool_target": 24.5, "humidity_target": 50.0, "fan_mode": "auto"},
    "away": {"label": "Assente", "heat_target": 17.0, "cool_target": 28.0, "humidity_target": 60.0, "fan_mode": "low"},
}


def active_profile(room: dict) -> dict[str, Any] | None:
    """Return the selected profile, including safe defaults for old rooms."""
    profile_id = room.get("active_profile", "")
    if not profile_id:
        return None
    profiles = {key: dict(value) for key, value in DEFAULT_PROFILES.items()}
    for key, value in (room.get("comfort_profiles") or {}).items():
        if isinstance(value, dict):
            profiles[key] = {**profiles.get(key, {}), **value}
    profile = profiles.get(profile_id)
    return profile if isinstance(profile, dict) else None


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
            "status": "below_target" if humidity < humidity_target else "above_target" if humidity > humidity_target else "on_target",
        }
    else:
        breakdown["humidity"] = {"penalty": 0, "status": "unavailable"}
    if window_open:
        score -= 15
        factors["window"] = 0
    breakdown["window"] = {"penalty": 15 if window_open else 0, "status": "open" if window_open else "closed"}
    risk_penalty = {"warning": 10, "critical": 25}.get(mold_risk_level or "", 0)
    score -= risk_penalty
    if risk_penalty:
        factors["air_quality"] = 100 - risk_penalty
    breakdown["air_quality"] = {"penalty": risk_penalty, "status": mold_risk_level or "ok"}
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
        suggestions.append("Il setpoint viene raggiunto con difficolta: controlla finestre, sensore e potenza del climatizzatore.")
    return suggestions
