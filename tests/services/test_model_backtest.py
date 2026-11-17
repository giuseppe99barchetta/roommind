"""One-hour backtest of the room model on the recorded history."""

from __future__ import annotations

import time

import pytest

from custom_components.roommind.control.thermal_model import RCModel
from custom_components.roommind.services.model_backtest import MIN_BACKTEST_WINDOWS, backtest

STEP = 180.0
MODEL = RCModel(C=2.0, U=0.1, Q_heat=20.0, Q_cool=25.0)


def _simulate(n: int, power=0.0, t0: float = 20.0, t_out: float = 5.0) -> list[dict]:
    """Rows the coordinator would write for a room following MODEL exactly.

    ``power`` is a share or a function of the step index (the step ending at row k is k-1).
    """
    share = power if callable(power) else (lambda _k: power)
    points = []
    T = t0
    for k in range(n):
        row = {"ts": 1_000_000.0 + k * STEP, "room_temp": round(T, 4), "outdoor_temp": t_out}
        if k:
            # the row closing a step carries that step's inputs
            row.update(model_power=share(k - 1), model_solar=0.0, model_residual=0.0, model_occupancy=0.0)
        points.append(row)
        pw = share(k)
        Q = pw * (MODEL.Q_heat if pw > 0 else MODEL.Q_cool)
        T = MODEL.predict(T, t_out, Q, STEP / 60.0)
    return points


def test_a_room_that_follows_the_model_has_no_error():
    for power, kind in [(0.0, "idle"), (0.5, "active"), (-0.5, "active")]:
        result = backtest(_simulate(60, power), MODEL)
        figures = result.figures()[kind]
        assert figures["n"] >= MIN_BACKTEST_WINDOWS
        assert abs(figures["mae"]) < 0.01
        assert result.predicted


def test_the_step_uses_the_inputs_of_the_row_that_closes_it():
    """Power changing every step: replaying with the opening row's inputs would be off."""
    result = backtest(_simulate(60, lambda k: 1.0 if k % 2 else 0.1), MODEL)
    assert result.active.n >= MIN_BACKTEST_WINDOWS
    assert result.active.abs_sum / result.active.n < 0.01


def test_a_row_without_inputs_breaks_every_hour_crossing_it():
    points = _simulate(60, 0.0)
    gap = points[30]
    for key in ("model_power", "model_solar", "model_residual", "model_occupancy"):
        gap[key] = None
    result = backtest(points, MODEL)
    crossing = [p["ts"] for p in points if gap["ts"] <= p["ts"] < gap["ts"] + 3600]
    assert crossing and not any(ts in result.predicted for ts in crossing)
    assert result.predicted  # hours that do not cross it still count


def test_a_gap_in_time_breaks_the_chain():
    points = _simulate(40, 0.0)
    for p in points[20:]:
        p["ts"] += 3600
    result = backtest(points, MODEL)
    assert points[25]["ts"] not in result.predicted


def test_rows_from_before_the_columns_are_left_out():
    points = [{k: v for k, v in p.items() if not k.startswith("model_")} for p in _simulate(40)]
    result = backtest(points, MODEL)
    assert result.predicted == {} and result.windows == 0
    assert result.figures()["idle"] == {"n": 0, "mae": None, "bias": None}


def test_ninety_days_of_rows_stay_fast():
    points = _simulate(90 * 24 * 12, 0.3)  # 5-min rows over 90 days
    for i, p in enumerate(points):
        p["ts"] = 1_000_000.0 + i * 300.0
    start = time.perf_counter()
    backtest(points, MODEL)
    assert time.perf_counter() - start < 5.0


@pytest.mark.parametrize("u", [0.0, -1.0])
def test_a_model_without_losses_gives_nothing(u):
    assert backtest(_simulate(20), RCModel(C=2.0, U=u, Q_heat=1.0, Q_cool=1.0)).predicted == {}


def test_an_hour_must_start_close_to_one_hour_before():
    """Irregular rows: a start reading 70 minutes back is not a one-hour forecast."""
    points = _simulate(60, 0.0)
    # remove the rows between 61 and 69 minutes before the last one
    last = points[-1]["ts"]
    kept = [p for p in points if not (last - 69 * 60 < p["ts"] < last - 58 * 60)]
    # one long step left: keep the chain (rows within MAX_STEP_S) but the start is too early
    assert last - max(p["ts"] for p in kept if p["ts"] <= last - 3600) > 3600 + 300
    assert last not in backtest(kept, MODEL).predicted
