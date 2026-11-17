"""The analytics response carries the day rhythm built from the real history files."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from custom_components.roommind.control.thermal_model import RoomModelManager
from custom_components.roommind.services.analytics_service import build_analytics_data
from custom_components.roommind.utils.history_store import HistoryStore


class _Hass:
    async def async_add_executor_job(self, fn, *args):
        return fn(*args)


def _store():
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_room.return_value = {"climate_mode": "heat_only"}
    return store


def _coordinator(history_store):
    coordinator = MagicMock()
    coordinator.rooms = {}
    coordinator.outdoor_temp = 5.0
    coordinator.outdoor_temp_effective = 5.0
    coordinator.outdoor_humidity = 60
    coordinator._weather_manager._outdoor_forecast = []
    coordinator._window_manager._paused = {}
    coordinator._history_store = history_store
    coordinator._model_manager = RoomModelManager()
    return coordinator


def _record_days(hs: HistoryStore, days: float, now: float) -> None:
    ts = now - days * 86400
    while ts < now:
        hs.record(
            "room_a",
            {
                "room_temp": 20.5,
                "outdoor_temp": 4.0,
                "target_temp": 21.0,
                "heat_target": 21.0,
                "mode": "heating",
                "current_humidity": 55.0,
            },
            timestamp=ts,
        )
        ts += 1800


@pytest.mark.asyncio
async def test_rhythm_has_days_and_humidity_means_from_recorded_rows(tmp_path):
    now = time.time()
    hs = HistoryStore(str(tmp_path))
    _record_days(hs, 1.9, now)
    data = await build_analytics_data(_Hass(), "room_a", "24h", _store(), _coordinator(hs), now - 86400, now)
    rhythm = data["rhythm"]
    assert rhythm is not None
    days = [d for d in rhythm["days"] if any(v is not None for v in d["temp"])]
    assert len(days) >= 2
    humidity = [v for d in days for v in d["humidity"] if v is not None]
    assert humidity and all(abs(v - 55.0) < 0.01 for v in humidity)


@pytest.mark.asyncio
async def test_rhythm_is_none_with_less_than_two_days(tmp_path):
    now = time.time()
    hs = HistoryStore(str(tmp_path))
    _record_days(hs, 0.2, now)
    data = await build_analytics_data(_Hass(), "room_a", "24h", _store(), _coordinator(hs), now - 86400, now)
    assert data["rhythm"] is None


@pytest.mark.asyncio
async def test_rhythm_accepts_a_custom_start_of_zero(tmp_path):
    """start_ts 0 is a real (very old) start, not 'no custom range'."""
    now = time.time()
    hs = HistoryStore(str(tmp_path))
    _record_days(hs, 1.9, now)
    data = await build_analytics_data(_Hass(), "room_a", "24h", _store(), _coordinator(hs), 0.0, now)
    assert "rhythm" in data


@pytest.mark.asyncio
async def test_no_history_store_no_rhythm():
    data = await build_analytics_data(_Hass(), "room_a", "24h", _store(), _coordinator(None), None, None)
    assert data["rhythm"] is None
