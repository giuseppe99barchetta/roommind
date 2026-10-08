"""Safety preview is read-only and never reserves the live budget."""

from unittest.mock import MagicMock, patch

from custom_components.roommind.managers.energy_manager import EnergyManager
from custom_components.roommind.managers.power_budget_manager import PowerBudgetManager
from custom_components.roommind.services.control_preview import build_control_preview


def test_preview_simulates_budget_without_writing_or_mutating_live_allocator():
    hass = MagicMock()
    hass.states.get.return_value = MagicMock(state="off")
    coordinator = MagicMock()
    coordinator._energy_manager = EnergyManager(hass)
    coordinator._power_budget_manager = PowerBudgetManager()
    coordinator._boiler_manager.state.value = "off"
    coordinator._boiler_manager.demand_rooms = set()
    coordinator.rooms = {"sala": {"window_open": False}}
    coordinator._compressor_manager.check_can_activate.return_value = True
    rooms = {"sala": {"heat_pump_power_watts": 1000, "devices": [{"type": "ac", "entity_id": "climate.ac"}]}}
    settings = {
        "climate_control_active": True,
        "power_budget_enabled": True,
        "power_sensor": "sensor.house",
        "power_sensor_mode": "consumption",
        "power_budget_max_watts": 3300,
        "power_budget_reserve_watts": 200,
    }
    with patch("custom_components.roommind.managers.power_budget_manager.read_sensor_value", return_value=2000):
        result = build_control_preview(hass, settings, rooms, coordinator, "cooling")
    assert result["read_only"] is True
    assert result["rooms"]["sala"]["would_allow"] is True
    assert result["rooms"]["sala"]["watts"] == 1000
    assert coordinator._power_budget_manager.status().enabled is False
    hass.services.async_call.assert_not_called()


def test_preview_respects_disabled_global_control():
    hass = MagicMock()
    hass.states.get.return_value = MagicMock(state="off")
    coordinator = MagicMock()
    coordinator._energy_manager = EnergyManager(hass)
    coordinator._boiler_manager.state.value = "off"
    coordinator._boiler_manager.demand_rooms = set()
    coordinator.rooms = {"sala": {}}
    coordinator._compressor_manager.check_can_activate.return_value = True
    rooms = {"sala": {"heat_pump_power_watts": 700, "devices": [{"type": "ac", "entity_id": "climate.ac"}]}}
    result = build_control_preview(hass, {"climate_control_active": False}, rooms, coordinator)
    assert result["rooms"]["sala"]["would_allow"] is False
    assert result["rooms"]["sala"]["reason"] == "control_disabled"
    hass.services.async_call.assert_not_called()


def test_preview_does_not_reserve_power_for_window_blocked_room():
    hass = MagicMock()
    hass.states.get.return_value = MagicMock(state="off")
    coordinator = MagicMock()
    coordinator._energy_manager = EnergyManager(hass)
    coordinator._boiler_manager.state.value = "off"
    coordinator._boiler_manager.demand_rooms = set()
    coordinator.rooms = {"a": {"window_open": True}, "b": {"window_open": False}}
    coordinator._compressor_manager.check_can_activate.return_value = True
    rooms = {
        key: {"heat_pump_power_watts": 1000, "devices": [{"type": "ac", "entity_id": f"climate.{key}"}]}
        for key in ("a", "b")
    }
    settings = {
        "power_budget_enabled": True,
        "power_sensor": "sensor.house",
        "power_sensor_mode": "consumption",
        "power_budget_max_watts": 3300,
        "power_budget_reserve_watts": 200,
    }
    with patch("custom_components.roommind.managers.power_budget_manager.read_sensor_value", return_value=2000):
        result = build_control_preview(hass, settings, rooms, coordinator)
    assert result["rooms"]["a"]["reason"] == "room_safety"
    assert result["rooms"]["b"]["would_allow"] is True
