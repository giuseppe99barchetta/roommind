"""The boiler interlock depends on HA readback, not service success."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.managers.boiler_manager import BoilerManager, BoilerState


def _settings():
    return {
        "climate_control_active": True,
        "boiler_entity": "climate.boiler",
        "hydraulic_bypass_entities": ["climate.bypass"],
        "hydraulic_bypass_open_temperature": 28,
        "boiler_startup_delay_seconds": 30,
    }


@pytest.mark.asyncio
async def test_bypass_must_report_heat_and_requested_setpoint_before_boiler_starts():
    states = {
        "climate.bypass": SimpleNamespace(state="off", attributes={"temperature": 7}),
        "climate.boiler": SimpleNamespace(state="off", attributes={}),
    }
    hass = MagicMock()
    hass.states.get.side_effect = states.get
    hass.services.async_call = AsyncMock()
    mgr = BoilerManager(hass)
    settings = _settings()

    with patch("custom_components.roommind.managers.boiler_manager.monotonic", return_value=100.0):
        await mgr.async_reconcile(settings, {"studio"})
    assert mgr.state == BoilerState.PREOPENING
    assert not mgr.path_safe
    assert not any(c.args[2].get("entity_id") == "climate.boiler" for c in hass.services.async_call.call_args_list)

    # No repeated Zigbee writes within the retry window, no boiler activation.
    hass.services.async_call.reset_mock()
    with patch("custom_components.roommind.managers.boiler_manager.monotonic", return_value=131.0):
        await mgr.async_reconcile(settings, {"studio"})
    assert not mgr.path_safe
    hass.services.async_call.assert_not_called()

    states["climate.bypass"] = SimpleNamespace(state="heat", attributes={"temperature": 28})
    with patch("custom_components.roommind.managers.boiler_manager.monotonic", return_value=160.0):
        await mgr.async_reconcile(settings, {"studio"})
    assert mgr.path_safe
    assert mgr.state == BoilerState.ON
    assert any(
        c.args[2] == {"entity_id": "climate.boiler", "hvac_mode": "heat"}
        for c in hass.services.async_call.call_args_list
    )


@pytest.mark.asyncio
async def test_bypass_fails_closed_if_no_acknowledgement_after_grace():
    hass = MagicMock()
    hass.states.get.side_effect = lambda eid: SimpleNamespace(state="off", attributes={"temperature": 7})
    hass.services.async_call = AsyncMock()
    mgr = BoilerManager(hass)
    with patch("custom_components.roommind.managers.boiler_manager.monotonic", return_value=100.0):
        await mgr.async_reconcile(_settings(), {"studio"})
    with patch("custom_components.roommind.managers.boiler_manager.monotonic", return_value=191.0):
        await mgr.async_reconcile(_settings(), {"studio"})
    assert mgr.state == BoilerState.FAULT
    assert mgr.path_safe is False
    assert not any(
        c.args[2] == {"entity_id": "climate.boiler", "hvac_mode": "heat"}
        for c in hass.services.async_call.call_args_list
    )


@pytest.mark.asyncio
async def test_failed_bypass_release_is_retried_next_tick():
    """A failed release call must not mark the bypass released (A8)."""
    states = {
        "climate.bypass": SimpleNamespace(state="heat", attributes={"temperature": 28.0}),
        "climate.boiler": SimpleNamespace(state="off", attributes={}),
    }
    hass = MagicMock()
    hass.states.get.side_effect = states.get
    hass.services.async_call = AsyncMock(side_effect=RuntimeError("zigbee timeout"))
    mgr = BoilerManager(hass)
    settings = _settings()

    await mgr.async_reconcile(settings, set())
    assert not mgr._bypass_released

    hass.services.async_call = AsyncMock()
    await mgr.async_reconcile(settings, set())
    released = [
        c
        for c in hass.services.async_call.call_args_list
        if c.args[2] == {"entity_id": "climate.bypass", "hvac_mode": "off"}
    ]
    assert len(released) == 1
    assert mgr._bypass_released


@pytest.mark.asyncio
async def test_unavailable_bypass_release_is_retried_when_it_returns():
    """CR-08: an unavailable bypass keeps the release pending; released or already-off
    bypasses are not re-commanded on every tick."""
    states = {
        "climate.bypass": SimpleNamespace(state="heat", attributes={"temperature": 28.0}),
        "climate.bypass2": SimpleNamespace(state="unavailable", attributes={}),
        "climate.bypass3": SimpleNamespace(state="off", attributes={}),
        "climate.boiler": SimpleNamespace(state="off", attributes={}),
    }
    hass = MagicMock()
    hass.states.get.side_effect = states.get
    hass.services.async_call = AsyncMock()
    mgr = BoilerManager(hass)
    settings = {**_settings(), "hydraulic_bypass_entities": ["climate.bypass", "climate.bypass2", "climate.bypass3"]}

    def _offs():
        return [
            c.args[2]["entity_id"]
            for c in hass.services.async_call.call_args_list
            if c.args[1] == "set_hvac_mode" and c.args[2].get("hvac_mode") == "off"
        ]

    await mgr.async_reconcile(settings, set())
    assert _offs() == ["climate.bypass"]
    assert not mgr._bypass_released

    hass.services.async_call.reset_mock()
    await mgr.async_reconcile(settings, set())
    assert _offs() == []  # still pending, but no OFF spam to the released bypass
    assert not mgr._bypass_released

    states["climate.bypass2"] = SimpleNamespace(state="heat", attributes={"temperature": 28.0})
    await mgr.async_reconcile(settings, set())
    assert _offs() == ["climate.bypass2"]
    assert mgr._bypass_released
