"""Store-backed shutdown work per device (#494, W1.6)."""

from __future__ import annotations

from custom_components.roommind.managers.pending_shutdowns import PendingShutdowns

TRV = {"entity_id": "climate.trv", "type": "trv"}
AC = {"entity_id": "climate.ac", "type": "ac"}


def test_one_entry_per_device_lists_every_waiting_room():
    p = PendingShutdowns()
    p.queue("a", [TRV, AC], 1.0)
    p.queue("b", [AC], 2.0)
    entries = dict(p.open_entries())
    assert entries["climate.ac"]["areas"] == ["a", "b"]
    assert entries["climate.trv"]["areas"] == ["a"]
    assert p.dirty


def test_requeue_by_a_listed_room_changes_nothing():
    p = PendingShutdowns()
    p.queue("a", [AC], 1.0)
    p.resolve("climate.ac", "off")
    p.dirty = False
    p.queue("a", [AC], 5.0)
    assert not p.dirty
    assert p.open_entries() == []


def test_a_new_waiting_room_resets_a_stale_outcome():
    """B-10: an old 'driven' must not settle a room that only starts waiting."""
    p = PendingShutdowns()
    p.queue("a", [AC], 1.0)
    p.resolve("climate.ac", "driven")
    p.queue("b", [AC], 9.0)
    ((eid, entry),) = p.open_entries()
    assert eid == "climate.ac" and entry["outcome"] is None and entry["since"] == 9.0


def test_room_done_only_when_every_device_has_an_outcome():
    p = PendingShutdowns()
    p.queue("a", [TRV, AC], 1.0)
    p.resolve("climate.trv", "off")
    assert p.room_done("a") == (False, False)
    p.resolve("climate.ac", "expired")
    assert p.room_done("a") == (True, True)
    assert p.room_done("unknown") == (True, False)


def test_cleanup_keeps_entries_a_waiting_room_needs_and_open_ones():
    p = PendingShutdowns()
    p.queue("a", [TRV], 1.0)
    p.queue("b", [AC], 1.0)
    p.resolve("climate.trv", "off")
    p.cleanup({"a"})
    assert "climate.trv" in p  # room a still waits (another device of it may be open)
    p.cleanup(set())
    assert "climate.trv" not in p
    assert "climate.ac" in p  # no outcome yet: never dropped


def test_forget_area_and_persistence_round_trip():
    p = PendingShutdowns()
    p.queue("a", [AC], 1.0)
    p.queue("b", [AC], 2.0)
    restored = PendingShutdowns(p.to_dict())
    assert dict(restored.open_entries())["climate.ac"]["areas"] == ["a", "b"]
    restored.forget_area("a")
    restored.forget_area("b")
    assert "climate.ac" not in restored
    broken = PendingShutdowns({"x": "junk", "y": {"areas": "a"}, "z": {"areas": ["a"], "outcome": "weird"}})
    assert [eid for eid, _ in broken.open_entries()] == ["z"]
