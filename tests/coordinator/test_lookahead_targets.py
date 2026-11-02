"""The MPC lookahead follows the same target pipeline as the live target."""

from __future__ import annotations

from datetime import datetime

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.control.mpc_controller import _with_deadband
from custom_components.roommind.coordinator import RoomMindCoordinator

BASE = TargetTemps(heat=20.0, cool=26.0)


def _resolver(room, settings=None, presence_away=False, base=BASE):
    return RoomMindCoordinator._lookahead_resolver(lambda _ts: base, room, settings or {}, presence_away)


def _ts(hour: int) -> float:
    return datetime(2026, 11, 3, hour, 30).astimezone().timestamp()


def test_night_setback_reaches_the_planner():
    room = {"night_mode_enabled": True, "night_start": "22:00", "night_end": "07:00", "night_ramp_minutes": 0}
    resolver = _resolver(room)
    assert resolver(_ts(12)).heat == 20.0
    assert resolver(_ts(2)).heat == 19.5


def test_profile_does_not_beat_an_active_override():
    room = {"active_profile": "work", "override_heat": 22.5, "override_cool": None, "override_until": None}
    resolver = _resolver(room, base=TargetTemps(heat=22.5, cool=None))
    assert resolver(_ts(12)).heat == 22.5


def test_profile_applies_without_override():
    room = {"active_profile": "work", "comfort_profiles": {"work": {"heat_target": 21.0, "cool_target": 25.0}}}
    assert _resolver(room)(_ts(12)) == TargetTemps(heat=21.0, cool=25.0)


def test_manual_heat_uses_logical_target():
    room = {"room_hvac_mode": "heat", "logical_heat_target": 22.0, "logical_cool_target": 26.0}
    assert _resolver(room)(_ts(12)) == TargetTemps(heat=22.0, cool=None)


def test_single_point_targets_get_a_dead_band():
    assert _with_deadband(21.0, 21.0) == (20.5, 21.5)
    assert _with_deadband(20.0, 26.0) == (20.0, 26.0)
