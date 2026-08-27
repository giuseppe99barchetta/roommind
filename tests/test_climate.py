"""Tests for RoomMind climate platform."""

from __future__ import annotations

import time
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import ClimateEntityFeature, HVACMode

from custom_components.roommind.climate import (
    RoomMindClimate,
    RoomMindOverrideClimate,
    _create_room_climates,
    async_setup_entry,
)
from custom_components.roommind.const import (
    DEFAULT_COMFORT_COOL,
    DEFAULT_COMFORT_HEAT,
    DOMAIN,
    OVERRIDE_CUSTOM,
)


@pytest.fixture
def mock_coordinator():
    coordinator = MagicMock()
    coordinator.hass = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    store = MagicMock()
    coordinator.hass.data = {DOMAIN: {"store": store}}
    coordinator.data = {}
    return coordinator, store


def _active_auto_room(**overrides):
    room = {
        "climate_mode": "auto",
        "override_heat": 21.0,
        "override_cool": 24.0,
        "override_until": None,
        "override_type": "custom",
    }
    room.update(overrides)
    return room


def test_create_room_climates(mock_coordinator):
    """Factory creates exactly one climate entity per room."""
    coordinator, _ = mock_coordinator
    climates = _create_room_climates(coordinator, "living_room")
    assert len(climates) == 2
    assert isinstance(climates[0], RoomMindClimate)
    assert isinstance(climates[1], RoomMindOverrideClimate)


def _canonical_room(devices, **overrides):
    room = {
        "devices": devices,
        "logical_heat_target": 21.0,
        "logical_cool_target": 26.0,
        "room_hvac_mode": "cool",
    }
    room.update(overrides)
    return room


def test_canonical_mixed_room_capabilities_and_logical_cooling_target(mock_coordinator):
    """TRV frost targets cannot affect the canonical cooling target."""
    coordinator, store = mock_coordinator
    ac = MagicMock(
        state="cool",
        attributes={"hvac_modes": ["off", "heat", "cool", "dry", "fan_only"], "fan_modes": ["low", "high"]},
    )
    trv = MagicMock(state="off", attributes={"temperature": 7.0, "hvac_modes": ["off", "heat"]})
    device_states = {"climate.ac": ac, "climate.trv": trv}
    coordinator.hass.states.get.side_effect = device_states.get
    store.get_room.return_value = _canonical_room(
        [{"entity_id": "climate.ac", "type": "ac"}, {"entity_id": "climate.trv", "type": "trv"}]
    )
    entity = RoomMindClimate(coordinator, "living_room")
    assert {mode.value for mode in entity.hvac_modes} == {"off", "heat", "cool", "heat_cool", "dry", "fan_only"}
    assert entity.hvac_mode == HVACMode.COOL
    assert entity.target_temperature == 26.0
    assert entity.fan_modes == ["low", "high"]


def test_canonical_trv_only_does_not_expose_ac_modes(mock_coordinator):
    coordinator, store = mock_coordinator
    store.get_room.return_value = _canonical_room([{"entity_id": "climate.trv", "type": "trv"}], room_hvac_mode="heat")
    coordinator.hass.states.get.return_value = MagicMock(state="heat", attributes={"hvac_modes": ["off", "heat"]})
    assert [mode.value for mode in RoomMindClimate(coordinator, "living_room").hvac_modes] == ["off", "heat"]


def test_unique_id_and_entity_id(mock_coordinator):
    """Climate entity has correct unique_id and entity_id."""
    coordinator, _ = mock_coordinator
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.unique_id == "roommind_living_room_override"
    assert entity.entity_id == "climate.roommind_living_room_override"


def test_hvac_mode_off_when_no_override(mock_coordinator):
    """hvac_mode returns OFF when no override is set."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {
        "override_heat": None,
        "override_cool": None,
        "override_until": None,
        "override_type": None,
    }
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.hvac_mode == HVACMode.OFF


def test_hvac_mode_heat_cool_when_permanent_override(mock_coordinator):
    """hvac_mode returns HEAT_COOL when permanent override is active in auto mode."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.hvac_mode == HVACMode.HEAT_COOL


def test_hvac_mode_heat_cool_when_timed_override_active(mock_coordinator):
    """hvac_mode returns HEAT_COOL when timed override is still active."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room(override_until=time.time() + 3600, override_type="boost")
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.hvac_mode == HVACMode.HEAT_COOL


def test_hvac_mode_off_when_timed_override_expired(mock_coordinator):
    """hvac_mode returns OFF when timed override has expired."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room(override_until=time.time() - 100, override_type="boost")
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.hvac_mode == HVACMode.OFF


def test_hvac_mode_heat_when_heat_only(mock_coordinator):
    """hvac_mode returns HEAT for active override in heat_only room."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room(climate_mode="heat_only", override_cool=None)
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.hvac_mode == HVACMode.HEAT


def test_hvac_mode_cool_when_cool_only(mock_coordinator):
    """hvac_mode returns COOL for active override in cool_only room."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room(climate_mode="cool_only", override_heat=None)
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.hvac_mode == HVACMode.COOL


def test_override_entity_auto_reports_range(mock_coordinator):
    """Auto mode exposes HEAT_COOL with range support and low/high targets."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert HVACMode.HEAT_COOL in entity.hvac_modes
    assert entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    assert not entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE
    assert entity.target_temperature_low == 21.0
    assert entity.target_temperature_high == 24.0


def test_override_entity_heat_only_single_target(mock_coordinator):
    """heat_only mode exposes single-target HEAT with override_heat value."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room(climate_mode="heat_only", override_cool=None)
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.hvac_modes == [HVACMode.OFF, HVACMode.HEAT]
    assert entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE
    assert not entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    assert entity.target_temperature == 21.0


def test_override_entity_cool_only_single_target(mock_coordinator):
    """cool_only mode exposes single-target COOL with override_cool value."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room(climate_mode="cool_only", override_heat=None)
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.hvac_modes == [HVACMode.OFF, HVACMode.COOL]
    assert entity.target_temperature == 24.0


def test_target_temperatures_none_when_no_override(mock_coordinator):
    """All target properties return None when no override is active."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {
        "climate_mode": "auto",
        "override_heat": None,
        "override_cool": None,
        "override_until": None,
        "override_type": None,
    }
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.target_temperature is None
    assert entity.target_temperature_low is None
    assert entity.target_temperature_high is None


def test_current_temperature_from_coordinator_data(mock_coordinator):
    """current_temperature reads from coordinator.data."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"override_heat": None, "override_cool": None}
    coordinator.data = {"rooms": {"living_room": {"current_temp": 20.5}}}
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.current_temperature == 20.5


def test_current_temperature_none_when_no_data(mock_coordinator):
    """current_temperature returns None when coordinator has no data."""
    coordinator, store = mock_coordinator
    coordinator.data = None
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.current_temperature is None


def test_current_temperature_none_when_room_not_in_data(mock_coordinator):
    """current_temperature returns None when room not in coordinator data."""
    coordinator, store = mock_coordinator
    coordinator.data = {"rooms": {"other_room": {"current_temp": 20.0}}}
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.current_temperature is None


@pytest.mark.asyncio
async def test_override_entity_set_range_writes_split(mock_coordinator):
    """Setting low/high in auto mode writes split override_heat/override_cool."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "auto"}
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_temperature(target_temp_low=20.0, target_temp_high=25.0)
    store.async_update_room.assert_awaited_once_with(
        "living_room",
        {
            "override_heat": 20.0,
            "override_cool": 25.0,
            "override_until": None,
            "override_type": OVERRIDE_CUSTOM,
        },
    )
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_single_temperature_auto_derives_dead_band(mock_coordinator):
    """Bare temperature in auto mode derives a dead-band from comfort_cool."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "auto", "comfort_cool": 24.0}
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_temperature(temperature=22.0)
    store.async_update_room.assert_awaited_once_with(
        "living_room",
        {
            "override_heat": 22.0,
            "override_cool": 24.0,
            "override_until": None,
            "override_type": OVERRIDE_CUSTOM,
        },
    )


@pytest.mark.asyncio
async def test_set_single_temperature_auto_above_comfort_cool(mock_coordinator):
    """Bare temperature above comfort_cool collapses band to the higher value."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "auto", "comfort_cool": 24.0}
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_temperature(temperature=26.0)
    written = store.async_update_room.await_args[0][1]
    assert written["override_heat"] == 26.0
    assert written["override_cool"] == 26.0


@pytest.mark.asyncio
async def test_set_single_temperature_heat_only(mock_coordinator):
    """Bare temperature in heat_only mode writes heat target only."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "heat_only"}
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_temperature(temperature=22.0)
    written = store.async_update_room.await_args[0][1]
    assert written["override_heat"] == 22.0
    assert written["override_cool"] is None


@pytest.mark.asyncio
async def test_set_single_temperature_cool_only(mock_coordinator):
    """Bare temperature in cool_only mode writes cool target only."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "cool_only"}
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_temperature(temperature=23.0)
    written = store.async_update_room.await_args[0][1]
    assert written["override_heat"] is None
    assert written["override_cool"] == 23.0


@pytest.mark.asyncio
async def test_set_temperature_no_temp_kwarg(mock_coordinator):
    """set_temperature does nothing when no temperature kwargs are given."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "auto"}
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_temperature()
    store.async_update_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_hvac_mode_off_clears_override(mock_coordinator):
    """Setting hvac_mode to OFF clears override and refreshes."""
    coordinator, store = mock_coordinator
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.OFF)
    store.async_update_room.assert_awaited_once_with(
        "living_room",
        {
            "override_heat": None,
            "override_cool": None,
            "override_until": None,
            "override_type": None,
        },
    )
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_hvac_mode_heat_cool_activates_with_comfort_defaults(mock_coordinator):
    """Setting HEAT_COOL without active override activates with comfort targets."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {
        "climate_mode": "auto",
        "override_heat": None,
        "override_cool": None,
        "override_until": None,
        "override_type": None,
    }
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    store.async_update_room.assert_awaited_once_with(
        "living_room",
        {
            "override_heat": DEFAULT_COMFORT_HEAT,
            "override_cool": DEFAULT_COMFORT_COOL,
            "override_until": None,
            "override_type": OVERRIDE_CUSTOM,
        },
    )
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_hvac_mode_heat_activates_heat_only(mock_coordinator):
    """Setting HEAT in heat_only room activates heat target only."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {
        "climate_mode": "heat_only",
        "comfort_heat": 22.0,
        "override_heat": None,
        "override_cool": None,
    }
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.HEAT)
    written = store.async_update_room.await_args[0][1]
    assert written["override_heat"] == 22.0
    assert written["override_cool"] is None


@pytest.mark.asyncio
async def test_set_hvac_mode_cool_activates_cool_only(mock_coordinator):
    """Setting COOL in cool_only room activates cool target only."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {
        "climate_mode": "cool_only",
        "comfort_cool": 25.0,
        "override_heat": None,
        "override_cool": None,
    }
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.COOL)
    written = store.async_update_room.await_args[0][1]
    assert written["override_heat"] is None
    assert written["override_cool"] == 25.0


@pytest.mark.asyncio
async def test_set_hvac_mode_noop_when_override_exists(mock_coordinator):
    """Setting a non-OFF mode does not update store if override already active."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room(override_heat=23.0, override_cool=25.0)
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    store.async_update_room.assert_not_awaited()
    coordinator.async_request_refresh.assert_awaited_once()


def test_hvac_mode_off_when_room_missing(mock_coordinator):
    """hvac_mode returns OFF when room doesn't exist in store."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = None
    entity = RoomMindOverrideClimate(coordinator, "nonexistent")
    assert entity.hvac_mode == HVACMode.OFF


@pytest.mark.asyncio
async def test_async_setup_entry_creates_entities_for_all_rooms():
    """async_setup_entry creates climate entities for all rooms."""
    coordinator = MagicMock()
    coordinator._climate_entity_areas = set()

    store = MagicMock()
    store.get_rooms.return_value = {
        "living_room": {"thermostats": ["climate.living"]},
        "bedroom": {},
    }

    entry = MagicMock()
    entry.entry_id = "test_entry"

    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: coordinator, "store": store}}

    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    assert coordinator.async_add_climate_entities is async_add_entities
    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 4
    assert sum(isinstance(e, RoomMindClimate) for e in entities) == 2
    assert "living_room" in coordinator._climate_entity_areas
    assert "bedroom" in coordinator._climate_entity_areas


@pytest.mark.asyncio
async def test_async_setup_entry_no_rooms():
    """async_setup_entry does not call async_add_entities when no rooms exist."""
    coordinator = MagicMock()
    coordinator._climate_entity_areas = set()

    store = MagicMock()
    store.get_rooms.return_value = {}

    entry = MagicMock()
    entry.entry_id = "test_entry"

    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: coordinator, "store": store}}

    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    async_add_entities.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("global_enabled,room_enabled", [(False, True), (True, False), (False, False)])
async def test_canonical_manual_fan_only_bypasses_automation_switches(
    mock_coordinator, global_enabled, room_enabled
):
    """Explicit fan-only commands remain manual even when automation is disabled."""
    coordinator, store = mock_coordinator
    room = _canonical_room(
        [{"entity_id": "climate.ac", "type": "ac"}],
        room_hvac_mode="off",
        climate_control_enabled=room_enabled,
    )
    store.get_room.return_value = room
    store.get_settings.return_value = {"climate_control_active": global_enabled}
    store.async_update_room = AsyncMock()
    coordinator.hass.states.get.return_value = MagicMock(
        state="off", attributes={"hvac_modes": ["off", "cool", "fan_only"]}
    )
    coordinator.hass.services.async_call = AsyncMock()

    await RoomMindClimate(coordinator, "living_room").async_set_hvac_mode(HVACMode.FAN_ONLY)

    coordinator.hass.services.async_call.assert_any_await(
        "climate", "set_hvac_mode", {"entity_id": "climate.ac", "hvac_mode": "fan_only"}, blocking=True
    )


@pytest.mark.asyncio
async def test_canonical_manual_cool_bypasses_global_automation_switch(mock_coordinator):
    coordinator, store = mock_coordinator
    store.get_room.return_value = _canonical_room(
        [{"entity_id": "climate.ac", "type": "ac"}],
        room_hvac_mode="off",
        climate_control_enabled=False,
    )
    store.get_settings.return_value = {"climate_control_active": False}
    store.async_update_room = AsyncMock()
    coordinator.hass.states.get.return_value = MagicMock(
        state="off", attributes={"hvac_modes": ["off", "cool", "fan_only"]}
    )
    coordinator.hass.services.async_call = AsyncMock()

    await RoomMindClimate(coordinator, "living_room").async_set_hvac_mode(HVACMode.COOL)

    coordinator.hass.services.async_call.assert_any_await(
        "climate", "set_hvac_mode", {"entity_id": "climate.ac", "hvac_mode": "cool"}, blocking=True
    )
    assert any(call.args[:2] == ("climate", "set_temperature") for call in coordinator.hass.services.async_call.await_args_list)


@pytest.mark.asyncio
async def test_canonical_manual_off_bypasses_global_automation_switch(mock_coordinator):
    coordinator, store = mock_coordinator
    store.get_room.return_value = _canonical_room(
        [{"entity_id": "climate.ac", "type": "ac"}],
        room_hvac_mode="cool",
        climate_control_enabled=False,
    )
    store.get_settings.return_value = {"climate_control_active": False}
    store.async_update_room = AsyncMock()
    coordinator.hass.states.get.return_value = MagicMock(
        state="cool", attributes={"hvac_modes": ["off", "cool", "fan_only"], "min_temp": 16}
    )
    coordinator.hass.services.async_call = AsyncMock()

    await RoomMindClimate(coordinator, "living_room").async_set_hvac_mode(HVACMode.OFF)

    coordinator.hass.services.async_call.assert_any_await(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.ac", "hvac_mode": "off"},
        blocking=True,
        context=ANY,
    )
