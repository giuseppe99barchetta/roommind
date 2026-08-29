"""Tests for room readiness and decision explanations."""

from custom_components.roommind.utils.room_insights import build_decision_reasons, build_room_readiness


def test_readiness_marks_managed_room_as_basic_not_missing():
    readiness = build_room_readiness(
        {"devices": [{"entity_id": "climate.office"}], "schedules": []},
        {"climate_control_active": True},
        outdoor_available=False,
    )

    assert readiness["level"] == "basic"
    assert readiness["items"][0] == {"key": "devices", "status": "ready"}
    assert readiness["items"][1] == {"key": "temperature_sensor", "status": "recommended"}


def test_readiness_marks_full_control_room_ready():
    readiness = build_room_readiness(
        {"devices": [{"entity_id": "climate.office"}], "temperature_sensor": "sensor.office", "schedules": [{}]},
        {"climate_control_active": True},
        outdoor_available=True,
    )

    assert readiness["level"] == "ready"
    assert readiness["ready_count"] == readiness["total_count"]


def test_decision_reasons_prioritise_safety_before_normal_control():
    reasons = build_decision_reasons(
        {"window_open": True, "power_budget_blocked": True, "override_active": True, "override_type": "boost"}
    )

    assert reasons == ["window_open", "power_budget", "override_boost"]


def test_decision_reasons_falls_back_to_room_mode():
    assert build_decision_reasons({"mode": "cooling"}) == ["mode_cooling"]
