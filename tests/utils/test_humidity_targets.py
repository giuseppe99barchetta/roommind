"""Seasonal humidity targets and season detection."""

from datetime import datetime
from types import SimpleNamespace

import pytest

from custom_components.roommind.utils.humidity_targets import current_season, room_humidity_target


def _hass(season=None, latitude=43.7):
    states = {"sensor.season": SimpleNamespace(state=season)} if season else {}
    return SimpleNamespace(states=SimpleNamespace(get=states.get), config=SimpleNamespace(latitude=latitude))


@pytest.mark.parametrize(
    ("room", "season", "expected"),
    [
        ({"humidity_comfort_enabled": False, "humidity_target": 50}, "winter", None),
        ({"humidity_comfort_enabled": True, "humidity_target": 55}, "winter", 55),
        ({"humidity_comfort_enabled": True, "humidity_target": 55, "humidity_season_targets": {}}, "winter", 55),
        (
            {"humidity_comfort_enabled": True, "humidity_target": 55, "humidity_season_targets": {"winter": 48}},
            "winter",
            48,
        ),
        (
            {"humidity_comfort_enabled": True, "humidity_target": 55, "humidity_season_targets": {"winter": 48}},
            "summer",
            55,
        ),
        (
            {"humidity_comfort_enabled": True, "humidity_target": 55, "humidity_season_targets": {"winter": None}},
            "winter",
            55,
        ),
        (
            {
                "humidity_comfort_enabled": True,
                "humidity_target": 55,
                "humidity_season_targets": {"winter": 48},
                "active_profile": "away",
            },
            "winter",
            60,
        ),
        (
            {"humidity_comfort_enabled": True, "humidity_target": 55, "humidity_season_targets": {"winter": 48}},
            None,
            55,
        ),
    ],
)
def test_room_humidity_target(room, season, expected):
    assert room_humidity_target(room, season) == expected


def test_season_sensor_wins():
    assert current_season(_hass("autumn"), datetime(2026, 1, 15)) == "autumn"


@pytest.mark.parametrize(
    ("month", "latitude", "expected"),
    [(1, 43.7, "winter"), (4, 43.7, "spring"), (7, 43.7, "summer"), (11, 43.7, "autumn"), (1, -33.9, "summer")],
)
def test_meteorological_fallback(month, latitude, expected):
    assert current_season(_hass(latitude=latitude), datetime(2026, month, 15)) == expected


def test_unknown_season_sensor_falls_back():
    assert current_season(_hass("unknown"), datetime(2026, 7, 1)) == "summer"
