"""Boiler start quorum, run/off guards, fault recovery and bypass ownership."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.managers.boiler_manager import BoilerManager, BoilerState, bypass_entities

MONO = "custom_components.roommind.managers.boiler_manager.monotonic"


def _settings(**overrides):
    settings = {
        "climate_control_active": True,
        "boiler_entity": "climate.boiler",
        "hydraulic_bypass_entities": ["climate.bypass"],
        "hydraulic_bypass_open_temperature": 28,
        "boiler_startup_delay_seconds": 30,
        "boiler_shutdown_delay_seconds": 60,
        "boiler_min_run_minutes": 5,
        "boiler_min_off_minutes": 3,
        "boiler_fault_retry_minutes": 5,
        "hydraulic_bypass_child_lock": False,
    }
    settings.update(overrides)
    return settings


def _hass(bypass_state="heat", bypass_temp=28):
    states = {
        "climate.bypass": SimpleNamespace(state=bypass_state, attributes={"temperature": bypass_temp}),
        "climate.boiler": SimpleNamespace(state="off", attributes={}),
    }
    hass = MagicMock()
    hass.states.get.side_effect = states.get
    hass.services.async_call = AsyncMock()
    return hass, states


def _boiler_calls(hass, mode):
    return [
        c
        for c in hass.services.async_call.call_args_list
        if c.args[2] == {"entity_id": "climate.boiler", "hvac_mode": mode}
    ]


async def _tick(mgr, settings, demand, t):
    with patch(MONO, return_value=t):
        await mgr.async_reconcile(settings, set(demand))


@pytest.mark.asyncio
async def test_single_room_below_quorum_never_starts_boiler_and_closes_bypass():
    hass, _ = _hass()
    mgr = BoilerManager(hass)
    settings = _settings(boiler_min_demand_rooms=2)

    await _tick(mgr, settings, {"bagno"}, 100.0)
    await _tick(mgr, settings, {"bagno"}, 200.0)

    assert mgr.state == BoilerState.OFF
    assert not mgr.heat_available
    assert not _boiler_calls(hass, "heat")
    # The bypass is idled once (it may have been left open), not every tick.
    releases = [
        c
        for c in hass.services.async_call.call_args_list
        if c.args[2] == {"entity_id": "climate.bypass", "hvac_mode": "off"}
    ]
    assert len(releases) == 1


@pytest.mark.asyncio
async def test_quorum_starts_boiler_and_any_demand_keeps_it_running():
    hass, _ = _hass()
    mgr = BoilerManager(hass)
    settings = _settings(boiler_min_demand_rooms=2)

    await _tick(mgr, settings, {"bagno", "studio"}, 100.0)
    assert mgr.state == BoilerState.PREOPENING
    assert mgr.heat_available
    await _tick(mgr, settings, {"bagno", "studio"}, 131.0)
    assert mgr.state == BoilerState.ON

    # One room satisfied: below the start quorum, but the boiler keeps running.
    await _tick(mgr, settings, {"bagno"}, 1000.0)
    assert mgr.state == BoilerState.ON


@pytest.mark.asyncio
async def test_quorum_lost_during_preopening_aborts_without_firing():
    hass, _ = _hass(bypass_state="off", bypass_temp=7)
    mgr = BoilerManager(hass)
    settings = _settings(boiler_min_demand_rooms=2)

    await _tick(mgr, settings, {"bagno", "studio"}, 100.0)
    await _tick(mgr, settings, {"bagno"}, 120.0)

    assert mgr.state == BoilerState.OFF
    assert not _boiler_calls(hass, "heat")


@pytest.mark.asyncio
async def test_minimum_run_time_holds_boiler_on_after_demand_drops():
    hass, _ = _hass()
    mgr = BoilerManager(hass)
    settings = _settings()

    await _tick(mgr, settings, {"studio"}, 100.0)
    await _tick(mgr, settings, {"studio"}, 131.0)
    assert mgr.state == BoilerState.ON

    await _tick(mgr, settings, set(), 200.0)  # 69 s after start
    assert mgr.state == BoilerState.ON
    assert not _boiler_calls(hass, "off")

    await _tick(mgr, settings, set(), 131.0 + 300.0)
    assert mgr.state == BoilerState.POSTSTOP
    assert _boiler_calls(hass, "off")


@pytest.mark.asyncio
async def test_minimum_off_time_delays_restart():
    hass, _ = _hass()
    mgr = BoilerManager(hass)
    settings = _settings(boiler_min_run_minutes=0)

    await _tick(mgr, settings, {"studio"}, 100.0)
    await _tick(mgr, settings, {"studio"}, 131.0)
    await _tick(mgr, settings, set(), 140.0)
    assert mgr.state == BoilerState.POSTSTOP

    await _tick(mgr, settings, {"studio"}, 150.0)  # 10 s after stopping
    assert mgr.state == BoilerState.POSTSTOP
    await _tick(mgr, settings, {"studio"}, 140.0 + 181.0)
    assert mgr.state == BoilerState.PREOPENING


@pytest.mark.asyncio
async def test_lost_bypass_faults_once_then_retries_and_recovers():
    hass, states = _hass()
    mgr = BoilerManager(hass)
    settings = _settings()

    await _tick(mgr, settings, {"studio"}, 100.0)
    await _tick(mgr, settings, {"studio"}, 131.0)
    assert mgr.state == BoilerState.ON

    # Someone presses the valve: it drops to its own schedule mode.
    states["climate.bypass"] = SimpleNamespace(state="auto", attributes={"temperature": 28})
    await _tick(mgr, settings, {"studio"}, 200.0)
    assert mgr.state == BoilerState.FAULT
    assert mgr.fault_reason
    assert len(_boiler_calls(hass, "off")) == 1

    # No OFF spam while faulted.
    await _tick(mgr, settings, {"studio"}, 260.0)
    assert len(_boiler_calls(hass, "off")) == 1

    # After the retry window the start sequence runs again and recovers.
    states["climate.bypass"] = SimpleNamespace(state="heat", attributes={"temperature": 28})
    await _tick(mgr, settings, {"studio"}, 200.0 + 300.0)
    assert mgr.state == BoilerState.OFF
    await _tick(mgr, settings, {"studio"}, 530.0)
    assert mgr.state == BoilerState.PREOPENING
    await _tick(mgr, settings, {"studio"}, 561.0)
    assert mgr.state == BoilerState.ON
    assert mgr.fault_reason is None


@pytest.mark.asyncio
async def test_fault_clears_when_demand_ends():
    hass, _ = _hass(bypass_state="off", bypass_temp=7)
    mgr = BoilerManager(hass)
    settings = _settings()

    await _tick(mgr, settings, {"studio"}, 100.0)
    await _tick(mgr, settings, {"studio"}, 191.0)
    assert mgr.state == BoilerState.FAULT

    await _tick(mgr, settings, set(), 200.0)
    assert mgr.state == BoilerState.OFF
    assert mgr.fault_reason is None


def test_bypass_entities_only_when_a_boiler_is_configured():
    assert bypass_entities({"hydraulic_bypass_entities": ["climate.bypass"]}) == set()
    assert bypass_entities(_settings()) == {"climate.bypass"}


@pytest.mark.asyncio
async def test_child_lock_is_enabled_on_bypass_when_requested():
    hass, states = _hass()
    states["switch.bypass_child_lock"] = SimpleNamespace(state="off", attributes={})
    mgr = BoilerManager(hass)
    mgr._child_lock_switches = MagicMock(return_value=["switch.bypass_child_lock"])

    await _tick(mgr, _settings(hydraulic_bypass_child_lock=True), {"studio"}, 100.0)

    assert any(
        c.args[:3] == ("switch", "turn_on", {"entity_id": "switch.bypass_child_lock"})
        for c in hass.services.async_call.call_args_list
    )


@pytest.mark.asyncio
async def test_child_lock_untouched_when_disabled():
    hass, states = _hass()
    states["switch.bypass_child_lock"] = SimpleNamespace(state="off", attributes={})
    mgr = BoilerManager(hass)
    mgr._child_lock_switches = MagicMock(return_value=["switch.bypass_child_lock"])

    await _tick(mgr, _settings(hydraulic_bypass_child_lock=False), {"studio"}, 100.0)

    assert not any(c.args[0] == "switch" for c in hass.services.async_call.call_args_list)
