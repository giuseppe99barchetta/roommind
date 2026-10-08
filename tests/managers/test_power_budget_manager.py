"""Tests for the power-sensor interpretation selected in settings."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from custom_components.roommind.managers.power_budget_manager import PowerBudgetManager


@pytest.mark.parametrize(
    ("power_sensor_mode", "expected_available"),
    (("available", 2000.0), ("consumption", 900.0)),
)
def test_power_sensor_mode_interprets_sensor_value(power_sensor_mode, expected_available):
    """Available is direct headroom; consumption is subtracted from the house limit."""
    manager = PowerBudgetManager()
    settings = {
        "power_budget_enabled": True,
        "power_sensor": "sensor.house_power",
        "power_sensor_mode": power_sensor_mode,
        "power_budget_max_watts": 3300,
        "power_budget_reserve_watts": 200,
    }

    with patch(
        "custom_components.roommind.managers.power_budget_manager.read_sensor_value",
        return_value=2200,
    ):
        manager.begin_cycle(MagicMock(), settings, {})

    assert manager.status().available_watts == expected_available


def test_consumption_meter_does_not_charge_running_acs_twice():
    manager = PowerBudgetManager()
    settings = {
        "power_budget_enabled": True,
        "power_sensor_mode": "consumption",
        "power_sensor": "sensor.house_power",
        "power_budget_max_watts": 3300,
        "power_budget_reserve_watts": 200,
    }
    with patch(
        "custom_components.roommind.managers.power_budget_manager.read_sensor_value",
        return_value=1500,
    ):
        manager.begin_cycle(MagicMock(), settings, {"sala": 1000})
    # 3300 - 1500 - 200 = 1600 W of actual free household headroom.
    assert manager.request_heat_pump("studio", 1200, already_running=False)
    assert not manager.request_heat_pump("camera", 500, already_running=False)
    assert manager.request_heat_pump("sala", 1000, already_running=True)


def test_unknown_startup_power_fails_closed_when_budget_enabled():
    manager = PowerBudgetManager()
    settings = {"power_budget_enabled": True, "power_sensor": "sensor.house"}
    with patch(
        "custom_components.roommind.managers.power_budget_manager.read_sensor_value",
        return_value=1000,
    ):
        manager.begin_cycle(MagicMock(), settings, {})
    assert not manager.request_heat_pump("camera", 0, already_running=False)
    assert manager.request_heat_pump("camera", 0, already_running=True)


def test_budget_disabled_preserves_unrestricted_activation():
    manager = PowerBudgetManager()
    manager.begin_cycle(MagicMock(), {"power_budget_enabled": False}, {})
    assert manager.request_heat_pump("camera", 0, already_running=False)


def test_stale_house_power_meter_fails_closed_without_affecting_room_sensors():
    manager = PowerBudgetManager()
    hass = MagicMock()
    hass.states.get.return_value = MagicMock(
        last_reported=datetime.now(UTC) - timedelta(minutes=5)
    )
    settings = {
        "power_budget_enabled": True,
        "power_sensor": "sensor.fastweb_power_control_consumo_istantaneo",
        "power_sensor_mode": "consumption",
        "power_budget_max_watts": 3300,
        "power_budget_reserve_watts": 200,
    }
    with patch("custom_components.roommind.managers.power_budget_manager.read_sensor_value", return_value=800):
        manager.begin_cycle(hass, settings, {})
    assert manager.status().available_watts is None
    assert manager.status().sensor_healthy is False
    assert not manager.request_heat_pump("sala", 600, already_running=False)
