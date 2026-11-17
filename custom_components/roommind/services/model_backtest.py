"""How far the room model is off one hour ahead, measured on the recorded history.

For every recorded point the model starts from the reading one hour earlier and runs forward
with what really happened in between (delivered heating/cooling share, outdoor temperature,
sun behind the covers, residual heat, occupancy): the inputs the model learned from, recorded
per history row (``model_*`` columns, see managers/model_inputs.py). The difference to the
reading at the end is the model's error over that hour.

It is today's model applied to the past, not a forecast made back then: over long ranges it
mixes seasons and changes to the room. Rows without inputs (before the columns existed, an
open or unknown window, a mode change or a cycle without training inside the interval) break
the chain and the hours crossing them are left out instead of guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..control.thermal_model import RCModel

BACKTEST_HORIZON_S = 3600.0
# Rows come every ~3 minutes; a longer step means a missed row (restart, skipped room, failed
# write) whose interval the next row's inputs do not describe, so it breaks the chain
MAX_STEP_S = 270.0
# How much earlier than one hour the start reading may be (rows come every ~3 minutes)
MAX_START_SLACK_S = 300.0
# Windows needed before a figure is shown
MIN_BACKTEST_WINDOWS = 12


@dataclass
class BacktestFigures:
    """Mean absolute and signed error after one hour, per kind of hour."""

    n: int = 0
    abs_sum: float = 0.0
    signed_sum: float = 0.0

    def add(self, error: float) -> None:
        self.n += 1
        self.abs_sum += abs(error)
        self.signed_sum += error

    def as_dict(self) -> dict:
        if self.n < MIN_BACKTEST_WINDOWS:
            return {"n": self.n, "mae": None, "bias": None}
        return {
            "n": self.n,
            "mae": round(self.abs_sum / self.n, 3),
            "bias": round(self.signed_sum / self.n, 3),
        }


@dataclass
class BacktestResult:
    predicted: dict[float, float] = field(default_factory=dict)
    idle: BacktestFigures = field(default_factory=BacktestFigures)
    active: BacktestFigures = field(default_factory=BacktestFigures)

    @property
    def has_figure(self) -> bool:
        """At least one kind of hour has enough windows for a figure."""
        return max(self.idle.n, self.active.n) >= MIN_BACKTEST_WINDOWS

    def figures(self) -> dict:
        return {
            "horizon_minutes": round(BACKTEST_HORIZON_S / 60),
            "idle": self.idle.as_dict(),
            "active": self.active.as_dict(),
        }


def _reading(p: dict) -> bool:
    return p.get("room_temp") is not None and p.get("outdoor_temp") is not None


def backtest(points: list[dict], model: RCModel, count_from: float | None = None) -> BacktestResult:
    """Run the one-hour backtest over *points* (sorted by ``ts``, typed like _csv_to_points).

    A row carries the mean inputs of the interval that *ends* at it, so the step from row k to
    row k+1 starts from row k's readings and runs with row k+1's inputs. ``predicted`` maps the
    end timestamp of each hour to the model's temperature. An hour counts as active when the
    model saw heating or cooling in it. Points before *count_from* only serve as the start of
    the first hours of a range; hours ending before it are neither returned nor counted.
    """
    result = BacktestResult()
    n = len(points)
    if n < 2 or model.U <= 0:
        return result

    ts = [p["ts"] for p in points]
    reading = [_reading(p) for p in points]
    # breaks[k]: steps up to point k that cannot be simulated (no reading, no inputs, a gap)
    breaks = [0] * n
    for k in range(1, n):
        bad = (
            not reading[k - 1]
            or points[k].get("model_power") is None
            or ts[k] - ts[k - 1] > MAX_STEP_S
            or ts[k] <= ts[k - 1]
        )
        breaks[k] = breaks[k - 1] + int(bad)

    j = 0
    for i in range(1, n):
        if points[i].get("room_temp") is None or (count_from is not None and ts[i] < count_from):
            continue
        start = ts[i] - BACKTEST_HORIZON_S
        while j + 1 < i and ts[j + 1] <= start:
            j += 1
        if ts[j] > start or ts[i] - ts[j] > BACKTEST_HORIZON_S + MAX_START_SLACK_S:
            continue
        if breaks[i] - breaks[j]:
            continue
        T = points[j]["room_temp"]
        active = False
        for k in range(j, i):
            step = points[k + 1]
            dt = (ts[k + 1] - ts[k]) / 60.0
            share = step["model_power"]
            if share > 0:
                Q = share * model.Q_heat
            elif share < 0:
                Q = share * model.Q_cool
            else:
                Q = 0.0
            active = active or Q != 0.0
            T = model.predict(
                T,
                points[k]["outdoor_temp"],
                Q,
                dt,
                q_solar=step.get("model_solar") or 0.0,
                q_residual=step.get("model_residual") or 0.0,
                q_occupancy=step.get("model_occupancy") or 0.0,
            )
        result.predicted[ts[i]] = round(T, 2)
        (result.active if active else result.idle).add(T - points[i]["room_temp"])
    return result
