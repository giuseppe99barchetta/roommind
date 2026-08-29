"""Tests for RoomMind configuration selectors."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.const import DOMAIN
from custom_components.roommind.select import RoomMindDryEntityTypeSelect


@pytest.mark.asyncio
async def test_dry_entity_type_select_switches_to_dehumidifier():
    """Selecting Dehumidifier persists the choice and swaps the endpoint."""
    coordinator = MagicMock()
    coordinator.hass = MagicMock()
    store = MagicMock()
    store.get_room.return_value = {"dry_entity_type": "switch"}
    store.async_update_room = AsyncMock(return_value={"dry_entity_type": "humidifier"})
    coordinator.hass.data = {DOMAIN: {"store": store}}
    coordinator._async_sync_dry_entity = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    entity = RoomMindDryEntityTypeSelect(coordinator, "bedroom")

    assert entity.current_option == "switch"

    await entity.async_select_option("humidifier")

    store.async_update_room.assert_awaited_once_with("bedroom", {"dry_entity_type": "humidifier"})
    coordinator._async_sync_dry_entity.assert_awaited_once_with(
        "bedroom", {"dry_entity_type": "humidifier"}
    )
    coordinator.async_request_refresh.assert_awaited_once()
