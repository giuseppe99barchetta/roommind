"""Tests for RoomMind's Dry-mode dehumidifier entity."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import HVACMode

from custom_components.roommind.const import DOMAIN
from custom_components.roommind.humidifier import RoomMindDryDehumidifier, async_setup_entry


@pytest.fixture
def mock_coordinator():
    coordinator = MagicMock()
    coordinator.hass = MagicMock()
    store = MagicMock()
    coordinator.hass.data = {DOMAIN: {"store": store}}
    return coordinator, store


def test_dehumidifier_reads_configured_room_humidity(mock_coordinator):
    """The entity provides the room humidity to HomeKit."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"humidity_sensor": "sensor.bedroom_humidity"}
    coordinator.hass.states.get.return_value = MagicMock(state="63.5")

    assert RoomMindDryDehumidifier(coordinator, "bedroom").current_humidity == 63.5


@pytest.mark.parametrize(
    ("requested_mode", "physical_mode", "expected"),
    [
        ("off", "dry", True),  # Automatic mold prevention overrides OFF without rewriting it.
        ("off", "off", False),
        ("dry", "dry", True),
        ("dry", "off", False),  # Never show a stopped AC as on after HA restart.
        ("off", "heat", False),
        ("off", "unavailable", False),
    ],
)
def test_dehumidifier_reflects_physical_dry_mode(mock_coordinator, requested_mode, physical_mode, expected):
    coordinator, store = mock_coordinator
    store.get_room.return_value = {
        "room_hvac_mode": requested_mode,
        "devices": [
            {"type": "trv", "entity_id": "climate.valve"},
            {"type": "ac", "entity_id": "climate.bedroom_ac"},
        ],
    }
    coordinator.hass.states.get.return_value = MagicMock(state=physical_mode)
    assert RoomMindDryDehumidifier(coordinator, "bedroom").is_on is expected
    coordinator.hass.states.get.assert_called_once_with("climate.bedroom_ac")


def test_dehumidifier_handles_missing_ac_state(mock_coordinator):
    coordinator, store = mock_coordinator
    store.get_room.return_value = {
        "devices": [{"type": "ac", "entity_id": "climate.bedroom_ac"}]
    }
    coordinator.hass.states.get.return_value = None
    assert RoomMindDryDehumidifier(coordinator, "bedroom").is_on is False


@pytest.mark.asyncio
async def test_dehumidifier_controls_canonical_climate(mock_coordinator):
    """Turning the entity on and off controls the room's Dry mode."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"room_hvac_mode": "dry"}
    climate = MagicMock(async_set_hvac_mode=AsyncMock())
    dehumidifier = RoomMindDryDehumidifier(coordinator, "bedroom")
    dehumidifier._climate = MagicMock(return_value=climate)

    await dehumidifier.async_turn_on()
    await dehumidifier.async_turn_off()

    assert climate.async_set_hvac_mode.await_args_list == [
        ((HVACMode.DRY,), {}),
        ((HVACMode.OFF,), {}),
    ]


@pytest.mark.asyncio
async def test_setup_creates_dehumidifier_when_selected():
    """A room selecting humidifier gets the dedicated entity."""
    coordinator = MagicMock()
    coordinator._dry_humidifier_entity_areas = set()
    store = MagicMock()
    store.get_rooms.return_value = {
        "bedroom": {
            "devices": [{"entity_id": "climate.bedroom_ac", "type": "ac"}],
            "dry_entity_type": "humidifier",
        }
    }
    entry = MagicMock(entry_id="test_entry")
    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: coordinator, "store": store}}
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1
    assert isinstance(entities[0], RoomMindDryDehumidifier)
