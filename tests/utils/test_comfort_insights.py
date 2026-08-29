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


def test_energy_suggestions_are_based_on_available_data() -> None:
    suggestions = energy_suggestions(
        heating_minutes=500,
        cooling_minutes=0,
        target_error_c=2.0,
        has_power_sensor=False,
    )

    assert len(suggestions) == 3
