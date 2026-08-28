from unittest.mock import MagicMock

import pytest

from custom_components.roommind.const import MOLD_RISK_WARNING
from custom_components.roommind.managers.energy_manager import EnergyManager
from custom_components.roommind.managers.mold_manager import MoldManager


class _State:
    def __init__(self, state, attrs=None):
        self.state = state
        self.attributes = attrs or {}


def _hass(states):
    hass = MagicMock()
    hass.states.get.side_effect = states.get
    return hass


def test_energy_manager_integrates_and_learns_power():
    states = {
        "sensor.ac_power": _State("500", {"unit_of_measurement": "W"}),
        "climate.ac": _State("cool", {"hvac_modes": ["off", "cool", "dry"]}),
    }
    manager = EnergyManager(_hass(states))
    room = {"devices": [{"entity_id": "climate.ac", "type": "ac", "power_sensor_entity_id": "sensor.ac_power"}]}
    rs = {"current_temp": 28.0, "current_humidity": 60.0, "target_temp": 26.0, "mode": "cooling"}
    base = 1_700_000_000.0
    result = None
    for i in range(8):
        result = manager.update_room("studio", room, rs, 32.0, now=base + i * 60)
    assert result is not None
    assert result["ac_power_w"] == 500.0
    assert result["ac_energy_today_kwh"] > 0
    assert result["energy_mode"] == "cooling"
    assert result["energy_learning_samples"] >= 6
    assert result["predicted_power_w"] is not None


def test_energy_manager_converts_kw_sensor():
    states = {
        "sensor.ac_power": _State("0.72", {"unit_of_measurement": "kW"}),
        "climate.ac": _State("cool", {"hvac_modes": ["cool"]}),
    }
    manager = EnergyManager(_hass(states))
    power, configured = manager.read_power_w(
        {"devices": [{"entity_id": "climate.ac", "type": "ac", "power_sensor_entity_id": "sensor.ac_power"}]}
    )
    assert configured == 1
    assert power == pytest.approx(720.0)


@pytest.mark.asyncio
async def test_mold_prevention_prefers_dry_in_warm_weather(monkeypatch):
    manager = MoldManager(MagicMock())
    monkeypatch.setattr(
        "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
        lambda *_: (MOLD_RISK_WARNING, 82.0),
    )
    result = await manager.evaluate(
        "studio",
        "Studio",
        27.0,
        72.0,
        29.0,
        {"mold_prevention_enabled": True, "mold_humidity_threshold": 65},
        can_dry=True,
        can_cool=True,
        automation_enabled=True,
    )
    assert result.prevention_active is True
    assert result.prevention_strategy == "dry"
    assert result.prevention_delta == 0.0


@pytest.mark.asyncio
async def test_mold_prevention_uses_heat_in_cold_weather(monkeypatch):
    manager = MoldManager(MagicMock())
    monkeypatch.setattr(
        "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
        lambda *_: (MOLD_RISK_WARNING, 82.0),
    )
    result = await manager.evaluate(
        "bedroom",
        "Bedroom",
        19.0,
        72.0,
        5.0,
        {"mold_prevention_enabled": True, "mold_humidity_threshold": 65},
        can_dry=True,
        can_cool=True,
        automation_enabled=True,
    )
    assert result.prevention_strategy == "heat"
    assert result.prevention_delta > 0


@pytest.mark.asyncio
async def test_mold_prevention_does_not_act_when_automation_disabled(monkeypatch):
    manager = MoldManager(MagicMock())
    monkeypatch.setattr(
        "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
        lambda *_: (MOLD_RISK_WARNING, 82.0),
    )
    result = await manager.evaluate(
        "studio",
        "Studio",
        27.0,
        72.0,
        29.0,
        {"mold_prevention_enabled": True, "mold_humidity_threshold": 65},
        can_dry=True,
        automation_enabled=False,
    )
    assert result.prevention_active is False
    assert result.prevention_strategy is None
