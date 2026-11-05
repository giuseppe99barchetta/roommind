"""Tests for room comfort scoring and profile helpers."""

from custom_components.roommind.utils.comfort_insights import (
    active_profile,
    calculate_comfort_score,
    energy_suggestions,
)


def test_active_profile_uses_default_profile() -> None:
    profile = active_profile({"active_profile": "sleep"})

    assert profile is not None
    assert profile["heat_target"] == 19.5
    assert profile["fan_mode"] == "low"


def test_comfort_score_combines_temperature_humidity_and_window() -> None:
    result = calculate_comfort_score(
        current_temp=18.0,
        heat_target=21.0,
        cool_target=25.0,
        humidity=75.0,
        humidity_target=55.0,
        window_open=True,
        mold_risk_level="warning",
        anomalies=[{"type": "target_not_reached", "message": "x"}],
    )

    assert result["score"] < 40
    assert result["label"] == "poor"
    assert result["breakdown"] == {
        "temperature": {"penalty": 45, "status": "below_target"},
        "humidity": {"penalty": 25, "status": "above_target"},
        "window": {"penalty": 15, "status": "open"},
        "air_quality": {"penalty": 10, "status": "warning"},
        "anomalies": {"penalty": 5, "status": "active"},
    }


def test_energy_suggestions_are_based_on_available_data() -> None:
    suggestions = energy_suggestions(
        heating_minutes=500,
        cooling_minutes=0,
        target_error_c=2.0,
        has_power_sensor=False,
    )

    assert len(suggestions) == 3


def test_profile_targets_merge_room_overrides_and_keep_numbers_only() -> None:
    from custom_components.roommind.utils.comfort_insights import profile_targets

    targets = profile_targets({"comfort_profiles": {"away": {"heat_target": 16.0, "label": "Fuori"}}})

    assert set(targets) == {"work", "sleep", "guests", "away"}
    assert targets["away"] == {"heat_target": 16.0, "cool_target": 28.0, "humidity_target": 60.0}
    assert targets["work"] == {"heat_target": 21.0, "cool_target": 25.0, "humidity_target": 55.0}


def test_default_profiles_carry_no_display_labels() -> None:
    from custom_components.roommind.utils.comfort_insights import DEFAULT_PROFILES

    assert all("label" not in profile for profile in DEFAULT_PROFILES.values())
