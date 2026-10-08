"""Tests for absolute-humidity airing advice."""

from __future__ import annotations

import pytest

from custom_components.roommind.utils.mold_utils import absolute_humidity, airing_recommended


def test_absolute_humidity_reference_values():
    assert absolute_humidity(24.0, 63.0) == pytest.approx(13.8, abs=0.2)
    assert absolute_humidity(5.0, 85.0) == pytest.approx(5.8, abs=0.2)


def test_cold_humid_outdoor_air_is_still_drier():
    assert airing_recommended(24.0, 63.0, 5.0, 90.0, None)


def test_mild_rain_does_not_recommend_airing():
    # 17 °C / 95 % outside holds about as much water as 24 °C / 63 % inside.
    assert not airing_recommended(24.0, 63.0, 17.0, 95.0, None)


def test_dry_room_or_warmer_outdoor_or_missing_data_is_never_advised():
    assert not airing_recommended(22.0, 45.0, 5.0, 50.0, 55.0)
    assert not airing_recommended(24.0, 70.0, 30.0, 20.0, None)
    assert not airing_recommended(24.0, 70.0, None, 50.0, None)
    # A high surface RH alone is enough moisture to act on.
    assert airing_recommended(20.0, 55.0, 5.0, 80.0, 70.0)


def test_hysteresis_band():
    # Gap of ~1.5 g/m³: not enough to start, enough to keep going.
    args = (20.0, 62.0, 16.0, 70.0, None)
    assert not airing_recommended(*args)
    assert airing_recommended(*args, was_recommended=True)
