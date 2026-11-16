"""Learned offset between an AC's own sensor and the room sensor (upstream #461).

An AC regulates on the sensor in its indoor unit, not on the room sensor RoomMind controls
against. While the compressor runs, that sensor often reads differently from the room: a wall
unit under the ceiling draws its intake from the warm layer, so it reads warm while heating. The
unit then stops at a different room temperature than the setpoint says.

The tracker learns ``T_device - T_room`` per AC for heating, cooling and idle (the three differ).
Upstream reads the state from ``hvac_action``; the fork's coordinator also derives it from the AC's
power sensor (units such as Hisense ConnectLife report no hvac_action), so ``observe`` takes the
state itself. The first minutes after a start or stop are skipped: the offset builds up or fades
with the airflow.
"""

from __future__ import annotations

from ..const import (
    HEAD_OFFSET_ALPHA,
    HEAD_OFFSET_GRID_K,
    HEAD_OFFSET_HYSTERESIS_K,
    HEAD_OFFSET_MAX_K,
    HEAD_OFFSET_MIN_SAMPLES,
    HEAD_OFFSET_SETTLE_S,
)

STATES = ("heat", "cool", "idle")


class HeadOffsetTracker:
    """Per-AC EMA of the device sensor's offset from the room sensor, for heating, cooling and idle."""

    def __init__(self) -> None:
        # {entity_id: {"heat"|"cool"|"idle": [offset_k, n_samples]}}
        self._offsets: dict[str, dict[str, list[float]]] = {}
        # {entity_id: (state, since)}
        self._state_since: dict[str, tuple[str, float]] = {}
        # {(entity_id, intent): offset on the HEAD_OFFSET_GRID_K grid handed out last}
        self._applied: dict[tuple[str, str], float] = {}
        self.dirty = False

    def observe(
        self,
        entity_id: str,
        state: str | None,
        device_temp: float | None,
        room_temp: float | None,
        now: float,
    ) -> None:
        """Fold one reading in. Only readings from a state the device has been in long enough count.

        *state*: "heat", "cool" or "idle"; None (no signal, fan only, unavailable) resets the timer.
        """
        if state not in STATES or device_temp is None or room_temp is None:
            self._state_since.pop(entity_id, None)
            return
        since = self._state_since.get(entity_id)
        if since is None or since[0] != state:
            self._state_since[entity_id] = (state, now)
            return
        if now - since[1] < HEAD_OFFSET_SETTLE_S:
            return
        delta = device_temp - room_temp
        if abs(delta) > HEAD_OFFSET_MAX_K:
            return
        entry = self._offsets.setdefault(entity_id, {}).get(state)
        if entry is None:
            self._offsets[entity_id][state] = [delta, 1]
        else:
            entry[0] += HEAD_OFFSET_ALPHA * (delta - entry[0])
            entry[1] += 1
        self.dirty = True

    def offset(self, entity_id: str, intent: str) -> float:
        """Learned offset (K) for ``intent`` ("heat"/"cool"/"idle"), 0.0 until enough readings."""
        entry = self._offsets.get(entity_id, {}).get(intent)
        if entry is None or entry[1] < HEAD_OFFSET_MIN_SAMPLES:
            return 0.0
        # On a grid with hysteresis: hundredths of EMA noise would move the setpoint of a
        # whole-degree device across a rounding edge
        key = (entity_id, intent)
        applied = self._applied.get(key)
        if applied is None or abs(entry[0] - applied) > HEAD_OFFSET_HYSTERESIS_K:
            applied = round(entry[0] / HEAD_OFFSET_GRID_K) * HEAD_OFFSET_GRID_K + 0.0
            self._applied[key] = applied
        return applied

    def prune(self, known_eids: set[str]) -> None:
        """Drop offsets of devices that are no longer configured anywhere."""
        stale = [eid for eid in self._offsets if eid not in known_eids]
        for eid in stale:
            del self._offsets[eid]
        for eid in [eid for eid in self._state_since if eid not in known_eids]:
            del self._state_since[eid]
        for key in [key for key in self._applied if key[0] not in known_eids]:
            del self._applied[key]
        if stale:
            self.dirty = True

    def get_state(self) -> dict:
        """Persistable state (the settle timers are not kept across restarts)."""
        return {eid: {d: [round(v[0], 3), int(v[1])] for d, v in dirs.items()} for eid, dirs in self._offsets.items()}

    def load_state(self, data: dict) -> None:
        """Restore persisted offsets, skipping malformed entries."""
        self._offsets = {}
        self._applied = {}
        for eid, dirs in (data or {}).items():
            if not isinstance(dirs, dict):
                continue
            for state, value in dirs.items():
                if state not in STATES:
                    continue
                try:
                    offset, n = float(value[0]), int(value[1])
                except (TypeError, ValueError, IndexError):
                    continue
                if abs(offset) <= HEAD_OFFSET_MAX_K:
                    self._offsets.setdefault(eid, {})[state] = [offset, n]
