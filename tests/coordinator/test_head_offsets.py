"""Coordinator side of the learned AC head offset (#461): power as the running signal, persistence, gate."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import HEAD_OFFSET_MIN_SAMPLES, HEAD_OFFSET_SETTLE_S, MODE_HEATING, MODE_IDLE
from custom_components.roommind.control.mpc_controller import MPCController

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

AC = "climate.living_ac"
POWER = "sensor.living_ac_power"
COORD = "custom_components.roommind.coordinator"


def _st(state, **attrs):
    return SimpleNamespace(state=state, attributes=attrs, last_reported=datetime.now(UTC))


def _room():
    return {
        **SAMPLE_ROOM,
        "devices": [{"entity_id": AC, "type": "ac", "role": "auto", "power_sensor_entity_id": POWER}],
    }


def _coord(hass, mock_config_entry, states=None, settings=None):
    room = _room()
    store = _make_store_mock(rooms={room["area_id"]: room}, settings=settings or {})
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()
    if states is not None:
        hass.states.get = MagicMock(side_effect=states.get)
    return _create_coordinator(hass, mock_config_entry), room


@pytest.mark.parametrize(
    ("state", "watts", "room_mode", "expected"),
    [
        (_st("heat"), 650.0, MODE_IDLE, "heat"),  # Hisense: no hvac_action, compressor running
        (_st("heat"), 22.0, MODE_HEATING, "idle"),  # standby draw: stopped
        (_st("cool"), 700.0, MODE_IDLE, "cool"),
        (_st("auto"), 700.0, MODE_HEATING, "heat"),  # auto: the mode RoomMind runs the room in
        (_st("auto"), 700.0, MODE_IDLE, None),
        (_st("heat"), None, MODE_HEATING, None),  # no (fresh) power reading: nothing to learn
        (_st("off"), 700.0, MODE_HEATING, None),
        (_st("fan_only"), 300.0, MODE_IDLE, None),
        (_st("heat", hvac_action="heating"), None, MODE_IDLE, "heat"),  # hvac_action wins
        (_st("heat", hvac_action="idle"), 700.0, MODE_HEATING, "idle"),
        (None, 700.0, MODE_HEATING, None),
    ],
)
def test_state_from_power_or_hvac_action(hass, mock_config_entry, state, watts, room_mode, expected):
    coordinator, _ = _coord(hass, mock_config_entry)
    assert coordinator._head_offset_state(state, watts, room_mode) == expected


def test_running_hisense_learns_its_warm_head(hass, mock_config_entry):
    states = {AC: _st("heat", current_temperature=23.0), POWER: _st("650")}
    coordinator, room = _coord(hass, mock_config_entry, states)
    with patch(f"{COORD}.time") as clock:
        for i in range(HEAD_OFFSET_MIN_SAMPLES + 1):
            clock.time.return_value = 1000.0 + (HEAD_OFFSET_SETTLE_S if i else 0) + 30 * i
            coordinator._observe_head_offsets(room, 21.0, MODE_HEATING)
    assert coordinator._head_offsets.offset(AC, "heat") == pytest.approx(2.0)


def test_stale_or_missing_power_learns_nothing(hass, mock_config_entry):
    stale = _st("650")
    stale.last_reported = datetime(2020, 1, 1, tzinfo=UTC)
    coordinator, room = _coord(hass, mock_config_entry, {AC: _st("heat", current_temperature=23.0), POWER: stale})
    with patch(f"{COORD}.time") as clock:
        for i in range(HEAD_OFFSET_MIN_SAMPLES + 1):
            clock.time.return_value = 1000.0 + HEAD_OFFSET_SETTLE_S * 2 * i
            coordinator._observe_head_offsets(room, 21.0, MODE_HEATING)
    assert coordinator._head_offsets.get_state() == {}


def test_display_shift_only_when_enabled(hass, mock_config_entry):
    coordinator, room = _coord(hass, mock_config_entry)
    coordinator._head_offsets.load_state({AC: {"heat": [1.0, 50]}})
    assert coordinator._ac_display_shift(room, {}, MODE_HEATING) == 0.0
    assert coordinator._ac_display_shift(room, {"ac_head_offset_enabled": True}, MODE_HEATING) == 1.0
    assert coordinator._ac_display_shift(room, {"ac_head_offset_enabled": True}, MODE_IDLE) == 0.0
    sp = coordinator._compute_device_setpoint(MODE_HEATING, 0.5, 18.0, 21.0, True, has_thermostats=False, has_acs=True)
    shifted = coordinator._compute_device_setpoint(
        MODE_HEATING, 0.5, 18.0, 21.0, True, has_thermostats=False, has_acs=True, ac_shift=1.0
    )
    assert shifted == sp + 1.0


def test_orchestrated_display_uses_the_shown_acs_own_offset(hass, mock_config_entry):
    coordinator, _ = _coord(hass, mock_config_entry)
    plan = SimpleNamespace(
        commands=[
            SimpleNamespace(entity_id=AC, device_type="ac", active=True, power_fraction=0.5),
            SimpleNamespace(entity_id="climate.other_ac", device_type="ac", active=False, power_fraction=0.0),
        ]
    )
    base = coordinator._compute_device_setpoint_orchestrated(plan, 18.0, 21.0, None, None)
    shown = coordinator._compute_device_setpoint_orchestrated(
        plan, 18.0, 21.0, None, None, ac_shifts={AC: 1.0, "climate.other_ac": 2.0}
    )
    assert shown == base + 1.0


async def _cycle(hass, mock_config_entry, settings):
    room = {**_room(), "temperature_sensor": "sensor.living_room_temp"}
    store = _make_store_mock(rooms={room["area_id"]: room}, settings={"climate_control_active": True, **settings})
    store.get_settings.return_value = {
        **store.get_settings.return_value,
        "ac_head_offsets": {AC: {"heat": [1.0, 50], "cool": [1.0, 50], "idle": [1.0, 50]}},
    }
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()
    hass.states.get = make_mock_states_get(
        temp="18.0", schedule_state="on", schedule_attrs={"current_event": True, "friendly_name": "Heat"}
    )
    coordinator = _create_coordinator(hass, mock_config_entry)
    with patch(f"{COORD}.MPCController", wraps=MPCController) as ctrl:
        await coordinator._async_update_data()
    return ctrl.call_args.kwargs["head_offsets"], coordinator


@pytest.mark.asyncio
async def test_controller_gets_offsets_only_with_the_setting(hass, mock_config_entry):
    off, coordinator = await _cycle(hass, mock_config_entry, {})
    assert off is None
    assert coordinator._head_offsets.offset(AC, "heat") == 1.0  # loaded and learning all the same
    on, coordinator = await _cycle(hass, mock_config_entry, {"ac_head_offset_enabled": True})
    assert on is not None and on(AC, "heat") == 1.0


@pytest.mark.asyncio
async def test_learned_offsets_are_saved_and_pruned(hass, mock_config_entry):
    coordinator, room = _coord(hass, mock_config_entry, settings={"ac_head_offsets": {}})
    store = hass.data["roommind"]["store"]
    store.get_settings.return_value = {
        **store.get_settings.return_value,
        "ac_head_offsets": {AC: {"heat": [1.0, 50]}, "climate.gone": {"idle": [1.0, 50]}},
    }
    coordinator._head_offsets.load_state({AC: {"heat": [1.0, 50]}, "climate.gone": {"idle": [1.0, 50]}})
    coordinator._head_offsets.dirty = True
    hass.states.get = make_mock_states_get()
    coordinator._thermal_save_count = -1  # this cycle is a save cycle
    await coordinator._async_update_data()
    saved = [c.args[0] for c in store.async_save_settings.call_args_list if "ac_head_offsets" in c.args[0]]
    assert saved and set(saved[-1]["ac_head_offsets"]) == {AC}
