"""Window delay state machine for RoomMind."""

from __future__ import annotations

import time


class WindowManager:
    """Manages window open/close delay logic per room."""

    def __init__(self) -> None:
        self._open_since: dict[str, float] = {}
        self._closed_since: dict[str, float] = {}
        self._paused: dict[str, bool] = {}
        self._recovery_since: dict[str, float] = {}
        self._recovery_minutes: dict[str, int] = {}
        self._seen: set[str] = set()

    def is_paused(self, area_id: str) -> bool:
        """Return True if climate control is paused due to open window."""
        return self._paused.get(area_id, False)

    def update(
        self,
        area_id: str,
        raw_open: bool,
        open_delay: int,
        close_delay: int,
        recovery_minutes: int = 0,
    ) -> bool:
        """Update window state machine and return effective window_open status.

        Returns True if climate should be paused (window considered open after delay).
        """
        now = time.time()
        was_paused = self._paused.get(area_id, False)
        first_observation = area_id not in self._seen
        self._seen.add(area_id)

        if raw_open:
            self._closed_since.pop(area_id, None)
            self._recovery_since.pop(area_id, None)
            self._recovery_minutes.pop(area_id, None)
            if not was_paused:
                if first_observation:
                    # Window already open on first observation (e.g. after HA
                    # restart).  Skip open_delay — the window has been open for
                    # an unknown duration that certainly exceeds any configured
                    # delay.
                    self._paused[area_id] = True
                else:
                    if area_id not in self._open_since:
                        self._open_since[area_id] = now
                    if now - self._open_since[area_id] >= open_delay:
                        self._paused[area_id] = True
        else:
            self._open_since.pop(area_id, None)
            if was_paused:
                if area_id not in self._closed_since:
                    self._closed_since[area_id] = now
                if now - self._closed_since[area_id] >= close_delay:
                    self._paused[area_id] = False
                    self._closed_since.pop(area_id, None)
                    if recovery_minutes > 0:
                        self._recovery_since[area_id] = now
                        self._recovery_minutes[area_id] = recovery_minutes

        return self._paused.get(area_id, False)

    def recovery_progress(self, area_id: str) -> float:
        """Return the 0..1 gradual-recovery progress after a window closes."""
        since = self._recovery_since.get(area_id)
        minutes = self._recovery_minutes.get(area_id, 0)
        if since is None or minutes <= 0:
            return 1.0
        progress = (time.time() - since) / (minutes * 60)
        if progress >= 1:
            self._recovery_since.pop(area_id, None)
            self._recovery_minutes.pop(area_id, None)
            return 1.0
        return max(0.0, progress)

    def remove_room(self, area_id: str) -> None:
        """Clean up state for a removed room."""
        self._open_since.pop(area_id, None)
        self._closed_since.pop(area_id, None)
        self._paused.pop(area_id, None)
        self._recovery_since.pop(area_id, None)
        self._recovery_minutes.pop(area_id, None)
        self._seen.discard(area_id)
