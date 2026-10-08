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
