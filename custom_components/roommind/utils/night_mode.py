"""Pure helpers for RoomMind's per-room night comfort profile."""

from __future__ import annotations

from datetime import datetime

from ..control.mpc_controller import TargetTemps


def _minutes(value: str) -> int:
    hour, minute = value.split(":", 1)
    return int(hour) * 60 + int(minute)


def night_progress(now: datetime, start: str, end: str, ramp_minutes: int) -> float:
    """Return the completed fraction of the night ramp, or zero when inactive."""
    start_minutes = _minutes(start)
    end_minutes = _minutes(end)
    current = now.hour * 60 + now.minute
    if start_minutes == end_minutes:
        return 0.0
    if start_minutes < end_minutes:
        active = start_minutes <= current < end_minutes
        elapsed = current - start_minutes
    else:
        active = current >= start_minutes or current < end_minutes
        elapsed = current - start_minutes if current >= start_minutes else current + 24 * 60 - start_minutes
    if not active:
        return 0.0
    if ramp_minutes <= 0:
        return 1.0
    return min(elapsed / ramp_minutes, 1.0)


def apply_night_targets(room: dict, targets: TargetTemps, now: datetime) -> tuple[TargetTemps, float]:
    """Apply the configured gradual night setback to logical heat/cool targets."""
    if not room.get("night_mode_enabled", False):
        return targets, 0.0
    progress = night_progress(
        now,
        str(room.get("night_start", "22:00")),
        str(room.get("night_end", "07:00")),
        int(room.get("night_ramp_minutes", 60) or 0),
    )
    if progress == 0:
        return targets, 0.0
    heat_delta = float(room.get("night_heat_delta", -0.5)) * progress
    cool_delta = float(room.get("night_cool_delta", 0.5)) * progress
    return (
        TargetTemps(
            heat=targets.heat + heat_delta if targets.heat is not None else None,
            cool=targets.cool + cool_delta if targets.cool is not None else None,
        ),
        progress,
    )
