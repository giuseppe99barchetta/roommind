"""Resting rooms (#494): the area registry listener."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind import async_track_area_changes
from custom_components.roommind.const import DOMAIN


@pytest.mark.asyncio
@pytest.mark.parametrize(("action", "method"), [("remove", "async_room_paused"), ("create", "async_room_resumed")])
async def test_area_registry_events_pause_and_resume_a_stored_room(hass, action, method):
    store = MagicMock()
    store.get_room = MagicMock(side_effect=lambda area_id: {"area_id": area_id} if area_id == "bed" else None)
    coordinator = MagicMock()
    setattr(coordinator, method, AsyncMock())
    hass.data = {DOMAIN: {"store": store, "coordinator": coordinator}}
    hass.bus.async_listen = MagicMock(return_value=MagicMock())
    unsub = async_track_area_changes(hass)
    callback = hass.bus.async_listen.call_args[0][1]
    await callback(SimpleNamespace(data={"action": action, "area_id": "bed"}))
    await callback(SimpleNamespace(data={"action": action, "area_id": "not_a_room"}))
    await callback(SimpleNamespace(data={"action": "update", "area_id": "bed"}))
    getattr(coordinator, method).assert_awaited_once_with("bed")
    assert unsub is hass.bus.async_listen.return_value
