"""Learned radiator afterglow (#493/#495), learning only: learner, EKF persistence, defaults."""

from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from custom_components.roommind.const import (
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
    RESIDUAL_LEARN_MIN_MINUTES,
    RESIDUAL_LEARN_WINDOW_MINUTES,
    RESIDUAL_SCALE_EMA_ALPHA,
    RESIDUAL_SCALE_MAX,
)
from custom_components.roommind.control.residual_heat import (
    build_residual_series,
    compute_residual_heat,
    learned_afterglow_info,
    residual_tau,
)
from custom_components.roommind.control.thermal_model import RCModel, RoomModelManager, ThermalEKF
from custom_components.roommind.managers.residual_heat_tracker import ResidualHeatLearner

ROOM = RCModel(C=1.0, U=0.1, Q_heat=4.0, Q_cool=0.0)
DT = 0.5  # coordinator cycle, minutes
TIME = "custom_components.roommind.managers.residual_heat_tracker.time"

# ---------------------------------------------------------------------------
# residual_heat: defaults unchanged, scale and decay time
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("elapsed", "pf", "duration"),
    [(0.0, 1.0, 0.0), (5.0, 1.0, 60.0), (3.0, 0.4, 20.0), (25.0, 1.0, 120.0), (-1.0, 1.0, 10.0)],
)
def test_default_arguments_keep_todays_profile(elapsed, pf, duration):
    """Control keeps the fixed profile: the new optional arguments change nothing by default."""
    if elapsed < 0:
        expected = 0.0
    else:
        charge = 1.0 - math.exp(-duration / 15.0) if duration > 0 else 1.0  # profile's tau_charge
        expected = 0.3 * charge * math.exp(-elapsed / 10.0) * pf
        expected = expected if expected >= 0.02 else 0.0
    assert compute_residual_heat(elapsed, "radiator", pf, duration) == pytest.approx(expected)


def test_scale_and_decay_time_change_the_profile():
    base = compute_residual_heat(5.0, "radiator", 1.0, 60.0)
    assert compute_residual_heat(5.0, "radiator", 1.0, 60.0, scale=2.5) == pytest.approx(2.5 * base)
    assert compute_residual_heat(5.0, "radiator", 1.0, 60.0, scale=0.0) == 0.0
    slow = compute_residual_heat(20.0, "radiator", 1.0, 60.0, 1.0, 30.0)
    assert slow > compute_residual_heat(20.0, "radiator", 1.0, 60.0)
    series = build_residual_series(0.0, "radiator", 3, 5.0, 1.0, 60.0, scale=2.0)
    assert series == pytest.approx([2.0 * q for q in build_residual_series(0.0, "radiator", 3, 5.0, 1.0, 60.0)])
    assert residual_tau("radiator") == 10.0
    assert residual_tau("radiator", 25.0) == 25.0
    assert residual_tau("") == 0.0


# ---------------------------------------------------------------------------
# ThermalEKF: learned scale and decay time, persistence
# ---------------------------------------------------------------------------


def test_first_samples_are_weighed_against_the_profile_then_smoothed():
    ekf = ThermalEKF()
    assert ekf.residual_scale == 1.0
    ekf.update_residual_scale(4.0)
    assert ekf.residual_scale == pytest.approx(2.0)  # (1 + 1 + 4) / 3
    ekf.update_residual_scale(4.0)
    assert ekf.residual_scale == pytest.approx(2.5)
    ekf.update_residual_scale(4.0)
    assert ekf.residual_scale == pytest.approx(2.8)
    ekf.update_residual_scale(4.0)
    assert ekf.residual_scale == pytest.approx(2.8 + RESIDUAL_SCALE_EMA_ALPHA * 1.2)
    assert ekf.residual_scale_n == 4


def test_samples_are_clamped_and_non_finite_ignored():
    ekf = ThermalEKF()
    ekf.update_residual_scale(float("nan"))
    assert ekf.residual_scale == 1.0 and ekf.residual_scale_n == 0
    ekf.update_residual_scale(100.0)
    assert ekf.residual_scale == pytest.approx(1.0 + (RESIDUAL_SCALE_MAX - 1.0) / 3)
    ekf2 = ThermalEKF()
    ekf2.update_residual_scale(-4.0)
    assert ekf2.residual_scale == pytest.approx(2.0 / 3)


def test_decay_time_update_keeps_the_total_heat():
    ekf = ThermalEKF()
    ekf.update_residual_scale(4.0)
    total = ekf.residual_scale * 10.0
    ekf.update_residual_tau(40.0, 10.0)
    assert ekf.residual_tau is not None and 10.0 < ekf.residual_tau < 40.0
    assert ekf.residual_scale * ekf.residual_tau == pytest.approx(total)
    ekf.update_residual_tau(float("inf"), 10.0)
    assert ekf._residual_tau_n == 1


def test_learned_values_persist_and_old_data_defaults():
    mgr = RoomModelManager()
    mgr.update_residual_scale("bath", 4.0)
    mgr.update_residual_tau("bath", 30.0, 10.0)
    restored = RoomModelManager.from_dict(mgr.to_dict())
    assert restored.get_residual_scale("bath") == pytest.approx(mgr.get_residual_scale("bath"))
    assert restored.get_residual_tau("bath") == pytest.approx(mgr.get_residual_tau("bath"))
    assert restored.get_residual_samples("bath") == 1
    assert restored.get_residual_scale("unknown") == 1.0
    assert restored.get_residual_tau("unknown") is None
    old = mgr.to_dict()["bath"]
    for key in ("residual_scale", "residual_scale_n", "residual_tau", "residual_tau_n"):
        del old[key]
    est = ThermalEKF.from_dict(old)
    assert (est.residual_scale, est.residual_scale_n, est.residual_tau, est._residual_tau_n) == (1.0, 0, None, 0)


def test_recovery_migration_keeps_the_learned_afterglow():
    data = ThermalEKF().to_dict()
    data["ekf_version"] = 4
    data["x"][1] = 1e6  # alpha pegged: an old model the recovery migration resets
    data.update(residual_scale=3.0, residual_scale_n=5, residual_tau=25.0, residual_tau_n=2)
    est = ThermalEKF.from_dict(data)
    assert (est.residual_scale, est.residual_scale_n, est.residual_tau, est._residual_tau_n) == (3.0, 5, 25.0, 2)


def test_afterglow_info_for_analytics():
    ekf = ThermalEKF()
    assert learned_afterglow_info(ekf) == {
        "residual_scale": 1.0,
        "residual_samples": 0,
        "residual_decay_minutes": 10.0,
    }
    ekf.update_residual_scale(4.0)
    ekf.update_residual_tau(30.0, 10.0)
    info = learned_afterglow_info(ekf)
    assert info["residual_samples"] == 1
    assert info["residual_decay_minutes"] == round(ekf.residual_tau, 1)


# ---------------------------------------------------------------------------
# ResidualHeatLearner: own run bookkeeping, samples on a synthetic room
# ---------------------------------------------------------------------------


def _replay(
    learner: ResidualHeatLearner,
    *,
    true_scale: float,
    true_tau: float | None = None,
    run_minutes: float = 60.0,
    true_power: float = 1.0,
    delivered: float | None = None,
    window: float = RESIDUAL_LEARN_WINDOW_MINUTES,
    disturb_at: float | None = None,
    restart_at: float | None = None,
    cool_at: float | None = None,
    missing_at: float | None = None,
    commanded_heating: bool = False,
    extra: tuple[float, ...] = (),
    skip: tuple[float, ...] = (),
) -> float | None:
    """Heat for *run_minutes* at *delivered* power, then replay the room cooling after the stop,
    warmed by *true_scale* x a continuously decaying radiator afterglow (decay *true_tau*,
    power *true_power*). *commanded_heating*: heating stays commanded while the radiators deliver
    nothing. *extra* / *skip*: refreshes (minutes after the stop) added to or missing from the
    30 s grid."""
    delivered = true_power if delivered is None else delivered
    kwargs = dict(model=ROOM, system_type="radiator", T_outdoor=5.0, dt_minutes=DT, q_solar=0.0, q_occupancy=0.0)
    after_mode, after_power = (MODE_HEATING, 0.0) if commanded_heating else (MODE_IDLE, None)
    t, T = 1000.0, 21.0
    with patch(TIME) as clock:
        for _ in range(int(run_minutes / DT)):
            clock.time.return_value = t
            assert (
                learner.step(
                    "r", mode=MODE_HEATING, delivered_power=delivered, current_temp=T, disturbed=False, **kwargs
                )
                is None
            )
            t += DT * 60
        clock.time.return_value = t  # the stop
        assert (
            learner.step("r", mode=after_mode, delivered_power=after_power, current_temp=T, disturbed=False, **kwargs)
            is None
        )
        stop = t
        grid = [round(DT * k, 6) for k in range(1, int(window / DT) + 1)]
        times = sorted({e for e in grid if all(abs(e - x) > 1e-9 for x in skip)} | set(extra))
        last = 0.0
        for elapsed in times:
            clock.time.return_value = stop + elapsed * 60
            mode, power = after_mode, after_power
            if restart_at is not None and elapsed >= restart_at:
                mode, power = MODE_HEATING, delivered
            if cool_at is not None and elapsed >= cool_at:
                mode, power = MODE_COOLING, None
            if power is None or power == 0.0:
                step = elapsed - last
                q = compute_residual_heat(
                    elapsed - step / 2, "radiator", true_power, run_minutes, true_scale, true_tau, cutoff=False
                )
                T = ROOM.predict(T, 5.0, 0.0, step, q_residual=q)
            last = elapsed
            reading = None if missing_at is not None and elapsed >= missing_at else T
            sample = learner.step(
                "r",
                mode=mode,
                delivered_power=power,
                current_temp=reading,
                disturbed=disturb_at is not None and elapsed >= disturb_at,
                **kwargs,
            )
            if sample is not None or (power or 0.0) > 0 or mode == MODE_COOLING or reading is None:
                return sample
    return None


@pytest.mark.parametrize("true_scale", [0.5, 1.0, 3.0])
def test_learner_recovers_the_true_scale(true_scale):
    # Tight: the learner compares against the uncut decay, as the physical afterglow is
    assert _replay(ResidualHeatLearner(), true_scale=true_scale) == pytest.approx(true_scale, rel=0.02)


@pytest.mark.parametrize("true_scale", [0.5, 3.0])
@pytest.mark.parametrize("true_power", [0.4, 1.0])
def test_learner_is_unbiased_by_the_control_cutoff(true_scale, true_power):
    """The control cutoff no longer cuts the reference tail: the tail at any scale and opening reads true."""
    sample = _replay(ResidualHeatLearner(), true_scale=true_scale, true_power=true_power)
    assert sample == pytest.approx(true_scale, rel=0.02)
    assert compute_residual_heat(50.0, "radiator", 0.4, 60.0) == 0.0  # control keeps its cutoff
    assert compute_residual_heat(50.0, "radiator", 0.4, 60.0, cutoff=False) > 0.0


def test_radiator_that_stops_delivering_ends_the_run_while_heating_is_commanded():
    """A TRV that closed on its own: the stop is when its heat ended, not the next idle cycle."""
    learner = ResidualHeatLearner()
    assert _replay(learner, true_scale=2.0, commanded_heating=True) == pytest.approx(2.0, rel=0.02)


def test_early_refreshes_are_measured_over_their_real_interval():
    extra = tuple(DT * k + DT / 3 for k in range(0, 100, 3))
    assert _replay(ResidualHeatLearner(), true_scale=2.0, extra=extra) == pytest.approx(2.0, rel=0.02)


def test_a_missed_cycle_drops_the_observation():
    learner = ResidualHeatLearner()
    assert _replay(learner, true_scale=2.0, skip=(10.0, 10.5, 11.0)) is None
    assert learner._obs == {}


def test_held_opening_is_the_run_power():
    """A pinned valve at 40 % charges the radiator at 40 %: the learner weighs the run at 0.4."""
    right = _replay(ResidualHeatLearner(), true_scale=2.0, true_power=0.4)
    assert right == pytest.approx(2.0, rel=0.02)
    # Weighed at full power, the same afterglow would read as a much smaller radiator
    wrong = _replay(ResidualHeatLearner(), true_scale=2.0, true_power=0.4, delivered=1.0)
    assert wrong is not None and wrong < 0.5 * right


def test_full_window_fits_the_decay_time():
    learner = ResidualHeatLearner()
    sample = _replay(learner, true_scale=3.0, true_tau=30.0)
    assert sample is not None
    assert learner.take_tau_sample("r") == pytest.approx(30.0, abs=5.0)
    assert learner.take_tau_sample("r") is None  # handed out once


def test_disturbance_drops_the_observation():
    learner = ResidualHeatLearner()
    assert _replay(learner, true_scale=2.0, disturb_at=10.0) is None
    assert learner._obs == {} and learner._runs == {}


def test_cooling_and_missing_reading_drop_the_observation():
    learner = ResidualHeatLearner()
    assert _replay(learner, true_scale=2.0, cool_at=10.0) is None
    assert learner._obs == {}
    assert _replay(learner, true_scale=2.0, missing_at=10.0) is None
    assert learner._obs == {}


def test_restart_after_min_minutes_still_counts():
    sample = _replay(ResidualHeatLearner(), true_scale=2.0, restart_at=RESIDUAL_LEARN_MIN_MINUTES + 5)
    assert sample == pytest.approx(2.0, rel=0.1)


def test_unseen_cycles_during_a_run_restart_it():
    """Cycles missing mid-run: the run counts from where heating was seen again."""
    learner = ResidualHeatLearner()
    kwargs = dict(model=ROOM, system_type="radiator", T_outdoor=5.0, dt_minutes=DT, q_solar=0.0, q_occupancy=0.0)
    with patch(TIME) as clock:
        for t in (0.0, 30.0, 60.0, 1260.0, 1290.0):  # 20 minutes unseen after the third cycle
            clock.time.return_value = t
            learner.step("r", mode=MODE_HEATING, delivered_power=1.0, current_temp=20.0, disturbed=False, **kwargs)
    assert learner._runs["r"].start == 1260.0


def test_unseen_cycles_right_before_the_stop_give_no_observation():
    learner = ResidualHeatLearner()
    kwargs = dict(model=ROOM, system_type="radiator", T_outdoor=5.0, dt_minutes=DT, q_solar=0.0, q_occupancy=0.0)
    with patch(TIME) as clock:
        for t in (0.0, 30.0, 60.0):
            clock.time.return_value = t
            learner.step("r", mode=MODE_HEATING, delivered_power=1.0, current_temp=20.0, disturbed=False, **kwargs)
        clock.time.return_value = 600.0  # the stop seen 9 minutes after the last heating cycle
        learner.step("r", mode=MODE_IDLE, delivered_power=None, current_temp=20.0, disturbed=False, **kwargs)
    assert learner._runs == {} and learner._obs == {}


def test_restart_after_a_gap_gives_no_sample():
    """Updates stopped for minutes, then heating restarted: the unseen gap may hide heat."""
    gap = tuple(round(DT * k, 6) for k in range(30, 41))  # 15-20 min after the stop missing
    assert _replay(ResidualHeatLearner(), true_scale=2.0, skip=gap, restart_at=20.5) is None


def test_restart_before_min_minutes_gives_no_sample():
    learner = ResidualHeatLearner()
    assert _replay(learner, true_scale=2.0, restart_at=RESIDUAL_LEARN_MIN_MINUTES - 5) is None
    assert "r" in learner._runs  # the new run is followed


def test_short_run_carries_no_signal():
    assert _replay(ResidualHeatLearner(), true_scale=2.0, run_minutes=1.0) is None


def test_heating_without_delivered_heat_starts_no_run():
    learner = ResidualHeatLearner()
    kwargs = dict(model=ROOM, system_type="radiator", T_outdoor=5.0, dt_minutes=DT, q_solar=0.0, q_occupancy=0.0)
    for power in (None, 0.0):
        learner.step("r", mode=MODE_HEATING, delivered_power=power, current_temp=20.0, disturbed=False, **kwargs)
    assert learner._runs == {}
    # No radiator in a known state while heating: the run in progress is dropped
    learner.step("r", mode=MODE_HEATING, delivered_power=1.0, current_temp=20.0, disturbed=False, **kwargs)
    learner.step("r", mode=MODE_HEATING, delivered_power=None, current_temp=20.0, disturbed=False, **kwargs)
    assert learner._runs == {} and learner._obs == {}
    learner.step("r", mode=MODE_IDLE, delivered_power=None, current_temp=20.0, disturbed=False, **kwargs)
    assert learner._obs == {}


def test_non_radiator_room_learns_nothing_and_cleanup():
    learner = ResidualHeatLearner()
    kwargs = dict(model=ROOM, T_outdoor=5.0, dt_minutes=DT, q_solar=0.0, q_occupancy=0.0, current_temp=20.0)
    learner.step("r", system_type="", mode=MODE_HEATING, delivered_power=1.0, disturbed=False, **kwargs)
    assert learner._runs == {}
    learner.step("r", system_type="radiator", mode=MODE_HEATING, delivered_power=1.0, disturbed=False, **kwargs)
    learner.remove_room("r")
    assert learner._runs == {}
    learner.step("r", system_type="radiator", mode=MODE_HEATING, delivered_power=1.0, disturbed=False, **kwargs)
    learner.clear_all()
    assert learner._runs == {}
