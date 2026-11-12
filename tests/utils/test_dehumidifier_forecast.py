"""Drying-rate forecast helpers."""

import math

from custom_components.roommind.utils.dehumidifier_forecast import (
    RH_FLOOR,
    heat_gain_c,
    minutes_to_target,
    observed_k,
)


def test_minutes_to_target_round_trips_with_observed_rate():
    k = observed_k(70.0, 60.0, 1.0)
    assert k is not None
    assert minutes_to_target(70.0, 60.0, k) == 60


def test_minutes_to_target_edges():
    assert minutes_to_target(50.0, 55.0, 0.3) == 0.0
    assert minutes_to_target(70.0, RH_FLOOR, 0.3) is None  # floor is never reached
    assert minutes_to_target(70.0, 55.0, 0.001) is None  # slower than 12 h
    assert minutes_to_target(70.0, 55.0, 0.0) is None


def test_observed_k_rejects_noise():
    assert observed_k(70.0, 72.0, 1.0) is None  # humidity rose
    assert observed_k(31.0, 30.5, 1.0) is None  # no room above the floor
    assert observed_k(90.0, 31.0, 0.01) is None  # implausibly fast


def test_heat_gain_saturates_at_steady_state():
    assert heat_gain_c(200.0, 0.0) == 0.0
    assert math.isclose(heat_gain_c(200.0, 10_000), 2.0)
