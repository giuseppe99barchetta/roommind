"""Tests for room climate capability and auxiliary-mode helpers."""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

from custom_components.roommind.managers.room_climate import async_apply_ac_auxiliary_mode


def _room(mode: str = "fan_only", **overrides):
    room = {
        "devices": [{"entity_id": "climate.ac", "type": "ac"}],
        "room_hvac_mode": mode,
        "room_fan_mode": "low",
        "room_swing_mode": "vertical",
        "room_swing_horizontal_mode": "middle",
    }
    room.update(overrides)
    return room


def _hass(mode: str, **attributes):
    hass = MagicMock()
    hass.states.get.return_value = MagicMock(
        state=mode,
        attributes={
            "fan_mode": "low",
            "swing_mode": "vertical",
            "swing_horizontal_mode": "middle",
            **attributes,
        },
    )
    hass.services.async_call = AsyncMock()
    return hass


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["fan_only", "dry"])
async def test_auxiliary_mode_does_nothing_when_physical_settings_match(mode):
    hass = _hass(mode)

    await async_apply_ac_auxiliary_mode(hass, _room(mode))

    hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_auxiliary_mode_changes_only_fan_mode_when_it_differs():
    hass = _hass("fan_only", fan_mode="high")

    await async_apply_ac_auxiliary_mode(hass, _room())

    hass.services.async_call.assert_awaited_once_with(
        "climate",
        "set_fan_mode",
        {"entity_id": "climate.ac", "fan_mode": "low"},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_auxiliary_mode_changes_only_swing_mode_when_it_differs():
    hass = _hass("fan_only", swing_mode="off")

    await async_apply_ac_auxiliary_mode(hass, _room())

    hass.services.async_call.assert_awaited_once_with(
        "climate",
        "set_swing_mode",
        {"entity_id": "climate.ac", "swing_mode": "vertical"},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_auxiliary_mode_changes_only_horizontal_swing_when_it_differs():
    hass = _hass("fan_only", swing_horizontal_mode="left")

    await async_apply_ac_auxiliary_mode(hass, _room())

    hass.services.async_call.assert_awaited_once_with(
        "climate",
        "set_swing_horizontal_mode",
        {"entity_id": "climate.ac", "swing_horizontal_mode": "middle"},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["fan_only", "dry"])
async def test_persisted_auxiliary_mode_does_not_turn_on_physical_ac(mode):
    hass = _hass("off")

    await async_apply_ac_auxiliary_mode(hass, _room(mode))

    hass.services.async_call.assert_not_awaited()
