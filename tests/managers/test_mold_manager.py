"""Tests for mold_manager.py — mold risk detection and prevention manager."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.roommind.managers.mold_manager import MoldManager


@pytest.fixture
def mm(hass):
    return MoldManager(hass)


def _settings_prevention_notify(**overrides):
    """Return settings with mold prevention + notification enabled."""
    s = {
        "mold_detection_enabled": True,
        "mold_prevention_enabled": True,
        "mold_prevention_notify_enabled": True,
        "mold_notifications_enabled": True,
        "mold_prevention_intensity": "medium",
        "mold_prevention_notify_targets": ["notify.mobile"],
        "mold_humidity_threshold": 70.0,
        "mold_sustained_minutes": 0,
        "mold_prevention_sustained_minutes": 0,
    }
    s.update(overrides)
    return s


@pytest.mark.asyncio
async def test_warning_must_persist_but_critical_risk_responds_faster():
    from unittest.mock import MagicMock

    manager = MoldManager(MagicMock())
    settings = {
        "mold_prevention_enabled": True,
        "mold_prevention_sustained_minutes": 60,
        "mold_notifications_enabled": False,
    }
    with (
        patch("custom_components.roommind.managers.mold_manager.calculate_mold_risk") as risk,
        patch("custom_components.roommind.managers.mold_manager.time") as clock,
    ):
        risk.return_value = ("warning", 72.0)
        clock.time.return_value = 1000
        first = await manager.evaluate("studio", "Studio", 25, 65, 20, settings, can_dry=True)
        assert not first.prevention_active
        clock.time.return_value = 4599
        before = await manager.evaluate("studio", "Studio", 25, 65, 20, settings, can_dry=True)
        assert not before.prevention_active
        clock.time.return_value = 4600
        ready = await manager.evaluate("studio", "Studio", 25, 65, 20, settings, can_dry=True)
        assert ready.prevention_active and ready.prevention_strategy == "dry"

        # Critical risk responds after 10 minutes rather than 60.
        risk.return_value = ("critical", 83.0)
        clock.time.return_value = 2000
        urgent = await manager.evaluate("bagno", "Bagno", 19, 75, 5, settings)
        assert not urgent.prevention_active
        clock.time.return_value = 2600
        urgent = await manager.evaluate("bagno", "Bagno", 19, 75, 5, settings)
        assert urgent.prevention_active and urgent.prevention_strategy == "heat"


@pytest.mark.asyncio
async def test_prevention_uses_hysteresis_and_minimum_run_time():
    from unittest.mock import MagicMock

    manager = MoldManager(MagicMock())
    settings = {
        "mold_prevention_enabled": True,
        "mold_prevention_sustained_minutes": 0,
        "mold_notifications_enabled": False,
    }
    with (
        patch("custom_components.roommind.managers.mold_manager.calculate_mold_risk") as risk,
        patch("custom_components.roommind.managers.mold_manager.time") as clock,
        patch("custom_components.roommind.managers.mold_manager.dismiss_mold_notification"),
    ):
        clock.time.return_value = 1000
        risk.return_value = ("warning", 72.0)
        assert (await manager.evaluate("studio", "Studio", 25, 70, 15, settings, can_dry=True)).prevention_active
        clock.time.return_value = 1300
        risk.return_value = ("ok", 68.0)
        assert (await manager.evaluate("studio", "Studio", 25, 60, 15, settings, can_dry=True)).prevention_active
        risk.return_value = ("ok", 60.0)
        assert (await manager.evaluate("studio", "Studio", 25, 55, 15, settings, can_dry=True)).prevention_active
        clock.time.return_value = 1601
        assert not (await manager.evaluate("studio", "Studio", 25, 55, 15, settings, can_dry=True)).prevention_active
        assert manager._prevention_started == {}


# --- prevention activation notification (lines 143-156) ---


@pytest.mark.asyncio
async def test_prevention_activation_sends_notification(mm):
    """When prevention activates for first time, notification is sent."""
    settings = _settings_prevention_notify()

    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("warning", 75.0),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.mold_prevention_delta",
            return_value=2.0,
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ) as mock_notify,
    ):
        result = await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
            celsius_delta_to_ha_fn=lambda x: x,
            ha_temp_unit_str_fn=lambda: "°C",
        )

    assert result.prevention_active is True
    assert result.prevention_delta == 2.0
    assert mock_notify.call_count >= 1
    # Check that prevention notification was sent (not just detection)
    prevention_call = [c for c in mock_notify.call_args_list if c.kwargs.get("tag_suffix") == "prevention"]
    assert len(prevention_call) == 1


@pytest.mark.asyncio
async def test_prevention_notification_not_sent_without_helper_fns(mm):
    """Prevention notification skipped if celsius_delta_to_ha_fn is None."""
    settings = _settings_prevention_notify()

    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("warning", 75.0),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.mold_prevention_delta",
            return_value=2.0,
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ) as mock_notify,
    ):
        result = await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
            celsius_delta_to_ha_fn=None,
            ha_temp_unit_str_fn=None,
        )

    assert result.prevention_active is True
    # Only detection notification, no prevention notification
    prevention_calls = [c for c in mock_notify.call_args_list if c.kwargs.get("tag_suffix") == "prevention"]
    assert len(prevention_calls) == 0


@pytest.mark.asyncio
async def test_prevention_notification_not_sent_on_second_evaluation(mm):
    """Prevention notification only sent on first activation, not repeated."""
    settings = _settings_prevention_notify()

    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("warning", 75.0),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.mold_prevention_delta",
            return_value=2.0,
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ) as mock_notify,
    ):
        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
            celsius_delta_to_ha_fn=lambda x: x,
            ha_temp_unit_str_fn=lambda: "°C",
        )
        mock_notify.reset_mock()

        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
            celsius_delta_to_ha_fn=lambda x: x,
            ha_temp_unit_str_fn=lambda: "°C",
        )

    prevention_calls = [c for c in mock_notify.call_args_list if c.kwargs.get("tag_suffix") == "prevention"]
    assert len(prevention_calls) == 0


# --- remove_room (lines 182-185) ---


@pytest.mark.asyncio
async def test_remove_room_clears_state(mm):
    """remove_room cleans up all internal state for a room."""
    settings = _settings_prevention_notify()

    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("warning", 75.0),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.mold_prevention_delta",
            return_value=2.0,
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ),
    ):
        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
            celsius_delta_to_ha_fn=lambda x: x,
            ha_temp_unit_str_fn=lambda: "°C",
        )

    assert "living" in mm._risk_since
    assert mm._prevention_active.get("living") is True

    mm.remove_room("living")

    assert "living" not in mm._risk_since
    assert "living" not in mm._prevention_active


def test_remove_room_no_op_for_unknown(mm):
    """remove_room on unknown area_id does not raise."""
    mm.remove_room("nonexistent")


@pytest.mark.asyncio
async def test_prevention_prefers_dehumidification_above_configured_temperature(mm):
    """A dry-capable heat pump is used only above its configured safe temperature."""
    with patch(
        "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
        return_value=("warning", 75.0),
    ):
        result = await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=22.0,
            current_humidity=75.0,
            outdoor_temp=5.0,
            settings=_settings_prevention_notify(mold_prevention_dry_min_temperature=21.5),
            can_dry=True,
        )

    assert result.prevention_strategy == "dry"
    assert result.prevention_delta == 0.0


@pytest.mark.asyncio
async def test_prevention_does_not_heat_warm_room_when_dry_is_disabled(mm):
    """Disabling DRY must not trigger heat in a room already at 25°C."""
    with patch(
        "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
        return_value=("warning", 75.0),
    ):
        result = await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=25.0,
            current_humidity=75.0,
            outdoor_temp=5.0,
            settings=_settings_prevention_notify(mold_prevention_dehumidification_enabled=False),
            can_dry=True,
            can_cool=True,
        )

    assert result.prevention_strategy is None
    assert result.prevention_active is False


# --- detection notification (tag_suffix="risk") ---


@pytest.mark.asyncio
async def test_detection_notification_sent_on_risk(mm):
    """When mold risk is detected, a notification with tag_suffix='risk' is sent."""
    settings = {
        "mold_detection_enabled": True,
        "mold_prevention_enabled": False,
        "mold_notifications_enabled": True,
        "mold_humidity_threshold": 70.0,
        "mold_sustained_minutes": 0,
    }

    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("warning", 75.0),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ) as mock_notify,
    ):
        result = await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
        )

    assert result.risk_level == "warning"
    assert mock_notify.call_count == 1
    assert mock_notify.call_args.kwargs["tag_suffix"] == "risk"


# --- hysteresis deactivation ---


@pytest.mark.asyncio
async def test_hysteresis_deactivation(mm):
    """Prevention deactivates when surface_rh drops below threshold minus hysteresis."""
    settings = _settings_prevention_notify()

    # First call: activate prevention
    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("warning", 75.0),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.mold_prevention_delta",
            return_value=2.0,
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ),
    ):
        r1 = await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
            celsius_delta_to_ha_fn=lambda x: x,
            ha_temp_unit_str_fn=lambda: "°C",
        )
    assert r1.prevention_active is True
    assert mm._prevention_active["living"] is True

    # Second call: surface_rh drops well below MOLD_SURFACE_RH_WARNING - MOLD_HYSTERESIS (70 - 5 = 65)
    mm._prevention_started["living"] -= 601  # Minimum runtime has elapsed.
    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("ok", 60.0),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.dismiss_mold_notification",
        ) as mock_dismiss,
    ):
        r2 = await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=21.0,
            current_humidity=50.0,
            outdoor_temp=5.0,
            settings=settings,
            celsius_delta_to_ha_fn=lambda x: x,
            ha_temp_unit_str_fn=lambda: "°C",
        )

    assert r2.prevention_active is False
    assert mm._prevention_active.get("living", False) is False
    # Both risk and prevention notifications dismissed
    assert mock_dismiss.call_count == 2
    dismiss_suffixes = [c[0][2] for c in mock_dismiss.call_args_list]
    assert "risk" in dismiss_suffixes
    assert "prevention" in dismiss_suffixes


# --- sustained_minutes delays notification ---


@pytest.mark.asyncio
async def test_sustained_minutes_delays_notification(mm):
    """With sustained_minutes > 0, notification is not sent until risk persists long enough."""
    settings = {
        "mold_detection_enabled": True,
        "mold_prevention_enabled": False,
        "mold_notifications_enabled": True,
        "mold_humidity_threshold": 70.0,
        "mold_sustained_minutes": 5,
    }

    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("warning", 75.0),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ) as mock_notify,
        patch("custom_components.roommind.managers.mold_manager.time") as mock_time,
    ):
        # First call at t=1000: risk just started
        mock_time.time.return_value = 1000.0
        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
        )
        assert mock_notify.call_count == 0, "Should not notify yet (sustained_minutes not met)"

        # Second call at t=1100 (100s later, still < 5 min = 300s)
        mock_time.time.return_value = 1100.0
        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
        )
        assert mock_notify.call_count == 0, "Still not sustained long enough"

        # Third call at t=1301 (301s > 300s)
        mock_time.time.return_value = 1301.0
        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
        )
        assert mock_notify.call_count == 1, "Now notification should be sent"


# --- dismiss notification on risk clear ---


@pytest.mark.asyncio
async def test_dismiss_notification_on_risk_clear(mm):
    """When risk clears (surface_rh < threshold - hysteresis), dismiss is called."""
    settings = _settings_prevention_notify()

    # Activate prevention first
    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("warning", 75.0),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.mold_prevention_delta",
            return_value=2.0,
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ),
    ):
        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
            celsius_delta_to_ha_fn=lambda x: x,
            ha_temp_unit_str_fn=lambda: "°C",
        )

    # Now clear risk
    mm._prevention_started["living"] -= 601  # Past the minimum run time.
    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("ok", 60.0),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.dismiss_mold_notification",
        ) as mock_dismiss,
    ):
        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=21.0,
            current_humidity=50.0,
            outdoor_temp=5.0,
            settings=settings,
        )

    # dismiss called for both "risk" and "prevention"
    assert mock_dismiss.call_count == 2


# --- detection disabled skips ---


@pytest.mark.asyncio
async def test_detection_disabled_skips(mm):
    """mold_detection_enabled=False and mold_prevention_enabled=False returns early with no risk."""
    settings = {
        "mold_detection_enabled": False,
        "mold_prevention_enabled": False,
    }

    result = await mm.evaluate(
        area_id="living",
        area_name="Living Room",
        current_temp=18.0,
        current_humidity=90.0,
        outdoor_temp=-5.0,
        settings=settings,
    )

    assert result.risk_level == "ok"
    assert result.surface_rh is None
    assert result.prevention_active is False


# --- no humidity returns early ---


@pytest.mark.asyncio
async def test_no_humidity_returns_early(mm):
    """current_humidity=None returns early with default MoldResult."""
    settings = {
        "mold_detection_enabled": True,
        "mold_prevention_enabled": True,
    }

    result = await mm.evaluate(
        area_id="living",
        area_name="Living Room",
        current_temp=18.0,
        current_humidity=None,
        outdoor_temp=-5.0,
        settings=settings,
    )

    assert result.risk_level == "ok"
    assert result.surface_rh is None
    assert result.prevention_active is False


@pytest.mark.asyncio
async def test_early_surface_watch_requires_two_hours_and_safe_dry(mm):
    settings = {"mold_prevention_enabled": True, "mold_prevention_sustained_minutes": 60}
    with (
        patch("custom_components.roommind.managers.mold_manager.calculate_mold_risk", return_value=("ok", 66.0)),
        patch("custom_components.roommind.managers.mold_manager.time") as clock,
    ):
        clock.time.return_value = 1000
        assert not (await mm.evaluate("bed", "Bed", 23, 62, 20, settings, can_dry=True)).prevention_active
        clock.time.return_value = 8199
        assert not (await mm.evaluate("bed", "Bed", 23, 62, 20, settings, can_dry=True)).prevention_active
        clock.time.return_value = 8200
        ready = await mm.evaluate("bed", "Bed", 23, 62, 20, settings, can_dry=True)
        assert ready.prevention_active and ready.prevention_strategy == "dry"


@pytest.mark.asyncio
async def test_dry_stops_at_21_and_cannot_restart_during_cooldown(mm):
    settings = {"mold_prevention_enabled": True, "mold_prevention_sustained_minutes": 0}
    with (
        patch("custom_components.roommind.managers.mold_manager.calculate_mold_risk", return_value=("warning", 73.0)),
        patch("custom_components.roommind.managers.mold_manager.time") as clock,
        patch("custom_components.roommind.managers.mold_manager.dismiss_mold_notification"),
    ):
        clock.time.return_value = 1000
        start = await mm.evaluate("bed", "Bed", 22, 65, 10, settings, can_dry=True)
        assert start.prevention_active and start.prevention_strategy == "dry"
        clock.time.return_value = 1300
        continue_dry = await mm.evaluate("bed", "Bed", 21.5, 65, 10, settings, can_dry=True)
        assert continue_dry.prevention_active and continue_dry.prevention_strategy == "dry"
        clock.time.return_value = 1600
        stop = await mm.evaluate("bed", "Bed", 21, 65, 10, settings, can_dry=True)
        assert not stop.prevention_active and stop.prevention_strategy is None
        clock.time.return_value = 1700
        assert mm.dry_retry_blocked("bed")
        assert not (await mm.evaluate("bed", "Bed", 23, 65, 10, settings, can_dry=True)).prevention_active
        clock.time.return_value = 5200
        again = await mm.evaluate("bed", "Bed", 23, 65, 10, settings, can_dry=True)
        assert again.prevention_active and again.prevention_strategy == "dry"


@pytest.mark.asyncio
async def test_no_heating_or_cooling_in_20_to_22_degree_gap(mm):
    settings = {"mold_prevention_enabled": True, "mold_prevention_sustained_minutes": 0}
    with patch("custom_components.roommind.managers.mold_manager.calculate_mold_risk", return_value=("critical", 85.0)):
        for temp in (20.0, 21.0, 21.9):
            result = await mm.evaluate("bed", "Bed", temp, 78, 5, settings, can_dry=True, can_cool=True)
            assert result.prevention_strategy is None
            assert not result.prevention_active
        # Below 20°C, only the heat plan is allowed.
        cold = await mm.evaluate("cold", "Cold", 19.0, 78, 5, settings, can_dry=True)
        assert cold.prevention_active and cold.prevention_strategy == "heat"


@pytest.mark.asyncio
async def test_dry_cycle_maximum_runtime_and_retry_pause(mm):
    settings = {"mold_prevention_enabled": True, "mold_prevention_sustained_minutes": 0}
    with (
        patch("custom_components.roommind.managers.mold_manager.calculate_mold_risk", return_value=("warning", 75.0)),
        patch("custom_components.roommind.managers.mold_manager.time") as clock,
        patch("custom_components.roommind.managers.mold_manager.dismiss_mold_notification"),
    ):
        clock.time.return_value = 1000
        assert (await mm.evaluate("bed", "Bed", 24, 67, 5, settings, can_dry=True)).prevention_active
        clock.time.return_value = 2800
        assert not (await mm.evaluate("bed", "Bed", 23, 67, 5, settings, can_dry=True)).prevention_active
        clock.time.return_value = 2801
        assert mm.dry_retry_blocked("bed")


_REHEAT = {
    "mold_prevention_enabled": True,
    "mold_prevention_sustained_minutes": 0,
    "mold_prevention_reheat_enabled": True,
}


@pytest.mark.asyncio
async def test_reheat_alternates_dry_and_heat_pump_without_cooldown(mm):
    with (
        patch("custom_components.roommind.managers.mold_manager.calculate_mold_risk", return_value=("warning", 73.0)),
        patch("custom_components.roommind.managers.mold_manager.time") as clock,
        patch("custom_components.roommind.managers.mold_manager.dismiss_mold_notification"),
    ):
        caps = {"can_dry": True, "can_heat_pump": True}
        clock.time.return_value = 1000
        assert (await mm.evaluate("bed", "Bed", 23, 65, 15, _REHEAT, **caps)).prevention_strategy == "dry"
        clock.time.return_value = 1600
        cold = await mm.evaluate("bed", "Bed", 21, 65, 15, _REHEAT, **caps)
        assert cold.prevention_active and cold.prevention_strategy == "reheat"
        assert not mm.dry_retry_blocked("bed")
        clock.time.return_value = 1900
        assert (await mm.evaluate("bed", "Bed", 21.6, 65, 15, _REHEAT, **caps)).prevention_strategy == "reheat"
        clock.time.return_value = 2200
        assert (await mm.evaluate("bed", "Bed", 22, 65, 15, _REHEAT, **caps)).prevention_strategy == "dry"
        # 30-minute single-DRY cap does not apply to an alternating session...
        clock.time.return_value = 1000 + 179 * 60
        assert (await mm.evaluate("bed", "Bed", 22.5, 65, 15, _REHEAT, **caps)).prevention_active
        # ...but the 3-hour session cap does.
        clock.time.return_value = 1000 + 180 * 60
        assert not (await mm.evaluate("bed", "Bed", 22.5, 65, 15, _REHEAT, **caps)).prevention_active
        assert mm.dry_retry_blocked("bed")


@pytest.mark.asyncio
async def test_reheat_closes_20_to_22_gap_only_when_enabled_and_heat_pump_present(mm):
    with patch("custom_components.roommind.managers.mold_manager.calculate_mold_risk", return_value=("critical", 85.0)):
        gap = await mm.evaluate("a", "A", 21.0, 78, 5, _REHEAT, can_dry=True, can_heat_pump=True)
        assert gap.prevention_active and gap.prevention_strategy == "reheat"
        no_hp = await mm.evaluate("b", "B", 21.0, 78, 5, _REHEAT, can_dry=True)
        assert no_hp.prevention_strategy is None
        off = {**_REHEAT, "mold_prevention_reheat_enabled": False}
        disabled = await mm.evaluate("c", "C", 21.0, 78, 5, off, can_dry=True, can_heat_pump=True)
        assert disabled.prevention_strategy is None
        # Cold rooms keep the regular heating plan.
        cold = await mm.evaluate("d", "D", 19.0, 78, 5, _REHEAT, can_dry=True, can_heat_pump=True)
        assert cold.prevention_strategy == "heat"


_EARLY = {"mold_prevention_enabled": True, "mold_prevention_sustained_minutes": 60}


def _humid_rows(start: float, end: float, step: float = 180.0, **overrides):
    """History rows like the bedroom tonight: 23.8 °C, 64.5 %, 20.5 °C outside (surface ≈ 67 %)."""
    row = {"room_temp": "23.8", "current_humidity": "64.5", "outdoor_temp": "20.5", **overrides}
    rows, ts = [], start
    while ts <= end:
        rows.append({"timestamp": str(ts), **row})
        ts += step
    return rows


@pytest.mark.asyncio
async def test_bootstrap_restores_early_timer_after_restart(mm):
    now = 100_000.0
    mm.bootstrap("bed", _humid_rows(now - 150 * 60, now - 60), _EARLY, now=now)
    with patch("custom_components.roommind.managers.mold_manager.time") as clock:
        clock.time.return_value = now
        result = await mm.evaluate("bed", "Bed", 23.8, 64.5, 20.5, _EARLY, can_dry=True)
    assert result.prevention_active and result.prevention_strategy == "dry"


@pytest.mark.asyncio
async def test_bootstrap_ignores_interrupted_or_stale_history(mm):
    now = 100_000.0
    humid_then_dry = (
        _humid_rows(now - 150 * 60, now - 61 * 60)
        + _humid_rows(now - 60 * 60, now - 60 * 60, current_humidity="50")
        + _humid_rows(now - 57 * 60, now - 60)
    )
    mm.bootstrap("dry_spell", humid_then_dry, _EARLY, now=now)
    # A 20-minute hole (e.g. HA was down) means the condition was not observed.
    holed = _humid_rows(now - 150 * 60, now - 81 * 60) + _humid_rows(now - 60 * 60, now - 60)
    mm.bootstrap("hole", holed, _EARLY, now=now)
    # History that stops 20 minutes before startup is not trusted at all.
    mm.bootstrap("stale", _humid_rows(now - 150 * 60, now - 20 * 60), _EARLY, now=now)
    with patch("custom_components.roommind.managers.mold_manager.time") as clock:
        clock.time.return_value = now
        for area in ("dry_spell", "hole", "stale"):
            result = await mm.evaluate(area, area, 23.8, 64.5, 20.5, _EARLY, can_dry=True)
            assert not result.prevention_active, area


@pytest.mark.asyncio
async def test_night_quiet_for_early_zone_but_not_for_warning(mm):
    now = 100_000.0
    mm.bootstrap("bed", _humid_rows(now - 150 * 60, now - 60), _EARLY, now=now)
    with patch("custom_components.roommind.managers.mold_manager.time") as clock:
        clock.time.return_value = now
        night = await mm.evaluate("bed", "Bed", 23.8, 64.5, 20.5, _EARLY, can_dry=True, night_phase="night")
        assert not night.prevention_active
        # Timers keep running through the night: DRY starts as soon as it ends.
        morning = await mm.evaluate("bed", "Bed", 23.8, 64.5, 20.5, _EARLY, can_dry=True)
        assert morning.prevention_active
    with (
        patch("custom_components.roommind.managers.mold_manager.calculate_mold_risk", return_value=("critical", 85.0)),
        patch("custom_components.roommind.managers.mold_manager.time") as clock,
    ):
        clock.time.return_value = 1000
        await mm.evaluate("wet", "Wet", 24, 75, 5, {**_EARLY, "mold_prevention_sustained_minutes": 0}, can_dry=True)
        clock.time.return_value = 1700
        urgent = await mm.evaluate(
            "wet",
            "Wet",
            24,
            75,
            5,
            {**_EARLY, "mold_prevention_sustained_minutes": 0},
            can_dry=True,
            night_phase="night",
        )
        assert urgent.prevention_active


@pytest.mark.asyncio
async def test_pre_night_dries_early_zone_after_30_minutes(mm):
    now = 100_000.0
    mm.bootstrap("bed", _humid_rows(now - 31 * 60, now - 60), _EARLY, now=now)
    with patch("custom_components.roommind.managers.mold_manager.time") as clock:
        clock.time.return_value = now
        day = await mm.evaluate("bed", "Bed", 23.8, 64.5, 20.5, _EARLY, can_dry=True)
        assert not day.prevention_active
        pre = await mm.evaluate("bed", "Bed", 23.8, 64.5, 20.5, _EARLY, can_dry=True, night_phase="pre_night")
        assert pre.prevention_active and pre.prevention_strategy == "dry"


@pytest.mark.asyncio
async def test_open_window_pauses_without_burning_runtime_or_retry_pause(mm):
    now = 100_000.0
    mm.bootstrap("bed", _humid_rows(now - 150 * 60, now - 60), _EARLY, now=now)
    with (
        patch("custom_components.roommind.managers.mold_manager.time") as clock,
        patch("custom_components.roommind.managers.mold_manager.dismiss_mold_notification"),
    ):
        clock.time.return_value = now
        assert (await mm.evaluate("bed", "Bed", 23.8, 64.5, 20.5, _EARLY, can_dry=True)).prevention_active
        clock.time.return_value = now + 25 * 60
        paused = await mm.evaluate("bed", "Bed", 23.8, 64.5, 20.5, _EARLY, can_dry=True, window_open=True)
        assert not paused.prevention_active
        assert not mm.dry_retry_blocked("bed")
        # Closed again 20 min later: a fresh session starts immediately and
        # is not cut by the 30-minute cap of the interrupted one.
        clock.time.return_value = now + 45 * 60
        assert (await mm.evaluate("bed", "Bed", 23.8, 64.5, 20.5, _EARLY, can_dry=True)).prevention_active
        clock.time.return_value = now + 70 * 60
        assert (await mm.evaluate("bed", "Bed", 23.8, 64.5, 20.5, _EARLY, can_dry=True)).prevention_active


@pytest.mark.asyncio
async def test_restarted_sessions_and_restart_do_not_repeat_notifications(mm):
    now = 100_000.0
    settings = {**_settings_prevention_notify(), "mold_prevention_sustained_minutes": 60}
    mm.bootstrap("bed", _humid_rows(now - 150 * 60, now - 60, current_humidity="72"), settings, now=now)
    send = AsyncMock()
    with (
        patch("custom_components.roommind.managers.mold_manager.async_send_mold_notification", send),
        patch("custom_components.roommind.managers.mold_manager.dismiss_mold_notification"),
        patch("custom_components.roommind.managers.mold_manager.time") as clock,
    ):
        kwargs = {"can_dry": True, "celsius_delta_to_ha_fn": lambda d: d, "ha_temp_unit_str_fn": lambda: "°C"}
        clock.time.return_value = now
        await mm.evaluate("bed", "Bed", 23.8, 72, 20.5, settings, **kwargs)
        titles = [c.kwargs["title"] for c in send.call_args_list]
        # Risk warning was already sent before the restart; prevention announces once.
        assert titles == ["RoomMind: Mold Prevention"]
        clock.time.return_value = now + 60
        await mm.evaluate("bed", "Bed", 23.8, 72, 20.5, settings, window_open=True, **kwargs)
        clock.time.return_value = now + 120
        await mm.evaluate("bed", "Bed", 23.8, 72, 20.5, settings, **kwargs)
        assert len(send.call_args_list) == 1


@pytest.mark.asyncio
async def test_high_weekly_exposure_skips_grace_and_quiet_night(mm):
    now = 100_000.0
    mm.bootstrap("bed", _humid_rows(now - 31 * 60, now - 60), _EARLY, now=now)
    with patch("custom_components.roommind.managers.mold_manager.time") as clock:
        clock.time.return_value = now
        low = await mm.evaluate("bed", "Bed", 23.8, 64.5, 20.5, _EARLY, can_dry=True, exposure_hours=5.0)
        assert not low.prevention_active
        high = await mm.evaluate(
            "bed", "Bed", 23.8, 64.5, 20.5, _EARLY, can_dry=True, night_phase="night", exposure_hours=30.0
        )
        assert high.prevention_active and high.prevention_strategy == "dry"


@pytest.mark.asyncio
async def test_room_wall_factor_reaches_the_risk_level(mm):
    settings = {"mold_detection_enabled": True, "mold_notifications_enabled": False}
    plain = await mm.evaluate("a", "A", 23.8, 64.5, 10.0, settings)
    corner = await mm.evaluate("b", "B", 23.8, 64.5, 10.0, settings, f_rsi=0.70)
    assert plain.risk_level == "warning" and corner.risk_level == "critical"
