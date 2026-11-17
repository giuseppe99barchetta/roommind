"""The analytics response carries the one-hour backtest from the recorded model inputs."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from custom_components.roommind.control.thermal_model import RCModel
from custom_components.roommind.services.analytics_service import build_analytics_data
from custom_components.roommind.utils.history_store import MODEL_INPUT_FIELDS, HistoryStore

from .test_analytics_rhythm_wiring import _coordinator, _store

MODEL = RCModel(C=2.0, U=0.1, Q_heat=20.0, Q_cool=25.0)


def _Hass():
    """A Home Assistant stand-in that runs executor jobs inline (the model card reads more of it)."""
    hass = MagicMock()

    async def run(fn, *args):
        return fn(*args)

    hass.async_add_executor_job = run
    hass.states.get.return_value = None
    return hass


def _record(hs: HistoryStore, now: float, rows: int, with_inputs: bool = True) -> None:
    T, t_out, step = 20.0, 5.0, 180.0
    t0 = now - rows * step
    for k in range(rows):
        data = {"room_temp": round(T, 4), "outdoor_temp": t_out, "mode": "heating", "predicted_temp": 99.0}
        if with_inputs and k:
            data.update(model_power=0.3, model_solar=0.0, model_residual=0.0, model_occupancy=0.0)
        hs.record("room_a", data, timestamp=t0 + k * step)
        T = MODEL.predict(T, t_out, 0.3 * MODEL.Q_heat, step / 60.0)


def _with_model(coordinator):
    est = coordinator._model_manager.get_estimator("room_a")
    est.get_model = lambda: MODEL
    return coordinator


@pytest.mark.asyncio
async def test_backtest_figures_and_line_from_recorded_inputs(tmp_path):
    now = time.time()
    hs = HistoryStore(str(tmp_path))
    _record(hs, now, 60)
    data = await build_analytics_data(
        _Hass(), "room_a", "24h", _store(), _with_model(_coordinator(hs)), now - 86400, now
    )
    figures = data["model"]["backtest"]
    assert figures["horizon_minutes"] == 60
    assert figures["active"]["n"] >= 12 and figures["active"]["mae"] < 0.01
    predicted = [p["predicted_temp"] for p in data["detail"]]
    assert 99.0 not in predicted, "the stored forecast end is replaced"
    assert any(v is not None for v in predicted)
    assert not any(key in p for p in data["detail"] + data["history"] for key in MODEL_INPUT_FIELDS)


@pytest.mark.asyncio
async def test_no_figures_without_recorded_inputs(tmp_path):
    now = time.time()
    hs = HistoryStore(str(tmp_path))
    _record(hs, now, 60, with_inputs=False)
    data = await build_analytics_data(
        _Hass(), "room_a", "24h", _store(), _with_model(_coordinator(hs)), now - 86400, now
    )
    assert "backtest" not in data["model"]
    assert all(p["predicted_temp"] is None for p in data["detail"])


@pytest.mark.asyncio
async def test_without_a_model_the_recorded_values_stay(tmp_path):
    now = time.time()
    hs = HistoryStore(str(tmp_path))
    _record(hs, now, 10)
    data = await build_analytics_data(_Hass(), "room_a", "24h", _store(), _coordinator(hs), now - 86400, now)
    assert data["model"] == {}
    assert all(p["predicted_temp"] == 99.0 for p in data["detail"])
