"""Learned AC head offset applied to setpoints (#461), only with the setting on."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.control.mpc_controller import MPCController, async_idle_device
from custom_components.roommind.control.thermal_model import RoomModelManager

from .conftest import build_hass, make_room

AC = "climate.hp"


def _hass(state="off", **attrs):
    hass = build_hass()
    ac = MagicMock()
    ac.state = state
    ac.attributes = {"hvac_modes": ["heat", "cool", "off"], "temperature": 20.0, "target_temp_step": 1, **attrs}
    hass.states.get = MagicMock(return_value=ac)
    return hass


def _ctrl(hass, room, offsets=None, *, external=True):
    return MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=external,
        head_offsets=offsets,
    )


def _temps(hass):
    return [c[0][2]["temperature"] for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]


OFFSETS = {("climate.hp", "heat"): 1.0, ("climate.hp", "cool"): 1.5, ("climate.hp", "idle"): 2.0}


def _lookup(eid, intent):
    return OFFSETS.get((eid, intent), 0.0)


@pytest.mark.asyncio
async def test_off_sends_todays_heating_setpoint():
    plain, shifted = _hass(), _hass()
    room = make_room(thermostats=[], acs=[AC])
    await _ctrl(plain, room).async_apply("heating", 21.0, power_fraction=0.5, current_temp=18.0)
    await _ctrl(shifted, room, _lookup).async_apply("heating", 21.0, power_fraction=0.5, current_temp=18.0)
    assert _temps(plain) == [24.0]  # 18 + 0.5 * (30 - 18)
    # A warm-reading head: the unit is asked 1 K more so it stops at the same room temperature
    assert _temps(shifted) == [25.0]


@pytest.mark.asyncio
async def test_cooling_setpoint_follows_the_cool_offset():
    plain, shifted = _hass(), _hass()
    room = make_room(thermostats=[], acs=[AC])
    await _ctrl(plain, room).async_apply("cooling", 24.0, power_fraction=0.5, current_temp=26.0)
    await _ctrl(shifted, room, _lookup).async_apply("cooling", 24.0, power_fraction=0.5, current_temp=26.0)
    assert _temps(shifted)[0] == pytest.approx(_temps(plain)[0] + 1.5, abs=0.5)  # step 1 rounding
    assert _temps(shifted)[0] > _temps(plain)[0]


@pytest.mark.asyncio
async def test_direct_ac_and_managed_mode_are_not_shifted():
    room = make_room(thermostats=[], acs=[AC])
    room["devices"][0]["setpoint_mode"] = "direct"
    hass = _hass()
    await _ctrl(hass, room, _lookup).async_apply("heating", 21.0, power_fraction=0.5, current_temp=18.0)
    assert _temps(hass) == [21.0]
    managed = _hass()
    await _ctrl(managed, make_room(thermostats=[], acs=[AC]), _lookup, external=False).async_apply(
        "heating", 21.0, power_fraction=0.5, current_temp=18.0
    )
    assert _temps(managed) == [21.0]


@pytest.mark.asyncio
async def test_setback_adds_the_idle_offset():
    devices = [{"entity_id": AC, "type": "ac", "role": "auto", "idle_action": "setback"}]
    targets = TargetTemps(heat=21.0, cool=24.0)
    plain, shifted = _hass("heat"), _hass("heat")
    await async_idle_device(plain, AC, devices, targets=targets)
    await async_idle_device(shifted, AC, devices, targets=targets, head_offset=2.0)
    assert _temps(shifted)[0] == _temps(plain)[0] + 2.0


@pytest.mark.asyncio
async def test_controller_idle_uses_the_idle_offset_only_when_on():
    room = make_room(thermostats=[], acs=[AC])
    room["devices"][0]["idle_action"] = "setback"
    plain, shifted = _hass("heat"), _hass("heat")
    await _ctrl(plain, room).async_apply("idle", TargetTemps(heat=21.0, cool=24.0), current_temp=21.5)
    await _ctrl(shifted, room, _lookup).async_apply("idle", TargetTemps(heat=21.0, cool=24.0), current_temp=21.5)
    assert _temps(plain) and _temps(shifted)
    assert _temps(shifted)[0] == _temps(plain)[0] + 2.0
