"""Inputs the room model learned from, averaged over each history interval (analytics backtest).

The history is written every few cycles while the model trains every cycle, so a history row
carries the mean of the cycles since the last row. Only an interval the model can replay with
its normal equation is kept: every cycle trained, in one mode (heating / cooling / idle), with
the window certainly closed (no open window, open delay or unknown sensor). Anything else
writes no inputs and the backtest leaves the interval out.
"""

from __future__ import annotations

from ..const import MODE_COOLING, MODE_HEATING, MODE_IDLE
from ..utils.history_store import MODEL_INPUT_FIELDS

_SIGN = {MODE_HEATING: 1.0, MODE_COOLING: -1.0, MODE_IDLE: 0.0}


class _Interval:
    __slots__ = ("cycles", "mode", "n", "ok", "sums")

    def __init__(self) -> None:
        self.cycles = 0
        self.n = 0
        self.ok = True
        self.mode: str | None = None
        self.sums = dict.fromkeys(MODEL_INPUT_FIELDS, 0.0)


class ModelInputs:
    """Per-room accumulator of the model's training inputs between two history rows."""

    def __init__(self) -> None:
        self._rooms: dict[str, _Interval] = {}

    def begin_cycle(self, area_id: str) -> None:
        """A cycle of the room starts: it has to train for the interval to stay usable."""
        self._rooms.setdefault(area_id, _Interval()).cycles += 1

    def note(
        self,
        area_id: str,
        *,
        mode: str | None,
        power: float,
        solar: float,
        residual: float,
        occupancy: float,
        window_closed: bool,
    ) -> None:
        """The model trained this cycle with these inputs (power = delivered share 0-1)."""
        interval = self._rooms.setdefault(area_id, _Interval())
        if mode not in _SIGN or not window_closed:
            interval.ok = False
            return
        if interval.mode is not None and interval.mode != mode:
            interval.ok = False
            return
        interval.mode = mode
        interval.n += 1
        interval.sums["model_power"] += _SIGN[mode] * power
        interval.sums["model_solar"] += solar
        interval.sums["model_residual"] += residual
        interval.sums["model_occupancy"] += occupancy

    def unusable(self, area_id: str) -> None:
        """The room did not train this cycle (learning off, no outdoor temperature, ...)."""
        self._rooms.setdefault(area_id, _Interval()).ok = False

    def take(self, area_id: str) -> dict[str, float]:
        """Means for the history row being written, or {} when the interval is not usable."""
        interval = self._rooms.pop(area_id, None)
        if interval is None or not interval.ok or interval.n == 0 or interval.n != interval.cycles:
            return {}
        return {key: round(total / interval.n, 3) for key, total in interval.sums.items()}

    def reset(self) -> None:
        """A history write happened: every room starts a new interval."""
        self._rooms.clear()

    def remove_room(self, area_id: str) -> None:
        self._rooms.pop(area_id, None)
