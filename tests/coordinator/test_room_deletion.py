"""Deleting a room switches its climate devices off on the next cycle (W1.6, upstream 49535315)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

TURN_OFF = "custom_components.roommind.coordinator.async_turn_off_climate"
BED = {
    "area_id": "bed",
    "devices": [
        {"entity_id": "climate.bed_trv", "type": "trv", "role": "auto"},
        {"entity_id": "climate.shared_ac", "type": "ac", "role": "auto"},
    ],
}


def _coordinator(hass, mock_config_entry, *, remaining=None, settings=None):
    store = _make_store_mock(remaining or {}, settings)
    hass.data = {"roommind": {"store": store}}
    return _create_coordinator(hass, mock_config_entry)


@pytest.mark.asyncio
async def test_deleted_room_devices_are_switched_off_next_cycle(hass, mock_config_entry):
    coordinator = _coordinator(hass, mock_config_entry)
    assert coordinator.note_room_deleted("bed", BED) is True
    with patch(TURN_OFF, new=AsyncMock()) as turn_off:
        await coordinator._async_switch_deleted_rooms_off({})
    assert sorted(c.args[1] for c in turn_off.await_args_list) == ["climate.bed_trv", "climate.shared_ac"]
    # one shot: the next cycle sends nothing more
    with patch(TURN_OFF, new=AsyncMock()) as turn_off:
        await coordinator._async_switch_deleted_rooms_off({})
    turn_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_device_still_used_by_another_room_is_left_on(hass, mock_config_entry):
    other = {"area_id": "living", "devices": [{"entity_id": "climate.shared_ac", "type": "ac", "role": "auto"}]}
    coordinator = _coordinator(hass, mock_config_entry, remaining={"living": other})
    coordinator.note_room_deleted("bed", BED)
    with patch(TURN_OFF, new=AsyncMock()) as turn_off:
        await coordinator._async_switch_deleted_rooms_off({})
    assert [c.args[1] for c in turn_off.await_args_list] == ["climate.bed_trv"]


@pytest.mark.asyncio
async def test_room_created_again_keeps_its_devices(hass, mock_config_entry):
    coordinator = _coordinator(hass, mock_config_entry, remaining={"bed": BED})
    coordinator.note_room_deleted("bed", BED)
    with patch(TURN_OFF, new=AsyncMock()) as turn_off:
        await coordinator._async_switch_deleted_rooms_off({})
    turn_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_global_control_off_sends_nothing(hass, mock_config_entry):
    """A device run by hand while RoomMind control is off stays on."""
    coordinator = _coordinator(hass, mock_config_entry)
    coordinator.note_room_deleted("bed", BED)
    with patch(TURN_OFF, new=AsyncMock()) as turn_off:
        await coordinator._async_switch_deleted_rooms_off({"climate_control_active": False})
    turn_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_room_with_control_disabled_sends_nothing(hass, mock_config_entry):
    coordinator = _coordinator(hass, mock_config_entry)
    assert coordinator.note_room_deleted("bed", {**BED, "climate_control_enabled": False}) is False
    with patch(TURN_OFF, new=AsyncMock()) as turn_off:
        await coordinator._async_switch_deleted_rooms_off({})
    turn_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_room_deleted_while_the_cycle_runs_is_not_processed(hass, mock_config_entry):
    """The cycle's snapshot still lists the room, the live store no longer does: no commands for it."""
    room = {**SAMPLE_ROOM}
    store = _make_store_mock({room["area_id"]: room})
    store.get_room = MagicMock(return_value=None)
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    with patch.object(coordinator, "_async_process_room", new=AsyncMock()) as process:
        await coordinator._async_update_data()
    process.assert_not_awaited()
