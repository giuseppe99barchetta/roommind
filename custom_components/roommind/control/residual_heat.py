"""Residual heat modeling for thermal mass (underfloor heating, radiators).

After heating stops, the thermal mass (floor screed, radiator body) continues
releasing stored energy into the room.  This module provides functions to
compute the decaying residual heat fraction so that the EKF and MPC can
account for it instead of mis-attributing the continued warming to solar
gain or insulation effects.
"""

from __future__ import annotations

import math
from typing import Any

from ..const import (
    HEATING_SYSTEM_PROFILES,
    HEATING_SYSTEM_RADIATOR,
    RADIATOR_SHORT_RUN_AFTERGLOW_K,
    RESIDUAL_HEAT_CUTOFF,
)


def compute_residual_heat(
    elapsed_minutes: float,
    system_type: str,
    last_power_fraction: float = 1.0,
    heating_duration_minutes: float = 0.0,
    scale: float = 1.0,
    tau_minutes: float | None = None,
    cutoff: bool = True,
) -> float:
    """Compute normalised residual heat fraction after heating stopped.

    The result is in [0, initial_fraction] and represents the fraction of
    ``beta_h`` (learned heating rate) still being delivered by thermal mass.

    The *charge_fraction* accounts for how long heating was active before
    it stopped — a brief 10-minute run barely warms the screed, whereas
    a 4-hour run fully charges it.

    Args:
        elapsed_minutes: Time since heating stopped (must be >= 0).
        system_type: Key into ``HEATING_SYSTEM_PROFILES`` (e.g. "underfloor").
        last_power_fraction: Power fraction that was active before stopping.
        heating_duration_minutes: How long heating was active before stopping.
        scale: Learned per-room multiplier on the profile's ``initial_fraction``
            (``ResidualHeatLearner``); 1.0 is the profile as is.
        tau_minutes: Learned per-room decay time; None uses the profile's. The charge
            time stays the profile's.
        cutoff: Treat values below ``RESIDUAL_HEAT_CUTOFF`` as zero (control). The
            afterglow learner compares against the uncut decay: a real radiator has no cutoff.

    Returns:
        Residual heat fraction in [0, initial_fraction * scale].  Returns 0.0 for unknown or empty
        system types (backwards-compatible default).
    """
    profile = HEATING_SYSTEM_PROFILES.get(system_type)
    if not profile or elapsed_minutes < 0:
        return 0.0

    initial = profile["initial_fraction"]
    tau_charge = profile.get("tau_charge_minutes", profile["tau_minutes"])
    tau = profile["tau_minutes"] if tau_minutes is None else tau_minutes

    if tau <= 0:
        return 0.0

    # Charge fraction: how much energy the thermal mass absorbed
    if heating_duration_minutes > 0 and tau_charge > 0:
        charge_fraction = 1.0 - math.exp(-heating_duration_minutes / tau_charge)
    else:
        charge_fraction = 1.0  # assume fully charged if duration unknown

    q = initial * scale * charge_fraction * math.exp(-elapsed_minutes / tau) * last_power_fraction
    return q if q >= RESIDUAL_HEAT_CUTOFF or not cutoff else 0.0


def build_residual_series(
    elapsed_minutes: float,
    system_type: str,
    n_blocks: int,
    dt_minutes: float = 5.0,
    last_power_fraction: float = 1.0,
    heating_duration_minutes: float = 0.0,
    scale: float = 1.0,
    tau_minutes: float | None = None,
) -> list[float]:
    """Build a decaying residual heat series for MPC lookahead.

    Each entry represents the q_residual at the start of the corresponding
    time block, evenly spaced by *dt_minutes*.

    Returns:
        List of length *n_blocks* with decaying residual fractions.
    """
    return [
        compute_residual_heat(
            elapsed_minutes + i * dt_minutes,
            system_type,
            last_power_fraction,
            heating_duration_minutes,
            scale,
            tau_minutes,
        )
        for i in range(n_blocks)
    ]


def residual_tau(system_type: str, learned: float | None = None) -> float:
    """Decay time of *system_type*'s afterglow: the learned one, else the profile's (0.0 without one)."""
    if learned is not None:
        return learned
    profile = HEATING_SYSTEM_PROFILES.get(system_type)
    return float(profile["tau_minutes"]) if profile else 0.0


def afterglow_rise_k(
    system_type: str,
    q_heat: float,
    run_minutes: float,
    scale: float = 1.0,
    tau_minutes: float | None = None,
) -> float:
    """How far the stored heat of a full-power run of *run_minutes* lifts the room after the stop."""
    q0 = compute_residual_heat(0.0, system_type, 1.0, run_minutes, scale, tau_minutes)
    return q_heat * q0 * residual_tau(system_type, tau_minutes) / 60.0


def heat_min_run_blocks(
    system_type: str,
    dt_minutes: float = 5.0,
    *,
    q_heat: float = 0.0,
    scale: float = 1.0,
    tau_minutes: float | None = None,
    fast_heater: bool = False,
) -> int:
    """Minimum heating run in blocks, a single block for radiators that store a lot of heat.

    Not with a heat-capable AC in the room (``fast_heater``): its compressor must not run
    5-min cycles. Used only with afterglow control on.
    """
    base = get_min_run_blocks(system_type, dt_minutes)
    if fast_heater or system_type != HEATING_SYSTEM_RADIATOR or q_heat <= 0 or dt_minutes <= 0:
        return base
    rise = afterglow_rise_k(system_type, q_heat, base * dt_minutes, scale, tau_minutes)
    return 1 if rise > RADIATOR_SHORT_RUN_AFTERGLOW_K else base


def learned_afterglow_info(estimator: Any) -> dict[str, Any]:
    """Learned afterglow of a radiator room for analytics and diagnostics (learning only)."""
    return {
        "residual_scale": round(estimator.residual_scale, 3),
        "residual_samples": estimator.residual_scale_n,
        "residual_decay_minutes": round(residual_tau(HEATING_SYSTEM_RADIATOR, estimator.residual_tau), 1),
    }


def get_min_run_blocks(system_type: str, dt_minutes: float = 5.0) -> int:
    """Return the minimum number of MPC blocks for a given heating system.

    Falls back to 2 blocks (the existing default) when the system type is
    unknown or empty.
    """
    profile = HEATING_SYSTEM_PROFILES.get(system_type)
    if not profile or dt_minutes <= 0:
        return 2  # existing default
    return max(2, math.ceil(profile["min_run_minutes"] / dt_minutes))
