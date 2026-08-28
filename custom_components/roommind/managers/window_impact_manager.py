"""Track an open-window baseline for contextual thermal impact."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class WindowBaseline:
    temp: float
    started_at: float


class WindowImpactManager:
    """Keep only the baseline needed to compare a window-open trajectory."""

    def __init__(self) -> None:
        self._baselines: dict[str, WindowBaseline] = {}

    def update(self, area_id: str, window_open: bool, current_temp: float | None) -> WindowBaseline | None:
        if not window_open or current_temp is None:
            self._baselines.pop(area_id, None)
            return None
        return self._baselines.setdefault(area_id, WindowBaseline(current_temp, time.time()))

    def remove_room(self, area_id: str) -> None:
        self._baselines.pop(area_id, None)
