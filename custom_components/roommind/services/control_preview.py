"""Read-only preview of AC electrical admission and existing room decisions."""

from __future__ import annotations

from ..managers.power_budget_manager import PowerBudgetManager
from ..utils.device_utils import get_ac_eids
from ..utils.room_insights import build_decision_reasons


def build_control_preview(hass, settings: dict, rooms: dict, coordinator, mode: str = "cooling") -> dict:
    """Simulate one hypothetical AC request per room; do not actuate devices.

    This is a power/compressor safety preview, not a new MPC forecast. The
    existing coordinator live state supplies the current decision reasons.
    """
    if mode not in ("heating", "cooling", "dry"):
        raise ValueError("Unsupported preview mode")
    energy = coordinator._energy_manager
    running_loads = {}
    running_rooms = set()
    for area_id, room in rooms.items():
        acs = get_ac_eids(room.get("devices", []))
        if any(
            (state := hass.states.get(eid)) is not None and state.state in ("heat", "cool", "dry")
            for eid in acs
        ):
            running_rooms.add(area_id)
            physical = energy._physical_mode(hass, room, "idle")
            running_loads[area_id] = energy.budget_power_w(
                area_id, physical, float(room.get("heat_pump_power_watts", 0) or 0)
            )

    # Independent manager: never alter the coordinator's live reservations.
    budget = PowerBudgetManager()
    budget.begin_cycle(hass, settings, running_loads)
    simulated_rooms = {}
    preview_order = sorted(
        rooms,
        key=lambda area_id: (coordinator.rooms.get(area_id, {}).get("coordination_rank", 9999), area_id),
    )
    for area_id in preview_order:
        room = rooms[area_id]
        acs = get_ac_eids(room.get("devices", []))
        if not acs:
            continue
        watts, source, samples = energy.budget_power_estimate(
            area_id, mode, float(room.get("heat_pump_power_watts", 0) or 0)
        )
        live = coordinator.rooms.get(area_id, {})
        physical_running = area_id in running_rooms
        compressor_ok = physical_running or all(coordinator._compressor_manager.check_can_activate(eid) for eid in acs)
        enabled = bool(settings.get("climate_control_active", True)) and room.get("climate_control_enabled", True)
        if room.get("is_outdoor") or not enabled:
            reason = "control_disabled"
        elif live.get("window_open") or live.get("force_off"):
            reason = "room_safety"
        elif not compressor_ok:
            reason = "compressor_protection"
        elif not budget.request_heat_pump(area_id, watts, physical_running):
            reason = "power_budget"
        else:
            reason = "eligible"
        simulated_rooms[area_id] = {
            "watts": watts,
            "source": source,
            "samples": samples,
            "already_running": physical_running,
            "would_allow": reason == "eligible",
            "reason": reason,
            "current_decision_reasons": build_decision_reasons(live),
        }
    status = budget.status()
    boiler = coordinator._boiler_manager
    return {
        "mode": mode,
        "read_only": True,
        "scope": "electrical_and_compressor_admission_only",
        "climate_control_active": bool(settings.get("climate_control_active", True)),
        "house_available_watts": status.available_watts,
        "power_sensor_healthy": status.sensor_healthy,
        "power_sensor_age_seconds": status.sensor_age_seconds,
        "boiler_state": boiler.state.value,
        "boiler_demand_rooms": sorted(boiler.demand_rooms),
        "bypass_acknowledged": boiler.path_safe,
        "rooms": simulated_rooms,
    }
