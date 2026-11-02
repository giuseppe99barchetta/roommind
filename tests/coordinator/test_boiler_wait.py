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
