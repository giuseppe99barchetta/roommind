"""Rooms waiting for the central boiler keep their valves closed."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.managers.boiler_manager import BoilerState

from ..conftest import make_mock_states_get
from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock

AREA = "living_room_abc12345"
BOILER = {
    "outdoor_temp_sensor": "sensor.outdoor_temp",
    "boiler_entity": "climate.boiler",
    "hydraulic_bypass_entities": ["climate.bypass"],
}


def _setup(hass, mock_config_entry, room, settings):
    store = _make_store_mock({AREA: room}, settings)
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="17.0", humidity="50.0"))
    return coordinator, store


def _writes_to(hass, entity_id):
    return [
        (c.args[1], c.args[2])
        for c in hass.services.async_call.call_args_list
        if c.args[2].get("entity_id") == entity_id
    ]


@pytest.mark.asyncio
async def test_room_wanting_heat_keeps_trv_closed_until_boiler_runs(hass, mock_config_entry):
    coordinator, store = _setup(hass, mock_config_entry, SAMPLE_ROOM, BOILER)

    result = await coordinator._async_process_room(SAMPLE_ROOM, store.get_settings(), [])

    assert result["commanded_mode"] == "heating"  # still counts as boiler demand
    assert result["boiler_wait"] is True
    writes = _writes_to(hass, "climate.living_room")
    assert writes, "the TRV must be idled explicitly"
    assert all(service != "set_temperature" for service, _ in writes)
    assert ("set_hvac_mode", {"entity_id": "climate.living_room", "hvac_mode": "heat"}) not in writes


@pytest.mark.asyncio
async def test_room_heats_normally_once_boiler_is_available(hass, mock_config_entry):
    coordinator, store = _setup(hass, mock_config_entry, SAMPLE_ROOM, BOILER)
    coordinator._boiler_manager.state = BoilerState.ON

    result = await coordinator._async_process_room(SAMPLE_ROOM, store.get_settings(), [])

    assert result["boiler_wait"] is False
    assert any(service == "set_temperature" for service, _ in _writes_to(hass, "climate.living_room"))


@pytest.mark.asyncio
async def test_without_boiler_rooms_are_unaffected(hass, mock_config_entry):
    coordinator, store = _setup(hass, mock_config_entry, SAMPLE_ROOM, {"outdoor_temp_sensor": "sensor.outdoor_temp"})

    result = await coordinator._async_process_room(SAMPLE_ROOM, store.get_settings(), [])

    assert result["boiler_wait"] is False
    assert any(service == "set_temperature" for service, _ in _writes_to(hass, "climate.living_room"))


@pytest.mark.asyncio
async def test_bypass_trv_is_never_written_by_room_control(hass, mock_config_entry):
    room = {
        **SAMPLE_ROOM,
        "thermostats": ["climate.bypass"],
        "devices": [{"entity_id": "climate.bypass", "type": "trv", "role": "auto", "heating_system_type": ""}],
    }
    coordinator, store = _setup(hass, mock_config_entry, room, BOILER)

    for state in (BoilerState.OFF, BoilerState.ON):
        coordinator._boiler_manager.state = state
        hass.services.async_call.reset_mock()
        result = await coordinator._async_process_room(room, store.get_settings(), [])
        assert result["commanded_mode"] == "heating"
        assert _writes_to(hass, "climate.bypass") == []


@pytest.mark.asyncio
async def test_waiting_radiator_is_not_learned_as_heating(hass, mock_config_entry):
    coordinator, store = _setup(hass, mock_config_entry, SAMPLE_ROOM, BOILER)
    coordinator._ekf_training.process = MagicMock()
    coordinator.outdoor_temp_effective = 5.0

    await coordinator._async_process_room(SAMPLE_ROOM, store.get_settings(), [])

    kwargs = coordinator._ekf_training.process.call_args.kwargs
    assert kwargs["ekf_mode"] == "idle"
    assert kwargs["ekf_pf"] == 0.0


@pytest.mark.asyncio
async def test_running_radiator_is_learned_as_heating(hass, mock_config_entry):
    coordinator, store = _setup(hass, mock_config_entry, SAMPLE_ROOM, BOILER)
    coordinator._boiler_manager.state = BoilerState.ON
    coordinator._ekf_training.process = MagicMock()
    coordinator.outdoor_temp_effective = 5.0

    await coordinator._async_process_room(SAMPLE_ROOM, store.get_settings(), [])

    assert coordinator._ekf_training.process.call_args.kwargs["ekf_mode"] == "heating"


@pytest.mark.asyncio
async def test_waiting_room_is_displayed_idle_but_still_demands_heat(hass, mock_config_entry):
    coordinator, store = _setup(hass, mock_config_entry, SAMPLE_ROOM, BOILER)

    result = await coordinator._async_process_room(SAMPLE_ROOM, store.get_settings(), [])

    assert result["mode"] == "idle"
    assert result["heating_power"] == 0
    assert coordinator._boiler_demand_rooms({AREA: result}, {AREA: SAMPLE_ROOM}, store.get_settings()) == {AREA}


HYBRID_ROOM = {
    **SAMPLE_ROOM,
    "schedules": [],
    "thermostats": ["climate.living_room"],
    "acs": ["climate.living_ac"],
    "devices": [
        {"entity_id": "climate.living_room", "type": "trv", "role": "auto", "heating_system_type": ""},
        {"entity_id": "climate.living_ac", "type": "ac", "role": "auto", "heating_system_type": ""},
    ],
    "heat_source_orchestration": True,
}


def _hybrid_setup(hass, mock_config_entry):
    coordinator, store = _setup(hass, mock_config_entry, HYBRID_ROOM, BOILER)
    hass.states.get = MagicMock(
        side_effect=make_mock_states_get(
            temp="19.5",
            humidity="50.0",
            extra={
                "climate.living_ac": ("off", {"hvac_modes": ["off", "heat", "cool"], "min_temp": 16, "max_temp": 30}),
                "climate.living_room": ("off", {"hvac_modes": ["off", "heat"], "min_temp": 5, "max_temp": 30}),
            },
        )
    )
    coordinator.outdoor_temp_effective = 2.0  # cold: radiators preferred
    return coordinator, store


@pytest.mark.asyncio
async def test_ac_heats_while_boiler_waits_and_room_keeps_boiler_demand(hass, mock_config_entry):
    coordinator, store = _hybrid_setup(hass, mock_config_entry)

    result = await coordinator._async_process_room(HYBRID_ROOM, store.get_settings(), [])

    assert result["boiler_wait"] is False  # the AC is heating meanwhile
    ac_writes = _writes_to(hass, "climate.living_ac")
    assert ("set_hvac_mode", {"entity_id": "climate.living_ac", "hvac_mode": "heat"}) in ac_writes
    assert all(service != "set_temperature" for service, _ in _writes_to(hass, "climate.living_room"))
    # Still counts towards the boiler quorum.
    assert coordinator._boiler_demand_rooms({AREA: result}, {AREA: HYBRID_ROOM}, store.get_settings()) == {AREA}


@pytest.mark.asyncio
async def test_radiators_take_over_when_boiler_runs(hass, mock_config_entry):
    coordinator, store = _hybrid_setup(hass, mock_config_entry)
    coordinator._boiler_manager.state = BoilerState.ON

    await coordinator._async_process_room(HYBRID_ROOM, store.get_settings(), [])

    assert any(service == "set_temperature" for service, _ in _writes_to(hass, "climate.living_room"))
    assert ("set_hvac_mode", {"entity_id": "climate.living_ac", "hvac_mode": "heat"}) not in _writes_to(
        hass, "climate.living_ac"
    )


@pytest.mark.asyncio
async def test_waiting_room_raises_no_long_run_anomaly(hass, mock_config_entry):
    import time

    coordinator, store = _setup(hass, mock_config_entry, SAMPLE_ROOM, BOILER)
    coordinator._previous_modes[AREA] = "heating"
    coordinator._mode_on_since[AREA] = time.time() - 5 * 3600

    result = await coordinator._async_process_room(SAMPLE_ROOM, store.get_settings(), [])

    assert result["boiler_wait"] is True
    assert not [a for a in result["anomalies"] if a["type"] in ("long_run", "target_not_reached")]


@pytest.mark.asyncio
async def test_setback_trv_is_closed_while_waiting(hass, mock_config_entry):
    """Codex P2: idle_action=setback must not keep a waiting valve open."""
    room = {
        **SAMPLE_ROOM,
        "devices": [
            {
                "entity_id": "climate.living_room",
                "type": "trv",
                "role": "auto",
                "heating_system_type": "",
                "idle_action": "setback",
            }
        ],
    }
    coordinator, store = _setup(hass, mock_config_entry, room, BOILER)
    hass.states.get = MagicMock(
        side_effect=make_mock_states_get(
            temp="17.0",
            humidity="50.0",
            extra={"climate.living_room": ("heat", {"hvac_modes": ["off", "heat"], "temperature": 30})},
        )
    )

    await coordinator._async_process_room(room, store.get_settings(), [])

    writes = _writes_to(hass, "climate.living_room")
    assert ("set_hvac_mode", {"entity_id": "climate.living_room", "hvac_mode": "off"}) in writes
    # Only the defensive low setpoint that accompanies OFF, never a heating setpoint.
    setpoints = [data["temperature"] for service, data in writes if service == "set_temperature"]
    assert all(t < 17.0 for t in setpoints), setpoints
