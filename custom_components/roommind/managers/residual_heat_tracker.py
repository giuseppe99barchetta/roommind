"""Residual heat transition tracking for RoomMind."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..const import (
    AFTERGLOW_READING_MAX_STEP_K,
    MODE_HEATING,
    MODE_IDLE,
    RESIDUAL_LEARN_MIN_EXPECTED_K,
    RESIDUAL_LEARN_MIN_MINUTES,
    RESIDUAL_LEARN_WINDOW_MINUTES,
    RESIDUAL_TAU_GRID,
    RESIDUAL_TAU_MIN_RISE_K,
)
from ..control.residual_heat import compute_residual_heat
from ..control.thermal_model import RCModel


class ResidualHeatTracker:
    """Tracks heating on/off transitions and computes residual heat."""

    def __init__(self) -> None:
        self._off_since: dict[str, float] = {}
        self._off_power: dict[str, float] = {}
        self._on_since: dict[str, float] = {}

    def get_q_residual(
        self,
        area_id: str,
        system_type: str,
        previous_mode: str,
        scale: float = 1.0,
        tau_minutes: float | None = None,
    ) -> float:
        """Compute residual heat from previous cycle state (learned scale / decay for afterglow control)."""
        if not system_type or area_id not in self._off_since or previous_mode == MODE_HEATING:
            return 0.0
        elapsed = (time.time() - self._off_since[area_id]) / 60.0
        heat_dur = (self._off_since[area_id] - self._on_since.get(area_id, self._off_since[area_id])) / 60.0
        last_pf = self._off_power.get(area_id, 1.0)
        return compute_residual_heat(elapsed, system_type, last_pf, heat_dur, scale, tau_minutes)

    def update(
        self, area_id: str, mode: str, power_fraction: float, previous_mode: str, q_residual: float = 0.0
    ) -> None:
        """Update heating transition state based on current mode."""
        if mode == MODE_HEATING:
            self._off_since.pop(area_id, None)
            self._off_power[area_id] = power_fraction
            if previous_mode != MODE_HEATING:
                self._on_since[area_id] = time.time()
        elif previous_mode == MODE_HEATING:
            self._off_since[area_id] = time.time()
        elif q_residual == 0.0 and area_id in self._off_since:
            self._off_since.pop(area_id, None)
            self._off_power.pop(area_id, None)
            self._on_since.pop(area_id, None)

    def remove_room(self, area_id: str) -> None:
        """Clean up state for a removed room."""
        self._off_since.pop(area_id, None)
        self._off_power.pop(area_id, None)
        self._on_since.pop(area_id, None)

    def clear_room(self, area_id: str) -> None:
        """Clear state for a room (thermal reset)."""
        self.remove_room(area_id)

    def clear_all(self) -> None:
        """Clear state for all rooms."""
        self._off_since.clear()
        self._off_power.clear()
        self._on_since.clear()


@dataclass
class _Run:
    """A heating run the learner follows: start and the radiators' delivered power per cycle."""

    start: float
    last: float  # last heating cycle seen
    power_sum: float = 0.0
    cycles: int = 0
    # False once a cycle of it ran while learning was paused: control still reads it, learning not
    learnable: bool = True

    @property
    def power(self) -> float:
        return self.power_sum / self.cycles if self.cycles else 0.0


@dataclass
class _Observation:
    """One afterglow under observation (see ResidualHeatLearner)."""

    stop: float
    T_prev: float
    t_prev: float  # when T_prev was read
    system_type: str
    run_minutes: float
    run_power: float
    measured_excess: float = 0.0  # K the room rose beyond the model's idle drift
    # Per step: (minutes after the stop at its middle, K one unit of residual heat adds
    # over the step, K measured beyond the idle drift). The model is linear in the
    # residual heat, so any decay time's expected rise follows from these.
    steps: list[tuple[float, float, float]] = field(default_factory=list)

    def expected(self, tau: float | None) -> list[float]:
        """Cumulative rise (K) the afterglow at scale 1 and decay time *tau* predicts per step."""
        total, out = 0.0, []
        for mid, gain, _ in self.steps:
            total += gain * compute_residual_heat(
                mid, self.system_type, self.run_power, self.run_minutes, 1.0, tau, cutoff=False
            )
            out.append(total)
        return out

    def fit_tau(self) -> float | None:
        """Decay time whose afterglow shape best matches the measured rise, None without a clear signal.

        The cumulative measured rise is fitted with each candidate's cumulative rise
        (least squares over the scale); the candidate with the smallest residual wins.
        """
        if self.measured_excess < RESIDUAL_TAU_MIN_RISE_K or len(self.steps) < 4:
            return None
        measured, total = [], 0.0
        for _, _, excess in self.steps:
            total += excess
            measured.append(total)
        best: tuple[float, float] | None = None
        for tau in RESIDUAL_TAU_GRID:
            unit = self.expected(tau)
            denom = sum(u * u for u in unit)
            if denom <= 0:
                continue
            scale = sum(m * u for m, u in zip(measured, unit, strict=True)) / denom
            if scale <= 0:
                continue
            sse = sum((m - scale * u) ** 2 for m, u in zip(measured, unit, strict=True))
            if best is None or sse < best[1]:
                best = (tau, sse)
        return best[0] if best is not None else None


class ResidualHeatLearner:
    """Learns how much heat a room's radiators really release after a run (upstream #493/#495).

    After each heating run the room is watched: every idle cycle the measured change is
    compared with the learned model's idle prediction without residual heat, and with the
    change the profile at scale 1 predicts. The ratio of the two sums is one sample of the
    room's residual scale; a full window also fits the decay time (``take_tau_sample``).

    Keeps its own run bookkeeping, apart from ``ResidualHeatTracker``: the run power is the
    mean power the radiators delivered (a pinned valve's held opening), and nothing here
    changes the residual heat control and the EKF work with.

    A disturbance (window, AC heating, bypass radiator, boiler wait, ...), a cooling run or a
    missing reading drops the run and the observation; a run that restarts after
    ``RESIDUAL_LEARN_MIN_MINUTES`` still gives a sample.
    """

    def __init__(self) -> None:
        self._runs: dict[str, _Run] = {}
        self._obs: dict[str, _Observation] = {}
        self._tau_samples: dict[str, float] = {}

    def step(
        self,
        area_id: str,
        *,
        model: RCModel,
        system_type: str,
        mode: str,
        delivered_power: float | None,
        current_temp: float | None,
        T_outdoor: float | None,
        dt_minutes: float,
        q_solar: float,
        q_occupancy: float,
        disturbed: bool,
        tau_minutes: float | None = None,
        learning: bool = True,
    ) -> float | None:
        """Advance one cycle. Returns a residual scale sample when an observation completes.

        *learning* False (the room's model learning is paused): only the run bookkeeping goes
        on (afterglow control reads it); no observation starts, one in progress and a pending
        decay sample are dropped, no sample is returned.

        *delivered_power*: the radiators' delivered power this cycle while heating: 0 when the
        driven radiators deliver nothing (a TRV that closed on its own), None when no radiator
        is driven in a known state. A heating cycle delivering nothing counts as idle: the
        run stopped there, even though heating is still commanded.
        """
        if (
            not system_type
            or disturbed
            or current_temp is None
            or T_outdoor is None
            or (mode == MODE_HEATING and delivered_power is None)
        ):
            self.remove_room(area_id)
            return None
        now = time.time()
        if not learning:
            self._obs.pop(area_id, None)
            self._tau_samples.pop(area_id, None)
        if mode == MODE_HEATING and delivered_power is not None and delivered_power > 0:
            obs = self._obs.pop(area_id, None)
            sample = None
            if (
                obs is not None
                and (now - obs.stop) / 60.0 >= RESIDUAL_LEARN_MIN_MINUTES
                # A gap before the restart may hide heat or a disturbance: then it does not count
                and (now - obs.t_prev) / 60.0 <= 2 * dt_minutes
            ):
                # Restarted: what was seen so far still counts when it was long enough
                sample = self._sample(obs, tau_minutes)
            run = self._runs.get(area_id)
            if run is None or (now - run.last) / 60.0 > 2 * dt_minutes:
                # New run, or cycles went unseen: the unseen part may not have heated
                run = self._runs[area_id] = _Run(start=now, last=now)
            run.last = now
            run.power_sum += delivered_power
            run.cycles += 1
            if not learning:
                run.learnable = False
            return sample
        if mode not in (MODE_IDLE, MODE_HEATING):
            self.remove_room(area_id)
            return None
        ended = self._runs.pop(area_id, None)
        if not learning or (ended is not None and not ended.learnable):
            # Nothing measured during a pause is learned, also not after it
            return None
        if ended is not None and (now - ended.last) / 60.0 > 2 * dt_minutes:
            # Cycles went unseen before the stop: when the heat really ended is unknown
            self._obs.pop(area_id, None)
            return None
        if ended is not None:
            # The stop: watch the afterglow from this reading on
            self._obs[area_id] = _Observation(
                stop=now,
                T_prev=current_temp,
                t_prev=now,
                system_type=system_type,
                run_minutes=(now - ended.start) / 60.0,
                run_power=ended.power,
            )
            return None
        obs = self._obs.get(area_id)
        if obs is None:
            return None
        # The step is the real time since the last reading: refreshes come early or late
        step_minutes = (now - obs.t_prev) / 60.0
        if step_minutes <= 0:
            return None
        minutes = (now - obs.stop) / 60.0
        if step_minutes > 2 * dt_minutes or minutes > RESIDUAL_LEARN_WINDOW_MINUTES + dt_minutes:
            # A missed cycle leaves a step whose inputs (outdoor, sun) were not seen
            self._obs.pop(area_id, None)
            return None
        mid = max(0.0, minutes - step_minutes / 2)
        base = model.predict(obs.T_prev, T_outdoor, 0.0, step_minutes, q_solar=q_solar, q_occupancy=q_occupancy)
        with_unit = model.predict(
            obs.T_prev, T_outdoor, 0.0, step_minutes, q_solar=q_solar, q_occupancy=q_occupancy, q_residual=1.0
        )
        excess = current_temp - base
        obs.measured_excess += excess
        obs.steps.append((mid, with_unit - base, excess))
        obs.T_prev = current_temp
        obs.t_prev = now
        if minutes < RESIDUAL_LEARN_WINDOW_MINUTES:
            return None
        self._obs.pop(area_id, None)
        sample = self._sample(obs, tau_minutes)
        # The shape only counts where the size does: a short run's rise is mostly not its own heat
        tau = obs.fit_tau() if sample is not None else None
        if tau is not None:
            self._tau_samples[area_id] = tau
        return sample

    def run_state(self, area_id: str) -> tuple[float, float] | None:
        """(minutes, delivered power) of the radiator run in progress, None without one."""
        run = self._runs.get(area_id)
        if run is None or not run.cycles:
            return None
        return (time.time() - run.start) / 60.0, run.power

    def take_tau_sample(self, area_id: str) -> float | None:
        """The decay time the last full window fitted for *area_id*, once (None without one)."""
        return self._tau_samples.pop(area_id, None)

    @staticmethod
    def _sample(obs: _Observation, tau_minutes: float | None) -> float | None:
        expected = obs.expected(tau_minutes)
        if not expected or expected[-1] < RESIDUAL_LEARN_MIN_EXPECTED_K:
            return None
        return obs.measured_excess / expected[-1]

    def remove_room(self, area_id: str) -> None:
        """Drop the run and observation of a room (removed, reset or disturbed)."""
        self._runs.pop(area_id, None)
        self._obs.pop(area_id, None)
        self._tau_samples.pop(area_id, None)

    def clear_all(self) -> None:
        """Drop all runs and observations."""
        self._runs.clear()
        self._obs.clear()
        self._tau_samples.clear()


class AfterglowReading:
    """Where a radiator room stands while its sensor lags the afterglow of a stopped run (3822bc45).

    A sensor reports in steps: after the plan stops a run on the stored heat, the room rises
    but the reading stays at the last step for minutes, and the next cycle would start the run
    again. While the reading has not fallen below the one at the stop, the plan works from the
    temperature the stopping plan predicted, at most one reporting step above the reading.
    Only the plan uses it (afterglow control on); EKF, history and display keep the reading.
    """

    def __init__(self) -> None:
        self._last: dict[str, float] = {}
        self._step: dict[str, float] = {}
        # area -> (stop time, reading at the stop, predicted temperatures, block minutes)
        self._stops: dict[str, tuple[float, float, list[float], float]] = {}

    def observe(self, area_id: str, reading: float) -> None:
        """Note this cycle's reading; a change sets the sensor's reporting step."""
        last = self._last.get(area_id)
        if last is not None and reading != last:
            self._step[area_id] = min(abs(reading - last), AFTERGLOW_READING_MAX_STEP_K)
        self._last[area_id] = reading

    def note_stop(self, area_id: str, reading: float, temperatures: list[float], dt_minutes: float) -> None:
        """The plan stopped a run: remember what it expects the room to do now."""
        self._stops[area_id] = (time.time(), reading, list(temperatures), dt_minutes)

    def clear(self, area_id: str) -> None:
        """A run started: the stop no longer applies."""
        self._stops.pop(area_id, None)

    def remove_room(self, area_id: str) -> None:
        self._stops.pop(area_id, None)
        self._last.pop(area_id, None)
        self._step.pop(area_id, None)

    def clear_all(self) -> None:
        self._stops.clear()
        self._last.clear()
        self._step.clear()

    def estimate(self, area_id: str, reading: float) -> float:
        """The temperature to plan from: *reading*, or the stopping plan's, at most a step above."""
        stop = self._stops.get(area_id)
        step = self._step.get(area_id, 0.0)
        if stop is None or step <= 0.0:
            return reading
        at, stop_reading, temps, dt = stop
        minutes = (time.time() - at) / 60.0
        if reading < stop_reading or minutes > RESIDUAL_LEARN_WINDOW_MINUTES or not temps or dt <= 0:
            self._stops.pop(area_id, None)
            return reading
        k = minutes / dt
        i = min(int(k), len(temps) - 1)
        j = min(i + 1, len(temps) - 1)
        predicted = temps[i] + (temps[j] - temps[i]) * (k - i)
        return max(reading, min(reading + step, predicted))
