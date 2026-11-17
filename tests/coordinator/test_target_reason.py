"""What set a room's targets is recorded with the history for the analytics chart."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import (
    TARGET_REASON_AWAY,
    TARGET_REASON_OVERRIDE,
    TARGET_REASON_VACATION,
)
from custom_components.roommind.utils.history_store import HistoryStore

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

OVERRIDE = {"override_heat": 25.0, "override_cool": 25.0, "override_until": None, "override_type": "boost"}
VACATION = {"vacation_temp": 15.0, "vacation_until": time.time() + 86400}


def _both(coordinator, room, settings):
    targets, reason = coordinator._resolve_target_temps_and_reason(room, settings, None, None)
    # the wrapper every other caller uses returns exactly the same targets
    assert coordinator._resolve_target_temps(room, settings, None, None) == targets
    return targets, reason


def test_override_vacation_and_away_are_named(hass, mock_config_entry):
    coordinator = _create_coordinator(hass, mock_config_entry)
    targets, reason = _both(coordinator, {**SAMPLE_ROOM, **OVERRIDE}, {})
    assert (targets.heat, reason) == (25.0, TARGET_REASON_OVERRIDE)
    targets, reason = _both(coordinator, SAMPLE_ROOM, VACATION)
    assert (targets.heat, reason) == (15.0, TARGET_REASON_VACATION)
    with patch.object(coordinator, "_is_presence_away", return_value=True):
        targets, reason = _both(coordinator, SAMPLE_ROOM, {})
        assert reason == TARGET_REASON_AWAY
        targets, reason = _both(coordinator, SAMPLE_ROOM, {"presence_away_action": "off"})
        assert (targets.heat, targets.cool, reason) == (None, None, TARGET_REASON_AWAY)


def test_profile_schedule_and_comfort_have_no_reason(hass, mock_config_entry):
    coordinator = _create_coordinator(hass, mock_config_entry)
    hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="off"))
    assert _both(coordinator, {**SAMPLE_ROOM, "active_profile": "guests"}, {})[1] == ""
    assert _both(coordinator, SAMPLE_ROOM, {})[1] == ""


@pytest.mark.asyncio
async def test_cycle_records_the_reason_and_a_manual_pin_clears_it(hass, mock_config_entry):
    store = _make_store_mock({"living_room_abc12345": {**SAMPLE_ROOM, **OVERRIDE}})
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="off"))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    data = await coordinator._async_update_data()
    assert data["rooms"]["living_room_abc12345"]["target_reason"] == TARGET_REASON_OVERRIDE

    pinned = {**SAMPLE_ROOM, **OVERRIDE, "room_hvac_mode": "heat", "logical_heat_target": 20.0}
    store.get_room.return_value = pinned
    store.get_rooms.return_value = {"living_room_abc12345": pinned}
    data = await coordinator._async_update_data()
    assert data["rooms"]["living_room_abc12345"]["target_reason"] == ""


def test_history_keeps_the_reason_through_record_and_compaction(tmp_path):
    hs = HistoryStore(str(tmp_path))
    t0 = 1_000_000.0
    hs.record("a", {"room_temp": 20.0, "mode": "idle", "target_reason": "vacation"}, timestamp=t0)
    hs.record("a", {"room_temp": 20.0, "mode": "idle", "target_reason": "vacation"}, timestamp=t0 + 60)
    hs.record("a", {"room_temp": 20.0, "mode": "idle"}, timestamp=t0 + 400)
    rows = hs.read_detail("a")
    assert [r["target_reason"] for r in rows] == ["vacation", "vacation", ""]
    compacted = hs._downsample(rows, 300)
    assert [r["target_reason"] for r in compacted] == ["vacation", ""]


def test_csv_points_carry_the_reason():
    from custom_components.roommind.services.analytics_service import _csv_to_points

    points = _csv_to_points([{"timestamp": "1", "target_reason": "away"}, {"timestamp": "2"}])
    assert [p["target_reason"] for p in points] == ["away", ""]
