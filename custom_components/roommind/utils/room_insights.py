"""Small, presentation-ready explanations of RoomMind room state."""

from __future__ import annotations


def build_room_readiness(room: dict, settings: dict, outdoor_available: bool) -> dict:
    """Return a non-blocking setup checklist for one room."""
    devices = room.get("devices", []) or room.get("thermostats", []) or room.get("acs", [])
    has_devices = bool(devices)
    has_sensor = bool(room.get("temperature_sensor"))
    has_schedule = bool(room.get("schedules"))
    is_outdoor = bool(room.get("is_outdoor", False))
    climate_enabled = room.get("climate_control_enabled", True) and settings.get("climate_control_active", True)

    items = [
        {"key": "devices", "status": "ready" if has_devices else "missing"},
        {"key": "temperature_sensor", "status": "ready" if has_sensor else "recommended"},
        {"key": "schedule", "status": "ready" if has_schedule else "recommended"},
    ]
    if not is_outdoor:
        items.append(
            {"key": "predictive_control", "status": "ready" if has_sensor and outdoor_available else "recommended"}
        )
    if not climate_enabled:
        items.append({"key": "climate_control", "status": "missing"})

    if not has_devices or not climate_enabled:
        level = "needs_setup"
    elif has_sensor and outdoor_available:
        level = "ready"
    else:
        level = "basic"
    return {
        "level": level,
        "items": items,
        "ready_count": sum(item["status"] == "ready" for item in items),
        "total_count": len(items),
    }


def build_decision_reasons(live: dict) -> list[str]:
    """Build ordered machine-readable reasons for the current room action."""
    reasons: list[str] = []
    if live.get("window_open"):
        reasons.append("window_open")
    if live.get("power_budget_blocked"):
        reasons.append("power_budget")
    if live.get("compressor_protection_active"):
        reasons.append(f"compressor_{live.get('compressor_protection_reason', 'protection')}")
    if live.get("override_active"):
        reasons.append(f"override_{live.get('override_type') or 'active'}")
    if live.get("presence_away"):
        reasons.append("presence_away")
    if live.get("mold_prevention_active"):
        reasons.append("mold_prevention")
    if live.get("humidity_action") == "dehumidifying":
        reasons.append("humidity_comfort")
    if live.get("smart_ventilation_active"):
        reasons.append("smart_ventilation")
    if live.get("preconditioning_active"):
        reasons.append("preconditioning")
    if live.get("heat_source_reason") and live.get("heat_source_reason") != "inactive":
        reasons.append("heat_source")
    if not reasons:
        reasons.append(f"mode_{live.get('mode', 'idle')}")
    return reasons
