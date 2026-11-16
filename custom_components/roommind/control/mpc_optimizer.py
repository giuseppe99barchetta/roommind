"""MPC Optimizer using Dynamic Programming for RoomMind."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..const import (
    DEFAULT_COMFORT_WEIGHT,
    HEATING_SYSTEM_PROFILES,
    HEATING_SYSTEM_RADIATOR,
    MIN_POWER_FRACTION,
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
)
from .residual_heat import compute_residual_heat, get_min_run_blocks, residual_tau
from .thermal_model import RCModel

# Base lookahead for per-block decision cost evaluation. Radiator / unknown
# systems stay at this value; systems with long thermal time constants scale up.
LOOKAHEAD_BASE_BLOCKS = 6
# How many tau time-constants to include in the lookahead beyond min_run. Set to
# 1.0 so UFH lookahead (24 blocks = 120 min) matches the outer horizon minimum,
# avoiding silent clamping. See issue #131.
LOOKAHEAD_HORIZON_SCALE = 1.0
# Predictions are clamped to [temp_min, temp_max], but never closer than this to where the
# room starts: a room already past a bound must still see which action moves it back (#462).
CLAMP_HEADROOM_K = 5.0
# A pre-heat must reach a rising heat target within this margin at the block it starts.
PREHEAT_DEADLINE_MARGIN = 0.1
# A running pre-heat continues while waiting this long (1 h) would miss the target.
PREHEAT_CONTINUE_BLOCKS = 12
# Pre-heat lead at the default comfort weight; the slider scales it down to 0 at full efficiency.
PREHEAT_MAX_LEAD_HOURS = 12.0
# Learned radiator afterglow in control (room switch, upstream #493): decisions look this many
# decay times past the min run, so the overshoot stored heat causes after a stop is weighed.
RADIATOR_LOOKAHEAD_TAUS = 2.0
# A radiator run is not paused for this many blocks and restarted (a439c14c).
RADIATOR_PAUSE_BLOCKS = 2


def preheat_max_blocks(comfort_weight: float, dt_minutes: float = 5.0) -> int | None:
    """Pre-heat lead the comfort/efficiency slider allows: the default and above
    plan up to the horizon, towards efficiency the lead shrinks to none."""
    if comfort_weight >= DEFAULT_COMFORT_WEIGHT:
        return None
    hours = PREHEAT_MAX_LEAD_HOURS * max(0.0, comfort_weight) / DEFAULT_COMFORT_WEIGHT
    return int(hours * 60 / dt_minutes)


@dataclass
class MPCPlan:
    """Result of MPC optimization — a planned sequence of actions."""

    actions: list[str]
    temperatures: list[float]  # len = len(actions) + 1 (includes initial)
    dt_minutes: float = 5.0
    power_fractions: list[float] = field(default_factory=list)
    # Per-system decision lookahead used when building this plan. Exposed so
    # the controller's safety guard can align its horizon with the optimizer's.
    lookahead_blocks: int = LOOKAHEAD_BASE_BLOCKS
    # Blocks to the rising heat target the first block pre-heats for (0: none), so the
    # controller's guard looks that far ahead instead of overruling the pre-heat.
    preheat_blocks: int = 0

    def get_current_action(self) -> str:
        """Return the action for the current (first) time block."""
        if not self.actions:
            return MODE_IDLE
        return self.actions[0]

    def get_current_power_fraction(self) -> float:
        """Power fraction for the current block. Backward-compatible."""
        if not self.power_fractions:
            return 1.0 if self.actions and self.actions[0] != MODE_IDLE else 0.0
        return self.power_fractions[0]


@dataclass
class MPCOptimizer:
    """Dynamic Programming optimizer for heating/cooling control.

    Plans the optimal on/off schedule over a prediction horizon
    to minimize a weighted sum of temperature deviation and energy use.
    """

    model: RCModel
    can_heat: bool = True
    can_cool: bool = True
    w_comfort: float = 10.0
    w_energy: float = 1.0
    min_run_blocks: int = 2  # minimum 2 blocks (10 min) per run
    outdoor_cooling_min: float = 16.0
    outdoor_heating_max: float = 22.0
    temp_min: float = 5.0  # frost protection
    temp_max: float = 30.0  # overheat protection
    override_active: bool = False
    # {"heat": bool, "cool": bool}: per-direction outdoor-gate rescue.
    gate_rescue: dict[str, bool] = field(default_factory=dict)
    heating_system_type: str = ""  # key into HEATING_SYSTEM_PROFILES; "" = unknown
    approach_rate: float = 1.0  # fraction of remaining gap closed per block; 1.0 = legacy deadbeat
    # Longest pre-heat lead the deadline may plan (blocks); None = up to the horizon.
    preheat_max_blocks: int | None = None
    # Learned radiator afterglow in control (room switch, off by default): the plan weighs the
    # stored heat of the run in progress and of each planned run. Off: today's plan exactly.
    afterglow_control: bool = False
    residual_scale: float = 1.0
    residual_tau: float | None = None

    def __post_init__(self) -> None:
        # Set before optimize() runs so callers / patched optimize() still expose
        # a sensible default. optimize() refreshes this from dt_minutes per call.
        self._lookahead_blocks = LOOKAHEAD_BASE_BLOCKS

    def optimize(
        self,
        T_room: float,
        T_outdoor_series: list[float],
        heat_target_series: list[float],
        cool_target_series: list[float] | None = None,
        dt_minutes: float = 5.0,
        *,
        solar_series: list[float] | None = None,
        residual_series: list[float] | None = None,
        occupancy_series: list[float] | None = None,
        initial_mode: str = MODE_IDLE,
        heat_run: tuple[float, float] | None = None,
    ) -> MPCPlan:
        """Find optimal action sequence over the planning horizon.

        ``heat_run`` (afterglow control only): (minutes, power) of the radiator run in progress.

        Uses forward simulation with greedy optimization per block,
        considering minimum run time constraints.

        Accepts dual target series (heat_target_series + cool_target_series)
        for dead-band-aware optimization. If cool_target_series is None,
        it defaults to heat_target_series (single-target behavior).
        """
        if cool_target_series is None:
            cool_target_series = list(heat_target_series)

        # Clamp inverted targets: cool must be >= heat
        cool_target_series = [max(h, c) for h, c in zip(heat_target_series, cool_target_series, strict=False)]

        # Per-system decision lookahead. UFH (tau=90min) scales up so the cost
        # function can see post-heating residual afterglow; radiator / "" stay
        # at LOOKAHEAD_BASE_BLOCKS for byte-identical behaviour. Hybrid UFH+AC
        # rooms (can_cool=True) also keep the base lookahead: extending the
        # horizon without a matching cooling-side synthesis would shift the
        # energy/comfort ratio for COOLING and cause more aggressive AC use.
        profile = HEATING_SYSTEM_PROFILES.get(self.heating_system_type) if self.heating_system_type else None
        glow_on = self.afterglow_control and self.heating_system_type == HEATING_SYSTEM_RADIATOR
        self._glow_cache: dict[tuple[float, float, float], float] = {}
        if glow_on and dt_minutes > 0 and not self.can_cool:
            # A heat-capable AC in the room keeps the base lookahead (no AC overshoot weighing)
            tau_l = residual_tau(HEATING_SYSTEM_RADIATOR, self.residual_tau)
            self._lookahead_blocks = max(
                LOOKAHEAD_BASE_BLOCKS, self.min_run_blocks + math.ceil(RADIATOR_LOOKAHEAD_TAUS * tau_l / dt_minutes)
            )
        elif profile and dt_minutes > 0 and not self.can_cool:
            tau_blocks = math.ceil(profile["tau_minutes"] / dt_minutes)
            self._lookahead_blocks = max(
                LOOKAHEAD_BASE_BLOCKS,
                self.min_run_blocks + math.ceil(LOOKAHEAD_HORIZON_SCALE * tau_blocks),
            )
        else:
            self._lookahead_blocks = LOOKAHEAD_BASE_BLOCKS

        n_blocks = min(len(T_outdoor_series), len(heat_target_series), len(cool_target_series))
        if n_blocks == 0 or not math.isfinite(T_room):
            return MPCPlan(actions=[], temperatures=[T_room], dt_minutes=dt_minutes)

        q_solar = solar_series or [0.0] * n_blocks
        q_residual = residual_series or [0.0] * n_blocks
        q_occupancy = occupancy_series or [0.0] * n_blocks

        actions: list[str] = []
        temp_lo, temp_hi = self._temp_bounds(T_room)
        temperatures: list[float] = [T_room]
        power_fractions: list[float] = []
        current_temp = T_room
        current_mode = MODE_IDLE
        blocks_in_mode = 0
        preheat_blocks = 0
        # UFH keeps its own pre-heat (longer lookahead with synthesized afterglow): heating
        # a screed until the air reaches the target overshot by the stored heat.
        slow_heat = self.min_run_blocks > get_min_run_blocks("", dt_minutes)
        # Afterglow control: the run in progress (minutes, power) and the last stopped one
        run = heat_run if glow_on and initial_mode == MODE_HEATING and heat_run is not None else None
        glow: tuple[float, float] | None = None
        glow_elapsed = 0.0

        for i in range(n_blocks):
            T_out = T_outdoor_series[i]
            heat_tgt = heat_target_series[i]
            cool_tgt = cool_target_series[i]
            qs = q_solar[i] if i < len(q_solar) else 0.0
            qr = q_residual[i] if i < len(q_residual) else 0.0
            qo = q_occupancy[i] if i < len(q_occupancy) else 0.0

            # Determine available actions this block
            available = [MODE_IDLE]
            if self.can_heat and not self._is_outdoor_gated(MODE_HEATING, T_out):
                available.append(MODE_HEATING)
            if self.can_cool and not self._is_outdoor_gated(MODE_COOLING, T_out):
                available.append(MODE_COOLING)

            # If in a run and below min_run_blocks, must continue
            forced = current_mode != MODE_IDLE and blocks_in_mode < self.min_run_blocks
            if forced:
                if current_mode in available:
                    best_action = current_mode
                else:
                    best_action = MODE_IDLE  # forced off by constraint
            else:
                # Evaluate each action: look ahead to find best
                best_action = MODE_IDLE
                best_cost = float("inf")
                future_solar = q_solar[i:] if q_solar else None
                future_residual = q_residual[i:] if q_residual else None
                future_occupancy = q_occupancy[i:] if q_occupancy else None
                for action in available:
                    cost = self._evaluate_action(
                        action,
                        current_temp,
                        heat_tgt,
                        cool_tgt,
                        T_outdoor_series[i:],
                        heat_target_series[i:],
                        cool_target_series[i:],
                        dt_minutes,
                        future_solar=future_solar,
                        future_residual=future_residual,
                        future_occupancy=future_occupancy,
                        run=run if glow_on else None,
                        glow=(glow, glow_elapsed) if glow_on and glow is not None else None,
                    )
                    if cost < best_cost:
                        best_cost = cost
                        best_action = action

            deadline = 0
            if best_action != MODE_HEATING and MODE_HEATING in available and not slow_heat:
                deadline = self._preheat_deadline(
                    i,
                    current_temp,
                    T_outdoor_series,
                    heat_target_series,
                    dt_minutes,
                    q_solar=q_solar,
                    q_occupancy=q_occupancy,
                    # Only the deadlines read the mode before this plan (a running pre-heat goes on)
                    continuing=(initial_mode if i == 0 else current_mode) == MODE_HEATING,
                    # Waiting is predicted with the stored heat of the run (stopping now) or the last one
                    glow=(run, 0.0) if run is not None else (glow, glow_elapsed) if glow is not None else None,
                )
                if deadline:
                    best_action = MODE_HEATING
                    if i == 0:
                        preheat_blocks = deadline
            # Also when the greedy step already cools: a room held at its eco target picks
            # cooling at the edge, and without the lead the controller's start hysteresis
            # turned that start down until the lower target was 30 min away. Never over a
            # heating step.
            if (
                not deadline
                and best_action != MODE_HEATING
                and MODE_COOLING in available
                and (best_action != MODE_COOLING or i == 0)
            ):
                lead = self._precool_deadline(
                    i,
                    current_temp,
                    T_outdoor_series,
                    cool_target_series,
                    dt_minutes,
                    q_solar=q_solar,
                    q_occupancy=q_occupancy,
                    q_residual=q_residual[i:],
                    continuing=(initial_mode if i == 0 else current_mode) == MODE_COOLING,
                )
                if lead:
                    deadline = lead
                    best_action = MODE_COOLING
                    if i == 0:
                        preheat_blocks = lead

            # Compute proportional power fraction for this block
            # Use heat target for heating power, cool target for cooling power
            pf_target = heat_tgt if best_action == MODE_HEATING else cool_tgt
            pf, pf_mode = self.compute_optimal_power(
                current_temp,
                T_out,
                pf_target,
                dt_minutes,
                q_solar=qs,
                q_residual=qr,
                q_occupancy=qo,
            )
            if best_action == MODE_IDLE:
                pf = 0.0
            elif deadline:
                pf = 1.0
            elif forced and (pf_mode != best_action or pf == 0.0):
                # Past the target inside the min run: the controller continues at gentle
                # power, so the plan must not show a full-power run (a phantom 1-3 K
                # overshoot that the cover logic and the prediction line read).
                horizon = slice(i, i + self._lookahead_blocks)
                strict = (
                    max(heat_target_series[horizon])
                    if best_action == MODE_HEATING
                    else min(cool_target_series[horizon])
                )
                pf, pf_mode = self.compute_optimal_power(
                    current_temp,
                    T_out,
                    strict,
                    dt_minutes,
                    q_solar=qs,
                    q_residual=qr,
                    q_occupancy=qo,
                )
                pf = max(pf, MIN_POWER_FRACTION) if pf_mode == best_action else MIN_POWER_FRACTION
            elif pf_mode != best_action:
                # compute_optimal_power found no demand in this block's direction: the
                # deviation is smaller than the energy bias, or the room needs this
                # direction only later (look-ahead). Its fraction is then 0.0 or belongs to
                # the other direction, so it is not used. Heating runs at full power, which
                # pre-heating slow systems relies on. Cooling runs at the minimum, because
                # full power would drive an AC to its lowest setpoint.
                pf = 1.0 if best_action == MODE_HEATING else MIN_POWER_FRACTION

            # Apply action with proportional Q for accurate forward prediction
            if best_action == MODE_HEATING:
                Q = pf * self.model.Q_heat
            elif best_action == MODE_COOLING:
                Q = -(pf * self.model.Q_cool)
            else:
                Q = 0.0
            if glow_on:
                if best_action == MODE_HEATING:
                    if glow is not None:
                        # A restart cannot deliver less than the radiator still releases
                        Q = max(Q, self.model.Q_heat * self._afterglow(glow_elapsed, glow))
                    run = ((run[0] if run is not None else 0.0) + dt_minutes, 1.0)
                    glow = None
                elif run is not None:
                    glow, glow_elapsed, run = run, 0.0, None
                if Q == 0.0 and glow is not None:
                    qr = max(qr, self._afterglow(glow_elapsed, glow))
                    glow_elapsed += dt_minutes
            next_temp = self.model.predict(
                current_temp,
                T_out,
                Q,
                dt_minutes,
                q_solar=qs,
                q_residual=qr if Q == 0.0 else 0.0,
                q_occupancy=qo,
            )
            next_temp = max(temp_lo, min(next_temp, temp_hi))

            actions.append(best_action)
            temperatures.append(round(next_temp, 2))
            power_fractions.append(round(pf, 3))

            # Track run length
            if best_action == current_mode:
                blocks_in_mode += 1
            else:
                current_mode = best_action
                blocks_in_mode = 1

            current_temp = next_temp

        if (
            glow_on
            and initial_mode == MODE_HEATING
            and actions
            and actions[0] == MODE_IDLE
            and MODE_HEATING in actions[1 : 1 + RADIATOR_PAUSE_BLOCKS]
        ):
            # A radiator run is not paused for a block or two and restarted: it goes on
            resume = actions.index(MODE_HEATING, 1)
            actions[0] = MODE_HEATING
            power_fractions[0] = power_fractions[resume]

        return MPCPlan(
            actions=actions,
            temperatures=temperatures,
            dt_minutes=dt_minutes,
            power_fractions=power_fractions,
            lookahead_blocks=self._lookahead_blocks,
            preheat_blocks=preheat_blocks,
        )

    def _afterglow(self, elapsed: float, run: tuple[float, float]) -> float:
        """Learned radiator afterglow *elapsed* minutes after a run of (minutes, power) stops."""
        key = (round(elapsed, 3), round(run[0], 3), round(run[1], 3))
        cached = self._glow_cache.get(key)
        if cached is None:
            cached = compute_residual_heat(
                elapsed, HEATING_SYSTEM_RADIATOR, run[1], run[0], self.residual_scale, self.residual_tau
            )
            self._glow_cache[key] = cached
        return cached

    def _precool_deadline(
        self,
        i: int,
        T_room: float,
        T_outdoor_series: list[float],
        cool_target_series: list[float],
        dt_minutes: float,
        *,
        q_solar: list[float],
        q_occupancy: list[float],
        q_residual: list[float],
        continuing: bool,
    ) -> int:
        """Blocks from *i* to the falling cool target that waiting would miss (mirror of ``_preheat_deadline``).

        The greedy plan sees a lower cool target only ``_lookahead_blocks`` ahead, so a warm
        room started cooling 30 min before the comfort block and reached it an hour late.
        Waits one block (a running pre-cool ``PREHEAT_CONTINUE_BLOCKS``), then cools at full
        power; if that misses a later, lower cool target, the pre-cool starts now. Same lead
        limit (Priority slider) as pre-heating.
        """
        n = len(cool_target_series)
        now = cool_target_series[i]
        if self.preheat_max_blocks is not None:
            n = min(n, i + self.preheat_max_blocks + 1)
        if next((j for j in range(i + 1, n) if cool_target_series[j] < min(now, T_room)), None) is None:
            return 0
        wait = max(PREHEAT_CONTINUE_BLOCKS, self.min_run_blocks) if continuing else 1
        T = T_room
        for j in range(i, n - 1):
            waiting = j < i + wait
            Q = 0.0 if waiting else -self.model.Q_cool
            T = self.model.predict(
                T,
                T_outdoor_series[j],
                Q,
                dt_minutes,
                q_solar=q_solar[j] if j < len(q_solar) else 0.0,
                q_occupancy=q_occupancy[j] if j < len(q_occupancy) else 0.0,
                q_residual=(q_residual[j - i] if j - i < len(q_residual) else 0.0) if waiting else 0.0,
            )
            target = cool_target_series[j + 1]
            if target < now and T > target + PREHEAT_DEADLINE_MARGIN:
                return j + 1 - i
        return 0

    def _preheat_deadline(
        self,
        i: int,
        T_room: float,
        T_outdoor_series: list[float],
        heat_target_series: list[float],
        dt_minutes: float,
        *,
        q_solar: list[float],
        q_occupancy: list[float],
        continuing: bool = False,
        glow: tuple[tuple[float, float], float] | None = None,
    ) -> int:
        """Blocks from *i* to the rising heat target that waiting would miss.

        *glow* (afterglow control): (run, elapsed) whose stored heat warms the waiting blocks,
        so a run whose stored heat carries the room to the coming target is not forced.

        The greedy decision only looks ``_lookahead_blocks`` ahead, so a schedule block
        further away stayed invisible until shortly before it and a room with a radiator
        sized to its heat load started too late. Waits one block, then heats at full
        power: if that misses a later, higher heat target, the pre-heat starts now
        (as late as possible). A run already heating keeps going while waiting
        ``PREHEAT_CONTINUE_BLOCKS`` (at least the min run) would miss: re-checking a
        single block switched it off and on at the edge. The Priority slider limits how
        far ahead (``preheat_max_blocks``). 0 when no such target exists.
        """
        n = len(heat_target_series)
        now = heat_target_series[i]
        if self.preheat_max_blocks is not None:
            n = min(n, i + self.preheat_max_blocks + 1)
        rise = next((j for j in range(i + 1, n) if heat_target_series[j] > max(now, T_room)), None)
        if rise is None:
            return 0
        wait = max(PREHEAT_CONTINUE_BLOCKS, self.min_run_blocks) if continuing else 1
        T = T_room
        for j in range(i, n - 1):
            Q = 0.0 if j < i + wait else self.model.Q_heat
            qr = self._afterglow(glow[1] + (j - i) * dt_minutes, glow[0]) if glow is not None and Q == 0.0 else 0.0
            T = self.model.predict(
                T,
                T_outdoor_series[j],
                Q,
                dt_minutes,
                q_solar=q_solar[j] if j < len(q_solar) else 0.0,
                q_occupancy=q_occupancy[j] if j < len(q_occupancy) else 0.0,
                q_residual=qr,
            )
            target = heat_target_series[j + 1]
            if target > now and T < target - PREHEAT_DEADLINE_MARGIN:
                return j + 1 - i
        return 0

    def _evaluate_action(
        self,
        action: str,
        T_room: float,
        heat_target: float,
        cool_target: float,
        future_T_outdoor: list[float],
        future_heat_targets: list[float],
        future_cool_targets: list[float],
        dt_minutes: float,
        *,
        future_solar: list[float] | None = None,
        future_residual: list[float] | None = None,
        future_occupancy: list[float] | None = None,
        run: tuple[float, float] | None = None,
        glow: tuple[tuple[float, float], float] | None = None,
    ) -> float:
        """Evaluate the cost of taking an action, looking a few steps ahead.

        *run* / *glow* (afterglow control): the radiator run in progress and the last stopped
        one. Not heating carries their stored heat; heating carries its own run's after the min
        run. Heat targets past the base window are capped at the base window's last one, so
        the longer lookahead weighs the overshoot without pre-heating outside the deadline.

        Per-system lookahead (self._lookahead_blocks) extends the window for
        slow heating systems. For UFH, the HEATING hypothesis synthesizes its
        own post-heating residual afterglow so the cost function values the
        sustained-comfort benefit of pre-heating. Radiator / "" lookahead stays
        at LOOKAHEAD_BASE_BLOCKS and synthesis is gated off — byte-identical
        to pre-fix behaviour.
        """
        lookahead = min(self._lookahead_blocks, len(future_T_outdoor))
        Q = self._action_to_Q(action)
        total_cost = 0.0
        T = T_room
        temp_lo, temp_hi = self._temp_bounds(T_room)
        solar = future_solar or []
        residual = future_residual or []
        occupancy = future_occupancy or []
        glow_on = self.afterglow_control and self.heating_system_type == HEATING_SYSTEM_RADIATOR
        synthesis_enabled = (
            action == MODE_HEATING
            and self._lookahead_blocks > LOOKAHEAD_BASE_BLOCKS
            and self.min_run_blocks > 0
            and bool(self.heating_system_type)
            and not glow_on
        )
        own_run = ((run[0] if run is not None else 0.0) + self.min_run_blocks * dt_minutes, 1.0)
        heating_duration_minutes = self.min_run_blocks * dt_minutes
        if action != MODE_IDLE and not synthesis_enabled:
            Q *= self._hypothesis_power_fraction(
                action,
                T_room,
                future_T_outdoor[0] if future_T_outdoor else T_room,
                heat_target if action == MODE_HEATING else cool_target,
                dt_minutes,
                q_solar=solar[0] if solar else 0.0,
                q_residual=residual[0] if residual else 0.0,
                q_occupancy=occupancy[0] if occupancy else 0.0,
            )

        for j in range(lookahead):
            qs = solar[j] if j < len(solar) else 0.0
            qo = occupancy[j] if j < len(occupancy) else 0.0
            # Simulate HVAC for min_run_blocks (not just 1 block) to correctly
            # value sustained heating/cooling over the lookahead horizon.
            block_Q = Q if j < self.min_run_blocks else 0.0
            if glow_on and block_Q > 0.0 and run is None and glow is not None:
                # Heating again after a stop: the radiator delivers at least what it still releases
                block_Q = max(block_Q, self.model.Q_heat * self._afterglow(glow[1] + j * dt_minutes, glow[0]))
            # Residual for the idle / post-run blocks. For the HEATING
            # hypothesis on a gated slow system, synthesize the afterglow this
            # hypothetical run would generate; otherwise fall back to the
            # controller-provided current-state decay.
            if synthesis_enabled and j >= self.min_run_blocks:
                elapsed = (j - self.min_run_blocks) * dt_minutes
                qr = compute_residual_heat(
                    elapsed,
                    self.heating_system_type,
                    last_power_fraction=1.0,
                    heating_duration_minutes=heating_duration_minutes,
                )
            else:
                qr = residual[j] if j < len(residual) else 0.0
                if glow_on:
                    if action == MODE_HEATING:
                        if j >= self.min_run_blocks:
                            qr = max(qr, self._afterglow((j - self.min_run_blocks) * dt_minutes, own_run))
                        if run is None and glow is not None:
                            # The stored heat of the stopped run goes on releasing after a restart
                            qr = max(qr, self._afterglow(glow[1] + j * dt_minutes, glow[0]))
                    elif run is not None:
                        qr = max(qr, self._afterglow(j * dt_minutes, run))
                    elif glow is not None:
                        qr = max(qr, self._afterglow(glow[1] + j * dt_minutes, glow[0]))
            T = self.model.predict(
                T,
                future_T_outdoor[j],
                block_Q,
                dt_minutes,
                q_solar=qs,
                q_residual=qr if block_Q == 0.0 else 0.0,
                q_occupancy=qo,
            )
            # Clamp temperature in lookahead to prevent cost explosion
            # from implausible model predictions
            T = max(temp_lo, min(temp_hi, T))
            h_tgt = future_heat_targets[j] if j < len(future_heat_targets) else heat_target
            if glow_on and j >= LOOKAHEAD_BASE_BLOCKS and len(future_heat_targets) >= LOOKAHEAD_BASE_BLOCKS:
                h_tgt = min(h_tgt, future_heat_targets[LOOKAHEAD_BASE_BLOCKS - 1])
            c_tgt = future_cool_targets[j] if j < len(future_cool_targets) else cool_target
            # Dead-band-aware comfort cost: zero inside the band
            if T < h_tgt:
                total_cost += self.w_comfort * (T - h_tgt) ** 2
            elif T > c_tgt:
                total_cost += self.w_comfort * (T - c_tgt) ** 2
            # else: inside dead band, no comfort cost
            # Energy cost: proportional to HVAC power for min_run blocks
            if j < self.min_run_blocks and action != MODE_IDLE:
                total_cost += self.w_energy * abs(Q) / 1000.0

        return total_cost

    def _hypothesis_power_fraction(
        self,
        action: str,
        T_room: float,
        T_outdoor: float,
        target: float,
        dt_minutes: float,
        *,
        q_solar: float,
        q_residual: float,
        q_occupancy: float,
    ) -> float:
        """Power fraction a HEATING/COOLING decision would actually be applied with.

        ``optimize`` applies the closed-form proportional power, so the candidate is
        judged at that power. Judging it at full power made a strong device (large
        learned Q, e.g. an AC heating the air node) look like it always overshoots, so
        idle won and the room sat below target. Without a proportional answer for
        this block (already at target, pre-heating for a later target) the candidate
        keeps full power as before.
        """
        pf, mode = self.compute_optimal_power(
            T_room,
            T_outdoor,
            target,
            dt_minutes,
            q_solar=q_solar,
            q_residual=q_residual,
            q_occupancy=q_occupancy,
        )
        return pf if mode == action and pf > 0.0 else 1.0

    def _temp_bounds(self, T_start: float) -> tuple[float, float]:
        """Clamp range for predictions that start at *T_start*.

        A fixed 30 °C ceiling made a room above it invisible to the cost: every
        hypothesis that could not bring it below 30 within the lookahead clamped to
        the same value at every block, idle won the tie, and a weak AC stayed off
        while the room heated further.
        """
        return min(self.temp_min, T_start - CLAMP_HEADROOM_K), max(self.temp_max, T_start + CLAMP_HEADROOM_K)

    def _action_to_Q(self, action: str) -> float:
        if action == MODE_HEATING:
            return self.model.Q_heat
        if action == MODE_COOLING:
            return -self.model.Q_cool
        return 0.0

    def _is_outdoor_gated(self, mode: str, T_outdoor: float) -> bool:
        if self.override_active:
            return False
        if self.gate_rescue.get("heat" if mode == MODE_HEATING else "cool"):
            return False
        if mode == MODE_COOLING and T_outdoor < self.outdoor_cooling_min:
            return True
        if mode == MODE_HEATING and T_outdoor > self.outdoor_heating_max:
            return True
        return False

    def compute_optimal_power(
        self,
        T_room: float,
        T_outdoor: float,
        target: float,
        dt_minutes: float,
        *,
        q_solar: float = 0.0,
        q_residual: float = 0.0,
        q_occupancy: float = 0.0,
    ) -> tuple[float, str]:
        """Analytical closed-form optimal heating/cooling power.

        Returns (power_fraction in [0,1], mode).
        """
        if not math.isfinite(T_room) or not math.isfinite(target):
            return 0.0, MODE_IDLE

        dt_h = dt_minutes / 60.0
        alpha = self.model.U
        if alpha < 0.01:
            beta = alpha * dt_h  # Euler approx for tiny alpha
        else:
            beta = 1.0 - math.exp(-alpha * dt_h)

        if beta < 1e-9:
            return 0.0, MODE_IDLE

        # Drift temperature: where the room would go with no HVAC
        T_drift = T_room + beta * (T_outdoor - T_room)
        # Add predicted solar gain to drift
        if alpha > 0.01:
            T_drift += beta * self.model.Q_solar * q_solar / alpha
        else:
            T_drift += self.model.Q_solar * q_solar * dt_h
        # Add residual heat from thermal mass to drift
        if q_residual > 0:
            if alpha > 0.01:
                T_drift += beta * self.model.Q_heat * q_residual / alpha
            else:
                T_drift += self.model.Q_heat * q_residual * dt_h
        # Add predicted occupancy gain to drift
        if q_occupancy > 0:
            if alpha > 0.01:
                T_drift += beta * self.model.Q_occupancy * q_occupancy / alpha
            else:
                T_drift += self.model.Q_occupancy * q_occupancy * dt_h

        # Reference sub-target: close `approach_rate` of the remaining gap this block
        # instead of the whole gap (deadbeat). approach_rate=1.0 => T_ref == target =>
        # identical to the legacy formula. Smaller values widen the proportional band.
        # Holding power is preserved: at steady state (T_room == target) T_ref == target
        # for any approach_rate, so Q_required reduces to the holding power.
        T_ref = T_room + self.approach_rate * (target - T_room)
        Q_required = (T_ref - T_drift) * alpha / beta

        # Energy penalty: bias toward less power based on comfort/energy weights
        energy_bias = (self.w_energy / max(self.w_comfort, 0.01)) * alpha / beta * 0.1
        if Q_required > 0:
            Q_required = max(0.0, Q_required - energy_bias)
        elif Q_required < 0:
            Q_required = min(0.0, Q_required + energy_bias)

        if Q_required > 0 and self.can_heat and not self._is_outdoor_gated(MODE_HEATING, T_outdoor):
            frac = min(Q_required / max(self.model.Q_heat, 0.01), 1.0)
            return max(frac, MIN_POWER_FRACTION), MODE_HEATING
        elif Q_required < 0 and self.can_cool and not self._is_outdoor_gated(MODE_COOLING, T_outdoor):
            frac = min(abs(Q_required) / max(self.model.Q_cool, 0.01), 1.0)
            return max(frac, MIN_POWER_FRACTION), MODE_COOLING
        else:
            return 0.0, MODE_IDLE
