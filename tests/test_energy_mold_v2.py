import time
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
    assert result["energy_prediction_confidence"] == "medium"
    assert 500 < manager.budget_power_w("studio", "cooling", 1000) < 1000


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


def test_energy_manager_treats_fan_only_as_idle_without_learning_or_prediction():
    states = {
        "sensor.ac_power": _State("75", {"unit_of_measurement": "W"}),
        "climate.ac": _State("fan_only", {"hvac_modes": ["off", "fan_only"]}),
    }
    manager = EnergyManager(_hass(states))
    room = {
        "heat_pump_power_watts": 900,
        "devices": [{"entity_id": "climate.ac", "type": "ac", "power_sensor_entity_id": "sensor.ac_power"}],
    }
    room_state = {"current_temp": 25.0, "current_humidity": 55.0, "target_temp": 23.0, "mode": "idle"}

    result = None
    for index in range(8):
        result = manager.update_room("studio", room, room_state, 30.0, now=1_700_000_000.0 + index * 60)

    assert result is not None
    assert result["energy_mode"] == "idle"
    assert result["energy_learning_samples"] == 0
    assert result["predicted_power_w"] is None
    assert result["predicted_energy_1h_kwh"] is None
    assert result["energy_prediction_confidence"] is None
    assert manager._rooms["studio"].models == {}
    assert manager.predict_power("studio", "fan_only", 25.0, 23.0, 30.0, 55.0, 900)[0] is None


@pytest.mark.parametrize(
    ("samples", "expected"),
    [(0, "low"), (5, "low"), (6, "medium"), (23, "medium"), (24, "high")],
)
def test_energy_prediction_confidence_tracks_learned_sample_count(samples, expected):
    assert EnergyManager.prediction_confidence(500.0, samples) == expected


def test_energy_prediction_confidence_is_unavailable_without_a_prediction():
    assert EnergyManager.prediction_confidence(None, 42) is None


def test_energy_manager_flags_sustained_low_thermal_response_at_expected_power():
    states = {
        "sensor.ac_power": _State("500", {"unit_of_measurement": "W"}),
        "climate.ac": _State("cool", {"hvac_modes": ["off", "cool"]}),
    }
    manager = EnergyManager(_hass(states))
    room = {"devices": [{"entity_id": "climate.ac", "type": "ac", "power_sensor_entity_id": "sensor.ac_power"}]}
    now = 1_700_000_000.0
    for index in range(14):
        manager.update_room(
            "studio", room, {"current_temp": 28 - index * 0.1, "target_temp": 24, "mode": "cooling"}, 32, now=now + index * 60
        )
    result = manager.update_room(
        "studio", room, {"current_temp": 26.69, "target_temp": 24, "mode": "cooling"}, 32, now=now + 14 * 60
    )
    assert result["ac_efficiency_status"] == "possible_issue"
    assert result["ac_efficiency_reason"] == "same_power_low_response"


def test_energy_manager_compares_efficiency_at_similar_outdoor_conditions():
    states = {
        "sensor.ac_power": _State("500", {"unit_of_measurement": "W"}),
        "climate.ac": _State("cool", {"hvac_modes": ["off", "cool"]}),
    }
    manager = EnergyManager(_hass(states))
    room = {"devices": [{"entity_id": "climate.ac", "type": "ac", "power_sensor_entity_id": "sensor.ac_power"}]}
    now = 1_700_000_000.0
    for index in range(14):
        manager.update_room(
            "studio", room, {"current_temp": 28 - index * 0.1, "target_temp": 24, "mode": "cooling"}, 32, now=now + index * 60
        )
    result = manager.update_room(
        "studio", room, {"current_temp": 26.69, "target_temp": 24, "mode": "cooling"}, 10, now=now + 14 * 60
    )
    assert result["ac_efficiency_status"] == "normal"
    assert result["ac_efficiency_outdoor_delta_c"] == pytest.approx(16.7)


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


def test_energy_manager_tracks_and_predicts_device_breakdown():
    from unittest.mock import MagicMock

    from custom_components.roommind.managers.energy_manager import EnergyManager

    hass = MagicMock()
    power = MagicMock(state="0.45", attributes={"unit_of_measurement": "kW"})
    climate = MagicMock(state="cool", attributes={})
    hass.states.get.side_effect = {"sensor.ac_power": power, "climate.ac": climate}.get
    manager = EnergyManager(hass)
    room = {
        "heat_pump_power_watts": 700,
        "devices": [
            {
                "entity_id": "climate.ac",
                "type": "ac",
                "power_sensor_entity_id": "sensor.ac_power",
            }
        ],
    }
    room_state = {"current_temp": 28, "target_temp": 25, "current_humidity": 60, "commanded_mode": "cooling"}
    for i in range(8):
        result = manager.update_room("sala", room, room_state, 32, now=1000 + i * 60)
    assert result["ac_device_power_w"] == {"climate.ac": 450.0}
    assert result["predicted_device_power_w"]["climate.ac"] > 0
    predicted, samples = manager.predict_power("sala", "cooling", 28, 25, 32, 60, 700)
    assert predicted is not None and predicted > 0
    assert samples >= 6


def test_energy_manager_bootstraps_device_breakdown_from_history(tmp_path):
    """Per-device learning is restored from RoomMind history after restart."""
    from unittest.mock import MagicMock

    from custom_components.roommind.managers.energy_manager import EnergyManager
    from custom_components.roommind.utils.history_store import HistoryStore

    store = HistoryStore(str(tmp_path / "history"))
    base = time.time()
    for index in range(6):
        store.record(
            "sala",
            {
                "ac_power_w": 450,
                "ac_device_power_w": {"climate.ac": 450},
                "energy_mode": "cooling",
                "room_temp": 28,
                "target_temp": 25,
                "outdoor_temp": 32,
                "current_humidity": 60,
            },
            timestamp=base + index * 60,
        )

    manager = EnergyManager(MagicMock())
    manager.bootstrap("sala", store.read_detail("sala"))

    prediction = manager.predict_device_power("sala", "cooling", 28, 25, 32, 60)
    assert prediction["climate.ac"] > 0
