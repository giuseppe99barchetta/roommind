"""Tests for RoomMind's optional HomeKit fan entity."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.fan import FanEntityFeature

from custom_components.roommind.const import DOMAIN
from custom_components.roommind.fan import RoomMindFan, async_setup_entry


@pytest.fixture
def mock_coordinator():
    coordinator = MagicMock()
    coordinator.hass = MagicMock()
    coordinator.hass.data = {DOMAIN: {"store": MagicMock()}}
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


def _room(**overrides):
    room = {"devices": [{"entity_id": "climate.ac", "type": "ac"}], "room_hvac_mode": "fan_only", "room_fan_mode": "low"}
    room.update(overrides)
    return room


def _state(mode="fan_only", fan_modes=None):
    return MagicMock(state=mode, attributes={"hvac_modes": ["off", "cool", "fan_only"], "fan_modes": fan_modes or ["auto", "low", "medium", "high"]})


def test_fan_exposes_speed_and_fan_only_state(mock_coordinator):
    mock_coordinator.hass.data[DOMAIN]["store"].get_room.return_value = _room()
    mock_coordinator.hass.states.get.return_value = _state()

    entity = RoomMindFan(mock_coordinator, "living_room")

    assert entity.is_on is True
    assert entity.percentage == 33
    assert entity.speed_count == 3
    assert entity.supported_features & FanEntityFeature.SET_SPEED
    assert entity.entity_registry_enabled_default is False


@pytest.mark.asyncio
async def test_fan_speed_is_forwarded_while_fan_only(mock_coordinator):
    mock_coordinator.hass.data[DOMAIN]["store"].get_room.return_value = _room()
    mock_coordinator.hass.states.get.return_value = _state()
    mock_coordinator.hass.data[DOMAIN]["store"].async_update_room = AsyncMock()
    mock_coordinator.hass.services.async_call = AsyncMock()

    await RoomMindFan(mock_coordinator, "living_room").async_set_percentage(100)

    mock_coordinator.hass.services.async_call.assert_awaited_once_with(
        "climate", "set_fan_mode", {"entity_id": "climate.ac", "fan_mode": "high"}, blocking=True
    )


@pytest.mark.asyncio
async def test_fan_speed_starts_fan_only_when_off(mock_coordinator):
    mock_coordinator.hass.data[DOMAIN]["store"].get_room.return_value = _room(room_hvac_mode="off")
    mock_coordinator.hass.states.get.return_value = _state(mode="off")
    climate = MagicMock(async_set_hvac_mode=AsyncMock(), async_set_fan_mode=AsyncMock())
    entity = RoomMindFan(mock_coordinator, "living_room")
    entity._climate = MagicMock(return_value=climate)

    await entity.async_set_percentage(100)

    climate.async_set_fan_mode.assert_awaited_once_with("high")
    climate.async_set_hvac_mode.assert_awaited_once_with("fan_only")


@pytest.mark.asyncio
async def test_fan_platform_creates_disabled_entities_for_ac_rooms(mock_coordinator):
    store = mock_coordinator.hass.data[DOMAIN]["store"]
    store.get_rooms.return_value = {"living_room": _room(), "outdoor": _room(is_outdoor=True)}
    entry = MagicMock(entry_id="entry")
    hass = MagicMock(data={DOMAIN: {entry.entry_id: mock_coordinator, "store": store}})
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    entities = async_add_entities.call_args.args[0]
    assert [entity._area_id for entity in entities] == ["living_room"]
