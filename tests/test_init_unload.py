"""Tests for config-entry unload (panel cleanup)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind import async_unload_entry
from custom_components.roommind.const import DOMAIN


def _hass(entries):
    hass = MagicMock()
    coordinator = MagicMock()
    hass.data = {DOMAIN: {"store": MagicMock(), "panel_registered": True, "coordinator": coordinator}}
    for entry in entries:
        hass.data[DOMAIN][entry.entry_id] = coordinator
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_entries = MagicMock(return_value=entries)
    return hass


@pytest.mark.asyncio
async def test_unload_last_entry_removes_panel():
    """The store/flags in hass.data must not keep the panel registered (A13)."""
    entry = MagicMock(entry_id="e1")
    hass = _hass([entry])

    with patch("custom_components.roommind.async_remove_panel") as remove:
        assert await async_unload_entry(hass, entry)

    remove.assert_called_once_with(hass, "roommind")
    assert "panel_registered" not in hass.data[DOMAIN]


@pytest.mark.asyncio
async def test_unload_keeps_panel_while_another_entry_is_loaded():
    entry, other = MagicMock(entry_id="e1"), MagicMock(entry_id="e2")
    hass = _hass([entry, other])

    with patch("custom_components.roommind.async_remove_panel") as remove:
        assert await async_unload_entry(hass, entry)

    remove.assert_not_called()
    assert hass.data[DOMAIN]["panel_registered"] is True
