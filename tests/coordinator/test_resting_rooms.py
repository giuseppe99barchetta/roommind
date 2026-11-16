"""Rooms whose Home Assistant area was deleted rest (#494): fork lifecycle on store-backed shutdowns."""

from __future__ import annotations

import copy
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.managers.pending_shutdowns import PENDING_SHUTDOWN_EXPIRY_S
from custom_components.roommind.utils.area_utils import REST_SHUTDOWN_EXPIRED, REST_SWITCHED_OFF

from .conftest import _create_coordinator

TURN_OFF = "custom_components.roommind.coordinator.async_turn_off_climate"
COORD = "custom_components.roommind.coordinator"


class FakeStore:
    """The store calls the resting-room code uses, on plain dicts."""

    def __init__(self, rooms: dict, settings: dict | None = None) -> None:
        self.rooms = copy.deepcopy(rooms)
        self.settings = {"climate_control_active": True, **(settings or {})}

    def get_rooms(self) -> dict:
        return copy.deepcopy(self.rooms)

    def get_room(self, area_id: str) -> dict | None:
        room = self.rooms.get(area_id)
        return copy.deepcopy(room) if room is not None else None

    def get_settings(self) -> dict:
        return copy.deepcopy(self.settings)

    def get_thermal_data(self) -> dict:
        return {}

    async def async_update_room(self, area_id: str, changes: dict) -> dict:
        self.rooms[area_id].update(changes)
        return copy.deepcopy(self.rooms[area_id])

    async def async_save_settings(self, changes: dict) -> dict:
        self.settings.update(copy.deepcopy(changes))
        return copy.deepcopy(self.settings)

    async def async_delete_room(self, area_id: str) -> None:
        del self.rooms[area_id]


def _room(area_id: str, *eids: str, **extra) -> dict:
    return {
        "area_id": area_id,
        "climate_control_enabled": True,
        "devices": [{"entity_id": e, "type": "ac" if "ac" in e else "trv", "role": "auto"} for e in eids],
        **extra,
    }


@contextmanager
def areas_missing(*area_ids: str):
    """Pretend these areas are gone from the area registry."""

    def _has(hass, area_id):
        return area_id not in area_ids

    with (
        patch("custom_components.roommind.utils.area_utils.has_area", side_effect=_has),
        patch(f"{COORD}.has_area", side_effect=_has),
    ):
        yield


def _states(hass, states: dict):
    def _get(eid):
        value = states.get(eid)
        if value is None:
            return None
        st = MagicMock()
        st.state = value
        st.attributes = {"hvac_modes": ["off", "heat", "cool"]}
        return st

    hass.states.get = MagicMock(side_effect=_get)


@pytest.fixture(autouse=True)
def _entity_registry():
    """The fixture hass has no loaded entity registry: a room's entities are looked up in an empty one."""
    with patch("homeassistant.helpers.entity_registry.async_get", return_value=MagicMock(entities={})):
        yield


def _coord(hass, mock_config_entry, store):
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


def _sent(turn_off):
    return [c.args[1] for c in turn_off.await_args_list]


@pytest.mark.asyncio
async def test_resting_room_is_switched_off_once_and_marked(hass, mock_config_entry):
    store = FakeStore({"bed": _room("bed", "climate.bed_trv", "climate.bed_ac")})
    _states(hass, {"climate.bed_trv": "heat", "climate.bed_ac": "heat"})
    coordinator = _coord(hass, mock_config_entry, store)
    with areas_missing("bed"), patch(TURN_OFF, new=AsyncMock()) as turn_off:
        await coordinator.async_room_paused("bed")
        await coordinator._async_process_pending_shutdowns()
        assert sorted(_sent(turn_off)) == ["climate.bed_ac", "climate.bed_trv"]
        assert not store.rooms["bed"].get(REST_SWITCHED_OFF)  # devices still report heat
        _states(hass, {"climate.bed_trv": "off", "climate.bed_ac": "off"})
        await coordinator._async_process_pending_shutdowns()
        assert store.rooms["bed"][REST_SWITCHED_OFF] is True
        turn_off.reset_mock()
        await coordinator._async_process_pending_shutdowns()
    turn_off.assert_not_awaited()
    assert store.settings["pending_shutdowns"] == {}


@pytest.mark.asyncio
async def test_pause_releases_the_dehumidifier_and_forgets_run_state(hass, mock_config_entry):
    store = FakeStore({"bed": _room("bed", "climate.bed_trv", dehumidifier={"entity_id": "switch.dehum"})})
    coordinator = _coord(hass, mock_config_entry, store)
    coordinator._previous_modes["bed"] = "heating"
    coordinator._model_manager.update_residual_scale("bed", 3.0)
    with (
        areas_missing("bed"),
        patch.object(coordinator._dehumidifier_manager, "release", new=AsyncMock()) as release,
    ):
        await coordinator.async_room_paused("bed")
    release.assert_awaited_once()
    assert "bed" not in coordinator._previous_modes
    assert coordinator._model_manager.get_residual_scale("bed") != 1.0  # learned model kept


@pytest.mark.asyncio
async def test_unavailable_device_survives_a_restart_and_is_switched_off_when_back(hass, mock_config_entry):
    store = FakeStore({"bed": _room("bed", "climate.bed_ac")})
    states = {"climate.bed_ac": "unavailable"}
    _states(hass, states)
    coordinator = _coord(hass, mock_config_entry, store)
    with areas_missing("bed"), patch(TURN_OFF, new=AsyncMock()) as turn_off:
        await coordinator._async_process_pending_shutdowns()
        turn_off.assert_not_awaited()  # nothing to send to an unavailable device
        assert "climate.bed_ac" in store.settings["pending_shutdowns"]
        # restart: a new coordinator loads the pending work from the settings
        restarted = _coord(hass, mock_config_entry, store)
        restarted._pending_shutdowns.__init__(store.settings["pending_shutdowns"])
        states["climate.bed_ac"] = "heat"
        await restarted._async_process_pending_shutdowns()
        assert _sent(turn_off) == ["climate.bed_ac"]
        states["climate.bed_ac"] = "off"
        await restarted._async_process_pending_shutdowns()
    assert store.rooms["bed"][REST_SWITCHED_OFF] is True


@pytest.mark.asyncio
async def test_expiry_marks_the_room_and_does_not_requeue(hass, mock_config_entry):
    store = FakeStore({"bed": _room("bed", "climate.bed_ac")})
    _states(hass, {"climate.bed_ac": "unavailable"})
    coordinator = _coord(hass, mock_config_entry, store)
    with areas_missing("bed"), patch(TURN_OFF, new=AsyncMock()), patch(f"{COORD}.time") as clock:
        clock.time.return_value = 1000.0
        await coordinator._async_process_pending_shutdowns()
        clock.time.return_value = 1000.0 + PENDING_SHUTDOWN_EXPIRY_S
        await coordinator._async_process_pending_shutdowns()
        assert store.rooms["bed"][REST_SWITCHED_OFF] is True
        assert store.rooms["bed"][REST_SHUTDOWN_EXPIRED] is True
        clock.time.return_value += 3600
        await coordinator._async_process_pending_shutdowns()
        restarted = _coord(hass, mock_config_entry, store)
        await restarted._async_process_pending_shutdowns()
    assert store.settings["pending_shutdowns"] == {}
    assert "climate.bed_ac" not in restarted._pending_shutdowns


@pytest.mark.asyncio
async def test_room_is_marked_only_when_the_last_device_has_an_outcome(hass, mock_config_entry):
    store = FakeStore({"bed": _room("bed", "climate.bed_trv", "climate.bed_ac")})
    states = {"climate.bed_trv": "off", "climate.bed_ac": "unavailable"}
    _states(hass, states)
    coordinator = _coord(hass, mock_config_entry, store)
    with areas_missing("bed"), patch(TURN_OFF, new=AsyncMock()):
        await coordinator._async_process_pending_shutdowns()
        assert not store.rooms["bed"].get(REST_SWITCHED_OFF)
        states["climate.bed_ac"] = "off"
        await coordinator._async_process_pending_shutdowns()
    assert store.rooms["bed"][REST_SWITCHED_OFF] is True


@pytest.mark.asyncio
async def test_device_shared_by_two_resting_rooms_is_switched_off_and_resolves_both(hass, mock_config_entry):
    """B-01: two resting rooms no longer protect each other's device."""
    store = FakeStore({"bed": _room("bed", "climate.shared_ac"), "office": _room("office", "climate.shared_ac")})
    states = {"climate.shared_ac": "unavailable"}
    _states(hass, states)
    coordinator = _coord(hass, mock_config_entry, store)
    with areas_missing("bed", "office"), patch(TURN_OFF, new=AsyncMock()) as turn_off:
        await coordinator._async_process_pending_shutdowns()
        restarted = _coord(hass, mock_config_entry, store)
        restarted._pending_shutdowns.__init__(store.settings["pending_shutdowns"])
        states["climate.shared_ac"] = "heat"
        await restarted._async_process_pending_shutdowns()
        states["climate.shared_ac"] = "off"
        await restarted._async_process_pending_shutdowns()
    # one command per cycle for both rooms (the last one confirms an off device, as W1.6 does)
    assert _sent(turn_off) == ["climate.shared_ac", "climate.shared_ac"]
    assert store.rooms["bed"][REST_SWITCHED_OFF] is True
    assert store.rooms["office"][REST_SWITCHED_OFF] is True


@pytest.mark.asyncio
async def test_device_of_a_running_room_is_left_on_until_that_room_rests_too(hass, mock_config_entry):
    """B-10: 'driven' was right while the owner ran; once the owner rests the device goes off."""
    store = FakeStore(
        {"bed": _room("bed", "climate.shared_ac", "climate.bed_trv"), "living": _room("living", "climate.shared_ac")}
    )
    states = {"climate.shared_ac": "heat", "climate.bed_trv": "unavailable"}
    _states(hass, states)
    coordinator = _coord(hass, mock_config_entry, store)
    with patch(TURN_OFF, new=AsyncMock()) as turn_off:
        with areas_missing("bed"):
            await coordinator._async_process_pending_shutdowns()
        assert "climate.shared_ac" not in _sent(turn_off)  # living drives it
        with areas_missing("bed", "living"):
            await coordinator._async_process_pending_shutdowns()
    assert "climate.shared_ac" in _sent(turn_off)


@pytest.mark.asyncio
async def test_deleting_a_resting_room_keeps_its_unfinished_shutdown(hass, mock_config_entry):
    """B-06: the work survives the room record and a restart."""
    store = FakeStore({"bed": _room("bed", "climate.bed_ac")})
    states = {"climate.bed_ac": "unavailable"}
    _states(hass, states)
    coordinator = _coord(hass, mock_config_entry, store)
    with areas_missing("bed"), patch(TURN_OFF, new=AsyncMock()) as turn_off:
        await coordinator._async_process_pending_shutdowns()
        room = store.get_room("bed")
        coordinator.note_room_deleted("bed", room)
        await coordinator.async_save_pending_shutdowns()
        await store.async_delete_room("bed")
        restarted = _coord(hass, mock_config_entry, store)
        restarted._pending_shutdowns.__init__(store.settings["pending_shutdowns"])
        states["climate.bed_ac"] = "heat"
        await restarted._async_process_pending_shutdowns()
    assert _sent(turn_off) == ["climate.bed_ac"]


@pytest.mark.asyncio
async def test_deleting_a_completed_resting_room_sends_nothing(hass, mock_config_entry):
    store = FakeStore({"bed": _room("bed", "climate.bed_ac", **{REST_SWITCHED_OFF: True})})
    coordinator = _coord(hass, mock_config_entry, store)
    assert coordinator.note_room_deleted("bed", store.get_room("bed")) is False
    assert coordinator._pending_shutdowns.open_entries() == []


@pytest.mark.asyncio
async def test_resume_clears_the_mark_and_recreates_entities(hass, mock_config_entry):
    store = FakeStore({"bed": _room("bed", "climate.bed_ac", **{REST_SWITCHED_OFF: True})})
    coordinator = _coord(hass, mock_config_entry, store)
    coordinator._pending_shutdowns.queue("bed", store.rooms["bed"]["devices"], 1.0)
    with patch.object(coordinator, "async_room_added", new=AsyncMock()) as added:
        await coordinator.async_room_resumed("bed")
    added.assert_awaited_once()
    assert store.rooms["bed"][REST_SWITCHED_OFF] is False
    assert "climate.bed_ac" not in coordinator._pending_shutdowns


@pytest.mark.asyncio
async def test_area_back_without_an_event_clears_the_mark(hass, mock_config_entry):
    store = FakeStore({"bed": _room("bed", "climate.bed_ac", **{REST_SWITCHED_OFF: True})})
    coordinator = _coord(hass, mock_config_entry, store)
    with patch(TURN_OFF, new=AsyncMock()) as turn_off:
        await coordinator._async_process_pending_shutdowns()
    turn_off.assert_not_awaited()
    assert store.rooms["bed"][REST_SWITCHED_OFF] is False


@pytest.mark.asyncio
async def test_global_control_off_keeps_a_resting_room_waiting_and_drops_deleted_work(hass, mock_config_entry):
    store = FakeStore({"bed": _room("bed", "climate.bed_ac")}, {"climate_control_active": False})
    _states(hass, {"climate.bed_ac": "heat", "climate.gone_ac": "heat"})
    coordinator = _coord(hass, mock_config_entry, store)
    coordinator._pending_shutdowns.queue("bed", store.rooms["bed"]["devices"], 1.0)
    coordinator._pending_shutdowns.queue("gone", [{"entity_id": "climate.gone_ac"}], 1.0)
    with areas_missing("bed"), patch(TURN_OFF, new=AsyncMock()) as turn_off:
        await coordinator._async_process_pending_shutdowns()
    turn_off.assert_not_awaited()
    assert "climate.bed_ac" in coordinator._pending_shutdowns
    assert "climate.gone_ac" not in coordinator._pending_shutdowns


@pytest.mark.asyncio
async def test_room_control_off_queues_nothing(hass, mock_config_entry):
    store = FakeStore({"bed": _room("bed", "climate.bed_ac", climate_control_enabled=False)})
    _states(hass, {"climate.bed_ac": "heat"})
    coordinator = _coord(hass, mock_config_entry, store)
    with areas_missing("bed"), patch(TURN_OFF, new=AsyncMock()) as turn_off:
        await coordinator._async_process_pending_shutdowns()
    turn_off.assert_not_awaited()
    assert not store.rooms["bed"].get(REST_SWITCHED_OFF)


@pytest.mark.asyncio
async def test_resting_room_gets_no_entities_from_a_save(hass, mock_config_entry):
    """B-03: a stale card or client saving a resting room does not bring its entities back."""
    store = FakeStore({"bed": _room("bed", "climate.bed_ac")})
    coordinator = _coord(hass, mock_config_entry, store)
    coordinator.async_add_entities = MagicMock()
    with areas_missing("bed"):
        await coordinator.async_room_added(store.get_room("bed"))
    coordinator.async_add_entities.assert_not_called()
    assert "bed" not in coordinator._entity_areas


@pytest.mark.asyncio
async def test_cycle_skips_a_resting_room_and_a_room_paused_meanwhile(hass, mock_config_entry):
    """B-05: the live check after an await covers a pause during the cycle."""
    store = FakeStore({"bed": _room("bed", "climate.bed_ac")})
    coordinator = _coord(hass, mock_config_entry, store)
    with areas_missing("bed"):
        assert coordinator._room_still_runs("bed") is False
    assert coordinator._room_still_runs("bed") is True
    assert coordinator._room_still_runs("nope") is False


def test_startup_removes_entities_of_a_room_whose_area_went_while_stopped(hass, mock_config_entry):
    """B-04: an area deleted while HA was stopped sends no event; startup cleanup handles it."""
    store = FakeStore({"bed": _room("bed", "climate.bed_ac"), "living": _room("living", "climate.living_ac")})
    coordinator = _coord(hass, mock_config_entry, store)
    entries = [
        MagicMock(platform="roommind", unique_id="roommind_bed_target_temp", entity_id="sensor.bed_target"),
        MagicMock(platform="roommind", unique_id="roommind_living_target_temp", entity_id="sensor.living_target"),
    ]
    registry = MagicMock(entities=MagicMock(values=MagicMock(return_value=entries)))
    with (
        areas_missing("bed"),
        patch("homeassistant.helpers.entity_registry.async_get", return_value=registry),
    ):
        coordinator.cleanup_orphaned_entities()
    removed = [c.args[0] for c in registry.async_remove.call_args_list]
    assert removed == ["sensor.bed_target"]


@pytest.mark.asyncio
async def test_valve_protection_skips_a_resting_room(hass, mock_config_entry):
    from custom_components.roommind.utils.area_utils import rooms_with_area

    store = FakeStore({"bed": _room("bed", "climate.bed_trv"), "living": _room("living", "climate.living_trv")})
    with areas_missing("bed"):
        assert set(rooms_with_area(hass, store.get_rooms())) == {"living"}


@pytest.mark.asyncio
async def test_room_paused_while_it_is_processed_is_not_published(hass, mock_config_entry):
    """B-REV-01: the state of a room that rested during its processing is dropped, not used."""
    from .conftest import SAMPLE_ROOM, _make_store_mock, make_mock_states_get

    room = {**SAMPLE_ROOM}
    aid = room["area_id"]
    store = _make_store_mock({aid: room})
    store.get_room = MagicMock(side_effect=lambda a: room if a == aid else None)
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()
    hass.states.get = make_mock_states_get()
    coordinator = _create_coordinator(hass, mock_config_entry)
    missing: set[str] = set()

    async def _process(room, *args, **kwargs):
        missing.add(aid)  # the area is deleted while this room is processed
        coordinator._previous_modes[aid] = "heating"
        return {"mode": "heating"}

    with (
        patch("custom_components.roommind.utils.area_utils.has_area", side_effect=lambda h, a: a not in missing),
        patch(f"{COORD}.has_area", side_effect=lambda h, a: a not in missing),
        patch.object(coordinator, "_async_process_room", side_effect=_process),
    ):
        result = await coordinator._async_update_data()
    assert aid not in result["rooms"]
    assert aid not in coordinator._previous_modes


@pytest.mark.asyncio
async def test_shared_device_shutdown_waits_for_every_waiting_rooms_command(hass, mock_config_entry):
    """B2-01: a command of the second room in flight finishes before the shutdown."""
    import asyncio

    store = FakeStore({"bed": _room("bed", "climate.shared_ac"), "office": _room("office", "climate.shared_ac")})
    _states(hass, {"climate.shared_ac": "heat"})
    coordinator = _coord(hass, mock_config_entry, store)
    office_lock = coordinator._room_command_locks.setdefault("office", asyncio.Lock())
    with areas_missing("bed", "office"), patch(TURN_OFF, new=AsyncMock()) as turn_off:
        await office_lock.acquire()
        task = asyncio.ensure_future(coordinator._async_process_pending_shutdowns())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        turn_off.assert_not_awaited()
        office_lock.release()
        await task
    assert _sent(turn_off) == ["climate.shared_ac"]


@pytest.mark.asyncio
async def test_resume_while_the_shutdown_waits_for_the_lock_sends_nothing(hass, mock_config_entry):
    """B2-02: the entry is re-read after the wait; a resumed room's device is left alone."""
    import asyncio

    store = FakeStore({"bed": _room("bed", "climate.bed_ac")})
    _states(hass, {"climate.bed_ac": "heat"})
    coordinator = _coord(hass, mock_config_entry, store)
    lock = coordinator._room_command_locks.setdefault("bed", asyncio.Lock())
    with areas_missing("bed"), patch(TURN_OFF, new=AsyncMock()) as turn_off:
        await lock.acquire()
        task = asyncio.ensure_future(coordinator._async_process_pending_shutdowns())
        await asyncio.sleep(0)
        coordinator._pending_shutdowns.forget_area("bed")  # what a resume does
        lock.release()
        await task
    turn_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_pause_keeps_the_dehumidifiers_learned_drying_rate(hass):
    """B2-03: a resting room keeps what was learned; only a deletion forgets it."""
    from custom_components.roommind.managers.dehumidifier_manager import DehumidifierManager

    manager = DehumidifierManager(hass)
    device = {"entity_id": "switch.dryer", "mode": "auto"}
    manager.learned["switch.dryer"] = MagicMock()
    await manager.release(device, None, True, keep_learned=True)
    assert "switch.dryer" in manager.learned
    await manager.release(device, None, True)
    assert "switch.dryer" not in manager.learned


@pytest.mark.asyncio
async def test_unload_releases_a_resting_rooms_valve_without_its_target(hass):
    """B2-04: unload right after an area removal must not hand the old target back."""
    from custom_components.roommind import _async_release_all_valves
    from custom_components.roommind.const import DOMAIN

    def _valve_room(area_id, eid):
        return {
            "area_id": area_id,
            "devices": [
                {
                    "entity_id": eid,
                    "type": "trv",
                    "role": "auto",
                    "valve_opening_entity": f"number.{area_id}_open",
                    "valve_closing_entity": f"number.{area_id}_close",
                }
            ],
        }

    store = FakeStore(
        {"bed": _valve_room("bed", "climate.bed_trv"), "living": _valve_room("living", "climate.living_trv")}
    )
    hass.data = {DOMAIN: {"store": store}}
    with (
        areas_missing("bed"),
        patch(
            "custom_components.roommind.__init__.rooms_with_area",
            side_effect=lambda h, rooms: {a: r for a, r in rooms.items() if a != "bed"},
        ),
        patch("custom_components.roommind.control.direct_valve.async_release_valve", new=AsyncMock()) as release,
    ):
        await _async_release_all_valves(hass)
    hand_back = {c.args[1]: c.kwargs["hand_back"] for c in release.await_args_list}
    assert hand_back == {"climate.bed_trv": False, "climate.living_trv": True}


@pytest.mark.asyncio
async def test_area_back_during_setup_brings_the_entities_back(hass, mock_config_entry):
    """C1/B-02: an area created while setup ran (no event seen) gets its room's entities on the next cycle."""
    store = FakeStore({"bed": _room("bed", "climate.bed_ac", **{REST_SWITCHED_OFF: True})})
    coordinator = _coord(hass, mock_config_entry, store)
    coordinator.async_add_entities = MagicMock()
    with patch.object(coordinator, "async_room_added", new=AsyncMock()) as added:
        await coordinator._async_process_pending_shutdowns()
    added.assert_awaited_once()
    assert store.rooms["bed"][REST_SWITCHED_OFF] is False
