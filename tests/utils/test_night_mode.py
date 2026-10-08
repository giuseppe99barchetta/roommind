"""Tests for the gradual night comfort profile."""

from datetime import datetime

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.utils.night_mode import apply_night_targets, night_progress


def test_night_progress_crosses_midnight_and_ramps_gradually():
    assert night_progress(datetime(2026, 8, 29, 22, 0), "22:00", "07:00", 60) == 0
    assert night_progress(datetime(2026, 8, 29, 22, 30), "22:00", "07:00", 60) == 0.5
    assert night_progress(datetime(2026, 8, 30, 2, 0), "22:00", "07:00", 60) == 1
    assert night_progress(datetime(2026, 8, 30, 8, 0), "22:00", "07:00", 60) == 0


def test_night_targets_apply_a_partial_setback():
    room = {
        "night_mode_enabled": True,
        "night_start": "22:00",
        "night_end": "07:00",
        "night_ramp_minutes": 60,
        "night_heat_delta": -1.0,
        "night_cool_delta": 2.0,
    }

    targets, progress = apply_night_targets(room, TargetTemps(heat=21, cool=25), datetime(2026, 8, 29, 22, 30))

    assert progress == 0.5
    assert targets == TargetTemps(heat=20.5, cool=26.0)


def test_night_phase_only_when_night_mode_enabled():
    from custom_components.roommind.utils.night_mode import night_phase

    room = {"night_mode_enabled": True, "night_start": "22:00", "night_end": "07:00"}
    at = lambda h, m: datetime(2026, 10, 8, h, m)  # noqa: E731
    assert night_phase(room, at(20, 59), 60) is None
    assert night_phase(room, at(21, 0), 60) == "pre_night"
    assert night_phase(room, at(23, 50), 60) == "night"
    assert night_phase(room, at(6, 59), 60) == "night"
    assert night_phase(room, at(7, 0), 60) is None
    assert night_phase({**room, "night_mode_enabled": False}, at(23, 50), 60) is None
