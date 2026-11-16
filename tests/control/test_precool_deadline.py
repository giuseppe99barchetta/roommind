"""Pre-cooling starts as late as possible so a falling cool target is reached in time."""

from __future__ import annotations

from custom_components.roommind.const import MODE_COOLING, MODE_HEATING, MODE_IDLE
from custom_components.roommind.control.mpc_optimizer import MPCOptimizer
from custom_components.roommind.control.thermal_model import RCModel

# A small AC in a warm room: ~1.2 K/h net at full power with 32 °C outside
SMALL_AC = RCModel(C=1.0, U=0.05, Q_heat=3.0, Q_cool=2.0)


def _plan(
    T_room,
    fall_at,
    *,
    n=72,
    eco=27.0,
    comfort=24.0,
    initial_mode=MODE_IDLE,
    can_cool=True,
    preheat_max_blocks=None,
    schedule_cool=None,
    cool=None,
):
    opt = MPCOptimizer(
        SMALL_AC, can_heat=False, can_cool=can_cool, min_run_blocks=2, preheat_max_blocks=preheat_max_blocks
    )
    cool = cool if cool is not None else [eco] * fall_at + [comfort] * (n - fall_at)
    return opt.optimize(
        T_room=T_room,
        T_outdoor_series=[32.0] * n,
        heat_target_series=[min(T_room, c) for c in cool],
        cool_target_series=cool,
        dt_minutes=5,
        initial_mode=initial_mode,
    )


def test_cools_now_when_waiting_would_miss_the_comfort_block():
    plan = _plan(26.8, fall_at=18)  # -2.8 K in 1.5 h: full power needs ~1.6 h
    assert plan.actions[0] == MODE_COOLING
    assert plan.power_fractions[0] == 1.0
    assert plan.preheat_blocks == 18


def test_waits_while_a_later_start_still_reaches_the_target():
    plan = _plan(24.5, fall_at=60)  # -0.5 K in 5 h: plenty of time
    assert plan.actions[0] == MODE_IDLE
    assert plan.preheat_blocks == 0


def test_no_fall_no_precool():
    plan = _plan(26.8, fall_at=72)
    assert plan.actions[0] == MODE_IDLE
    assert plan.preheat_blocks == 0


def test_room_already_below_the_coming_target_is_no_precool():
    plan = _plan(23.5, fall_at=12)
    assert plan.actions[0] == MODE_IDLE
    assert plan.preheat_blocks == 0


def test_running_precool_keeps_going_at_the_deadline_edge():
    # Waiting one block would still make it, so a fresh start waits ...
    assert _plan(24.6, fall_at=10).actions[0] == MODE_IDLE
    # ... but a pre-cool already running keeps going instead of toggling at the edge
    plan = _plan(24.6, fall_at=10, initial_mode=MODE_COOLING)
    assert plan.actions[0] == MODE_COOLING
    assert plan.preheat_blocks == 10


def test_running_precool_stops_at_the_target():
    plan = _plan(24.05, fall_at=24, initial_mode=MODE_COOLING)
    assert plan.actions[0] == MODE_IDLE


def test_no_precool_without_cooling():
    plan = _plan(26.8, fall_at=24, can_cool=False)
    assert plan.actions[0] == MODE_IDLE
    assert plan.preheat_blocks == 0


def test_room_switch_and_slider_limit_the_precool_lead():
    assert _plan(26.8, fall_at=18, preheat_max_blocks=0).actions[0] == MODE_IDLE
    assert _plan(26.8, fall_at=18, preheat_max_blocks=12).actions[0] == MODE_IDLE
    assert _plan(26.8, fall_at=18, preheat_max_blocks=24).actions[0] == MODE_COOLING


def test_heat_deadline_wins_over_cooling():
    """Rooms that can do both: a coming heat rise keeps its pre-heat, no cooling hypothesis on top."""
    opt = MPCOptimizer(SMALL_AC, can_heat=True, can_cool=True, min_run_blocks=2)
    n = 72
    plan = opt.optimize(
        T_room=19.0,
        T_outdoor_series=[0.0] * n,
        heat_target_series=[17.0] * 24 + [21.0] * (n - 24),
        cool_target_series=[27.0] * 24 + [24.0] * (n - 24),
        dt_minutes=5,
        initial_mode=MODE_IDLE,
    )
    assert plan.actions[0] in (MODE_HEATING, MODE_IDLE)


def test_cheap_charge_is_no_precool_target():
    """A cheap stretch lowers the target below the schedule: charging is the cheap hours' job."""
    n = 72
    cool = [24.0] * 24 + [23.0] * (n - 24)
    schedule = [24.0] * n
    plan = _plan(24.0, fall_at=0, cool=cool, schedule_cool=schedule)
    assert plan.preheat_blocks == 0
