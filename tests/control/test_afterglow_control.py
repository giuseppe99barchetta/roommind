"""Learned radiator afterglow in control (room switch, upstream #493), off by default."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from custom_components.roommind.const import MODE_HEATING, MODE_IDLE
from custom_components.roommind.control.mpc_optimizer import (
    LOOKAHEAD_BASE_BLOCKS,
    RADIATOR_LOOKAHEAD_TAUS,
    MPCOptimizer,
)
from custom_components.roommind.control.residual_heat import heat_min_run_blocks
from custom_components.roommind.control.thermal_model import RCModel
from custom_components.roommind.managers.residual_heat_tracker import AfterglowReading, ResidualHeatLearner

ROOM = RCModel(C=1.0, U=0.1, Q_heat=4.0, Q_cool=0.0)
N = 36


def _opt(control: bool, **kw):
    return MPCOptimizer(
        model=ROOM,
        can_heat=True,
        can_cool=False,
        heating_system_type="radiator",
        afterglow_control=control,
        residual_scale=kw.pop("scale", 6.0),
        residual_tau=kw.pop("tau", 30.0),
        **kw,
    )


def _plan(opt, T, *, target=21.0, heat_run=(60.0, 1.0), initial=MODE_HEATING, targets=None):
    return opt.optimize(
        T_room=T,
        T_outdoor_series=[5.0] * N,
        heat_target_series=targets or [target] * N,
        dt_minutes=5.0,
        initial_mode=initial,
        heat_run=heat_run,
    )


def test_switch_off_plans_exactly_as_before():
    """With the flag off a learned scale and a run in progress change nothing."""
    plain = MPCOptimizer(model=ROOM, can_heat=True, can_cool=False, heating_system_type="radiator")
    ignored = _opt(False)
    a = _plan(plain, 20.6, heat_run=None)
    b = _plan(ignored, 20.6)
    assert (a.actions, a.temperatures, a.power_fractions, a.lookahead_blocks) == (
        b.actions,
        b.temperatures,
        b.power_fractions,
        b.lookahead_blocks,
    )


def test_stored_heat_of_the_run_stops_it_early():
    """(a) Near the target a large learned afterglow carries the room: the run stops now."""
    without = _plan(_opt(False), 20.6)
    with_glow = _plan(_opt(True), 20.6)
    assert without.actions[0] == MODE_HEATING
    assert with_glow.actions[0] == MODE_IDLE


def test_stopped_run_keeps_warming_the_plan():
    plan = _plan(_opt(True), 20.6)
    stop = plan.actions.index(MODE_IDLE)
    # After the stop the plan's temperature still rises on the stored heat
    assert plan.temperatures[stop + 1] > plan.temperatures[stop]


def test_longer_lookahead_sees_the_learned_decay():
    """(c) 2 decay times past the min run; a heat-capable AC keeps the base window."""
    plan = _plan(_opt(True, tau=30.0), 20.0)
    assert plan.lookahead_blocks == 2 + int(RADIATOR_LOOKAHEAD_TAUS * 30.0 / 5.0)
    with_ac = MPCOptimizer(
        model=ROOM, can_heat=True, can_cool=True, heating_system_type="radiator", afterglow_control=True
    )
    assert _plan(with_ac, 20.0).lookahead_blocks == LOOKAHEAD_BASE_BLOCKS


def test_preheat_deadline_does_not_force_a_run_the_stored_heat_covers():
    """(b) The coming target is reached on the run's stored heat: no forced pre-heat run."""
    targets = [20.0] * 4 + [21.0] * (N - 4)
    opt = _opt(True, scale=8.0)
    opt.optimize(
        T_room=20.6,
        T_outdoor_series=[5.0] * N,
        heat_target_series=targets,
        dt_minutes=5.0,
        initial_mode=MODE_HEATING,
        heat_run=(60.0, 1.0),
    )
    common = dict(q_solar=[0.0] * N, q_occupancy=[0.0] * N, continuing=False)
    assert opt._preheat_deadline(0, 20.2, [5.0] * N, targets, 5.0, **common) > 0
    assert opt._preheat_deadline(0, 20.2, [5.0] * N, targets, 5.0, glow=((60.0, 1.0), 0.0), **common) == 0


def test_a_run_is_not_paused_and_restarted():
    """(e) IDLE now and HEATING within two blocks while a run goes on: the run continues."""
    opt = _opt(True)
    real = MPCOptimizer._evaluate_action
    calls = {"i": 0}

    def _eval(self, action, *args, **kwargs):
        cost = real(self, action, *args, **kwargs)
        # block 0 prefers idle, block 1 prefers heating
        block = calls["i"]
        if action == MODE_IDLE:
            calls["i"] += 1
            return cost - 1e6 if block == 0 else cost + 1e6
        return cost

    with patch.object(MPCOptimizer, "_evaluate_action", _eval):
        plan = _plan(opt, 20.0, target=22.0)
    assert plan.actions[0] == MODE_HEATING


@pytest.mark.parametrize(
    ("scale", "fast_heater", "system", "expected"),
    [(8.0, False, "radiator", 1), (0.2, False, "radiator", 2), (8.0, True, "radiator", 2), (8.0, False, "", 2)],
)
def test_single_block_runs_only_for_a_large_learned_afterglow(scale, fast_heater, system, expected):
    """(d) One min run's stored heat lifting the room more than 0.5 K: single-block runs."""
    blocks = heat_min_run_blocks(system, 5.0, q_heat=4.0, scale=scale, tau_minutes=30.0, fast_heater=fast_heater)
    assert blocks == expected


def test_afterglow_reading_plans_from_the_hidden_rise():
    """(f) The reading sticks at a step: the plan starts from the stopping plan, a step at most."""
    reading = AfterglowReading()
    with patch("custom_components.roommind.managers.residual_heat_tracker.time") as clock:
        clock.time.return_value = 0.0
        reading.observe("r", 20.0)
        reading.observe("r", 20.2)  # 0.2 K sensor steps
        reading.note_stop("r", 20.2, [20.2, 20.4, 20.6, 20.7], 5.0)
        clock.time.return_value = 10 * 60.0
        assert reading.estimate("r", 20.2) == pytest.approx(20.4)  # predicted 20.6, capped one step up
        assert reading.estimate("r", 20.0) == 20.0  # below the stop reading: the reading leads again
        assert reading.estimate("r", 20.2) == 20.2  # and the stop is forgotten


def test_paused_learning_keeps_the_run_and_folds_nothing():
    """C-01 / C-02: run bookkeeping goes on, observations and pending decay samples are dropped."""
    learner = ResidualHeatLearner()
    kw = dict(model=ROOM, system_type="radiator", T_outdoor=5.0, dt_minutes=0.5, q_solar=0.0, q_occupancy=0.0)
    with patch("custom_components.roommind.managers.residual_heat_tracker.time") as clock:
        for t in (0.0, 30.0, 60.0):
            clock.time.return_value = t
            learner.step(
                "r", mode=MODE_HEATING, delivered_power=0.4, current_temp=20.0, disturbed=False, learning=False, **kw
            )
        state = learner.run_state("r")
        assert state is not None and state[1] == pytest.approx(0.4)
        learner._tau_samples["r"] = 30.0
        clock.time.return_value = 90.0
        assert (
            learner.step(
                "r", mode=MODE_IDLE, delivered_power=None, current_temp=20.0, disturbed=False, learning=False, **kw
            )
            is None
        )
    assert learner._obs == {} and learner.take_tau_sample("r") is None


def test_a_continuing_run_keeps_its_delivered_power():
    """C1-01: a pinned valve's run at 0.4 is not turned into a full-power run by planning on."""
    from custom_components.roommind.control.mpc_optimizer import _extend_run

    assert _extend_run((60.0, 0.4), 5.0) == (65.0, 0.4)
    assert _extend_run(None, 10.0) == (10.0, 1.0)
    opt = _opt(True)
    opt._glow_cache = {}
    # The heating hypothesis' own run carries the run's power as well
    low = opt._evaluate_action(MODE_IDLE, 20.6, 21.0, 21.0, [5.0] * N, [21.0] * N, [21.0] * N, 5.0, run=(60.0, 0.4))
    high = opt._evaluate_action(MODE_IDLE, 20.6, 21.0, 21.0, [5.0] * N, [21.0] * N, [21.0] * N, 5.0, run=(60.0, 1.0))
    assert low != high


def test_heat_capable_ac_keeps_the_base_lookahead_in_a_heat_only_room():
    """C1-02: can_cool is False in a heat-only room, the AC can still heat: no long lookahead."""
    opt = MPCOptimizer(
        model=ROOM,
        can_heat=True,
        can_cool=False,
        heating_system_type="radiator",
        afterglow_control=True,
        residual_tau=30.0,
        heat_capable_ac=True,
    )
    assert _plan(opt, 20.0).lookahead_blocks == LOOKAHEAD_BASE_BLOCKS


def test_kept_run_plan_matches_the_command():
    """C1-03: the plan of a run kept on is simulated with the first block heating."""
    opt = _opt(True)
    real = MPCOptimizer._evaluate_action
    calls = {"i": 0}

    def _eval(self, action, *args, **kwargs):
        cost = real(self, action, *args, **kwargs)
        block = calls["i"]
        if action == MODE_IDLE:
            calls["i"] += 1
            return cost - 1e6 if block == 0 else cost + 1e6
        return cost

    with patch.object(MPCOptimizer, "_evaluate_action", _eval):
        plan = _plan(opt, 20.0, target=22.0)
    assert plan.actions[0] == MODE_HEATING
    expected = ROOM.predict(20.0, 5.0, plan.power_fractions[0] * ROOM.Q_heat, 5.0)
    assert plan.temperatures[1] == pytest.approx(expected, abs=0.01)


def test_a_run_that_spans_a_pause_teaches_nothing_after_it():
    """C2-02: a run with cycles during a paused learning gives no observation once learning is back."""
    learner = ResidualHeatLearner()
    kw = dict(model=ROOM, system_type="radiator", T_outdoor=5.0, dt_minutes=0.5, q_solar=0.0, q_occupancy=0.0)
    with patch("custom_components.roommind.managers.residual_heat_tracker.time") as clock:
        for t, learning in ((0.0, False), (30.0, True), (60.0, True)):
            clock.time.return_value = t
            learner.step(
                "r", mode=MODE_HEATING, delivered_power=1.0, current_temp=20.0, disturbed=False, learning=learning, **kw
            )
        clock.time.return_value = 90.0
        learner.step("r", mode=MODE_IDLE, delivered_power=None, current_temp=20.0, disturbed=False, **kw)
    assert learner._obs == {}
