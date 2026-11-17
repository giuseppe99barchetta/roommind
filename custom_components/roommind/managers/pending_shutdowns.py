"""Shutdown work for devices of deleted or resting rooms, kept across restarts (#494, W1.6).

One entry per device, deduplicated: ``{entity_id: {"since": ts, "areas": [area_id, ...],
"outcome": None | "off" | "expired" | "driven", "device": {...}}}``. ``areas`` lists every room
waiting for the device; ``device`` is its configuration (valve entities for the release).

- A new request for a device (an area not listed yet) resets its outcome and ``since``: the
  device is evaluated again against the owners of now, so an old ``driven`` / ``off`` /
  ``expired`` never settles a room that only starts waiting.
- The coordinator works on entries without outcome and records one: ``off`` (confirmed off),
  ``driven`` (a running room or the boiler manager owns it), ``expired`` (still not off after
  ``PENDING_SHUTDOWN_EXPIRY_S``).
- A resting room is done once every device it drove has an outcome.
- An entry is dropped once it has an outcome and no listed room still waits for it.
"""

from __future__ import annotations

from typing import Any

PENDING_SHUTDOWN_EXPIRY_S = 24 * 3600
OUTCOMES = ("off", "expired", "driven")


class PendingShutdowns:
    """Store-backed list of device switch-offs still to do."""

    def __init__(self, data: dict | None = None) -> None:
        self._entries: dict[str, dict[str, Any]] = {}
        # Bumped whenever a room starts waiting for a device (in memory): a shutdown whose
        # command was awaited while it changed does not settle the newcomer
        self._revisions: dict[str, int] = {}
        self.dirty = False
        for eid, entry in (data or {}).items():
            if not isinstance(entry, dict) or not isinstance(entry.get("areas"), list):
                continue
            outcome = entry.get("outcome")
            self._entries[eid] = {
                "since": float(entry.get("since", 0.0)),
                "areas": [a for a in entry["areas"] if isinstance(a, str)],
                "outcome": outcome if outcome in OUTCOMES else None,
                "device": dict(entry.get("device") or {"entity_id": eid}),
            }

    def to_dict(self) -> dict:
        return {eid: {**e, "areas": list(e["areas"]), "device": dict(e["device"])} for eid, e in self._entries.items()}

    def __contains__(self, entity_id: str) -> bool:
        return entity_id in self._entries

    def queue(self, area_id: str, devices: list[dict], now: float) -> None:
        """*area_id* waits for its *devices* to be switched off."""
        for dev in devices:
            eid = dev.get("entity_id")
            if not eid:
                continue
            entry = self._entries.get(eid)
            if entry is None:
                self._entries[eid] = {"since": now, "areas": [area_id], "outcome": None, "device": dict(dev)}
            elif area_id not in entry["areas"]:
                entry["areas"].append(area_id)
                entry["outcome"] = None
                entry["since"] = now
            else:
                continue
            self._revisions[eid] = self._revisions.get(eid, 0) + 1
            self.dirty = True

    def revision(self, entity_id: str) -> int:
        """Changes when a room starts waiting for *entity_id*."""
        return self._revisions.get(entity_id, 0)

    def open_entries(self) -> list[tuple[str, dict[str, Any]]]:
        """Entries still without an outcome, in queue order."""
        return [(eid, e) for eid, e in self._entries.items() if e["outcome"] is None]

    def get(self, entity_id: str) -> dict[str, Any] | None:
        """The live entry of *entity_id* (None once dropped)."""
        return self._entries.get(entity_id)

    def resolve(self, entity_id: str, outcome: str) -> None:
        entry = self._entries.get(entity_id)
        if entry is not None and entry["outcome"] != outcome:
            entry["outcome"] = outcome
            self.dirty = True

    def expired(self, entity_id: str, now: float) -> bool:
        entry = self._entries.get(entity_id)
        return entry is not None and now - entry["since"] >= PENDING_SHUTDOWN_EXPIRY_S

    def room_done(self, area_id: str) -> tuple[bool, bool]:
        """(every device *area_id* waits for has an outcome, one of them expired)."""
        mine = [e for e in self._entries.values() if area_id in e["areas"]]
        return all(e["outcome"] is not None for e in mine), any(e["outcome"] == "expired" for e in mine)

    def forget_area(self, area_id: str) -> None:
        """*area_id* no longer waits (resumed, or its waiting was dropped)."""
        for eid in list(self._entries):
            entry = self._entries[eid]
            if area_id in entry["areas"]:
                entry["areas"].remove(area_id)
                self.dirty = True
                if not entry["areas"]:
                    del self._entries[eid]

    def cleanup(self, waiting: set[str]) -> None:
        """Drop entries with an outcome that no room in *waiting* (resting, not done) needs."""
        for eid in list(self._entries):
            entry = self._entries[eid]
            if entry["outcome"] is not None and not (set(entry["areas"]) & waiting):
                del self._entries[eid]
                self.dirty = True
