"""Tests for the power-sensor interpretation selected in settings."""

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
