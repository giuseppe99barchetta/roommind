"""Tests for mold delta, hysteresis, surface RH, prevention intensity, notifications."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .conftest import (
    SAMPLE_ROOM,
    _create_coordinator,
    _make_store_mock,
    make_mock_states_get,
)


class TestMoldRiskDetection:
    """Tests for mold risk detection and prevention in the coordinator."""

    @pytest.mark.asyncio
    async def test_mold_detection_disabled_by_default(self, hass, mock_config_entry):
        """When mold detection is not enabled, mold_risk_level should be 'ok'."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(humidity="80.0"),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_risk_level"] == "ok"
        assert room["mold_prevention_active"] is False

    @pytest.mark.asyncio
    async def test_mold_risk_computed_when_detection_enabled(
        self,
        hass,
        mock_config_entry,
    ):
        """When detection is enabled, mold risk should be calculated."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_detection_enabled": True,
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        # 18degC, 75% RH, 0degC outside -> should be critical
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0",
                outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_risk_level"] == "critical"
        assert room["mold_surface_rh"] is not None
        assert room["mold_surface_rh"] > 80.0

    @pytest.mark.asyncio
    async def test_mold_prevention_raises_target_temp(
        self,
        hass,
        mock_config_entry,
    ):
        """When prevention is enabled and risk is high, target temp is raised."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_prevention_enabled": True,
            "mold_prevention_sustained_minutes": 0,
            "mold_prevention_intensity": "medium",
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        # High mold risk conditions
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0",
                outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_prevention_active"] is True
        # Radiator-only room (no DRY): in season the walls are warmed to 21.5 °C.
        assert room["mold_prevention_delta"] == 0.5
        assert room["target_temp"] == 21.5

    @pytest.mark.asyncio
    async def test_mold_prevention_intensity_light(
        self,
        hass,
        mock_config_entry,
    ):
        """Light intensity raises target by 1degC."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_prevention_enabled": True,
            "mold_prevention_sustained_minutes": 0,
            "mold_prevention_intensity": "light",
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0",
                outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_prevention_delta"] == 0.0
        assert room["target_temp"] == 21.0

    @pytest.mark.asyncio
    async def test_mold_no_humidity_sensor_skipped(
        self,
        hass,
        mock_config_entry,
    ):
        """Rooms without humidity data should not trigger mold logic."""
        room_no_humidity = {**SAMPLE_ROOM, "humidity_sensor": ""}
        store = _make_store_mock({"living_room_abc12345": room_no_humidity})
        store.get_settings.return_value = {
            "mold_detection_enabled": True,
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity=None,
                outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_risk_level"] == "ok"
        assert room["mold_surface_rh"] is None

    @pytest.mark.asyncio
    async def test_mold_risk_fields_in_room_state(
        self,
        hass,
        mock_config_entry,
    ):
        """Mold risk fields should always be present in room state."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert "mold_risk_level" in room
        assert "mold_surface_rh" in room
        assert "mold_prevention_active" in room
        assert "mold_prevention_delta" in room

    @pytest.mark.asyncio
    async def test_mold_prevention_intensity_strong(
        self,
        hass,
        mock_config_entry,
    ):
        """Strong intensity raises target by 3degC."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_prevention_enabled": True,
            "mold_prevention_sustained_minutes": 0,
            "mold_prevention_intensity": "strong",
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0",
                outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_prevention_delta"] == 1.0
        assert room["target_temp"] == 22.0

    @pytest.mark.asyncio
    async def test_mold_sustained_timer_no_notification_before_threshold(
        self,
        hass,
        mock_config_entry,
    ):
        """Notification should NOT be sent before sustained_minutes elapsed."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_detection_enabled": True,
            "mold_notifications_enabled": True,
            "mold_sustained_minutes": 30,
            "mold_notification_targets": [
                {"entity_id": "notify.mobile", "person_entity": "", "notify_when": "always"},
            ],
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0",
                outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)

        # First cycle: risk starts, sustained timer begins
        await coordinator._async_update_data()

        # No notification service call should have been made for mold
        # (only climate control calls may have been made)
        mold_calls = [c for c in hass.services.async_call.call_args_list if c[0][0] == "notify"]
        assert len(mold_calls) == 0

    @pytest.mark.asyncio
    async def test_mold_sustained_timer_notification_after_threshold(
        self,
        hass,
        mock_config_entry,
    ):
        """Notification should be sent after sustained_minutes have elapsed."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_detection_enabled": True,
            "mold_notifications_enabled": True,
            "mold_sustained_minutes": 0,  # immediate notification
            "mold_notification_cooldown": 60,
            "mold_notification_targets": [
                {"entity_id": "notify.mobile", "person_entity": "", "notify_when": "always"},
            ],
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0",
                outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        with patch(
            "custom_components.roommind.coordinator._get_area_name",
            return_value="Living Room",
        ):
            await coordinator._async_update_data()

        mold_calls = [c for c in hass.services.async_call.call_args_list if c[0][0] == "notify"]
        assert len(mold_calls) >= 1

    @pytest.mark.asyncio
    async def test_mold_hysteresis_clearing(
        self,
        hass,
        mock_config_entry,
    ):
        """Prevention should deactivate only when surface RH drops below hysteresis threshold."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_prevention_enabled": True,
            "mold_prevention_sustained_minutes": 0,
            "mold_prevention_intensity": "medium",
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)

        # Cycle 1: High risk -> prevention activates
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0",
                outdoor_temp="0.0",
            ),
        )
        data = await coordinator._async_update_data()
        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_prevention_active"] is True

        # Cycle 2: Conditions improve (warm outside) -> risk ok, surface RH well below threshold
        coordinator._mold_manager._prevention_started["living_room_abc12345"] -= 601
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="40.0",
                outdoor_temp="15.0",
            ),
        )
        data = await coordinator._async_update_data()
        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_prevention_active"] is False
        assert room["mold_prevention_delta"] == 0.0

    @pytest.mark.asyncio
    async def test_mold_warning_triggers_prevention(
        self,
        hass,
        mock_config_entry,
    ):
        """WARNING-level surface RH should trigger prevention (not just CRITICAL)."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_prevention_enabled": True,
            "mold_prevention_sustained_minutes": 0,
            "mold_prevention_intensity": "medium",
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        # Conditions that produce WARNING (surface RH 70-80%) but room humidity below threshold
        # 20degC, 60% RH, 5degC outside -> surface ~16degC, surface RH ~76% (WARNING)
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="20.0",
                humidity="60.0",
                outdoor_temp="5.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_risk_level"] == "warning"
        # A radiator-only room at 20 °C is no longer left alone in season.
        assert room["mold_prevention_active"] is True
        assert room["mold_prevention_strategy"] == "heat"
        assert room["target_temp"] == 21.5

    @pytest.mark.asyncio
    async def test_mold_no_outdoor_sensor_fallback(
        self,
        hass,
        mock_config_entry,
    ):
        """Without outdoor temp sensor, conservative fallback should be used."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_detection_enabled": True,
            # No outdoor_temp_sensor
        }
        hass.data = {"roommind": {"store": store}}
        # 70% room humidity -> fallback = 80% surface RH -> critical
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(humidity="70.0"),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_risk_level"] == "critical"
        assert room["mold_surface_rh"] == pytest.approx(80.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_mold_prevention_force_off_override(self, hass, mock_config_entry):
        """Mold prevention overrides force_off to prevent structural damage."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_prevention_enabled": True,
            "mold_prevention_sustained_minutes": 0,
            "mold_prevention_intensity": "medium",
            "outdoor_temp_sensor": "sensor.outdoor_temp",
            "presence_enabled": True,
            "presence_persons": ["person.kevin"],
            "presence_away_action": "off",
        }
        hass.data = {"roommind": {"store": store}}
        # Nobody home + mold risk conditions
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0",
                outdoor_temp="0.0",
                person_states={"person.kevin": "not_home"},
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        # Mold prevention should override force_off
        assert room["mold_prevention_active"] is True
        assert room["force_off"] is False


_HYBRID_ROOM = {
    **SAMPLE_ROOM,
    "acs": ["climate.living_ac"],
    "devices": [
        {"entity_id": "climate.living_room", "type": "trv", "role": "auto", "heating_system_type": ""},
        {"entity_id": "climate.living_ac", "type": "ac", "role": "auto", "heating_system_type": ""},
    ],
}
_AC_STATE = ("off", {"hvac_modes": ["off", "heat", "cool", "dry"], "min_temp": 16, "max_temp": 30})


class TestMoldReheatAndAiring:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("reheat", [True, False])
    async def test_gap_room_reheats_with_heat_pump_only(self, hass, mock_config_entry, reheat):
        store = _make_store_mock(
            {"living_room_abc12345": _HYBRID_ROOM},
            {
                "mold_prevention_enabled": True,
                "mold_prevention_sustained_minutes": 0,
                "mold_prevention_reheat_enabled": reheat,
            },
        )
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="21.0", humidity="75.0", outdoor_temp="10.0", extra={"climate.living_ac": _AC_STATE}
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        heat_calls = [
            c.args[2]["entity_id"]
            for c in hass.services.async_call.call_args_list
            if c.args[:2] == ("climate", "set_hvac_mode") and c.args[2].get("hvac_mode") == "heat"
        ]
        if reheat:
            assert room["mold_prevention_strategy"] == "reheat"
            assert room["target_temp"] == 22.0
            assert "climate.living_ac" in heat_calls
            assert "climate.living_room" not in heat_calls  # radiators / boiler stay off
        else:
            assert room["mold_prevention_strategy"] is None
            assert heat_calls == []

    @pytest.mark.asyncio
    async def test_airing_recommended_when_outdoor_air_is_drier(self, hass, mock_config_entry):
        store = _make_store_mock(
            {"living_room_abc12345": SAMPLE_ROOM}, {"outdoor_humidity_sensor": "sensor.outdoor_humidity"}
        )
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="70.0", outdoor_temp="5.0", extra={"sensor.outdoor_humidity": ("85.0", {})}
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        assert data["rooms"]["living_room_abc12345"]["airing_recommended"] is True
        assert data["airing_rooms"] == ["living_room_abc12345"]
        assert data["outdoor_abs_humidity"] == pytest.approx(5.8, abs=0.2)

    @pytest.mark.asyncio
    async def test_restart_resumes_early_zone_timer_from_history(self, hass, mock_config_entry):
        import time

        room = {**_HYBRID_ROOM, "room_hvac_mode": "off"}
        store = _make_store_mock(
            {"living_room_abc12345": room},
            {"mold_prevention_enabled": True, "mold_prevention_sustained_minutes": 60},
        )
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="23.8", humidity="64.5", outdoor_temp="20.5", extra={"climate.living_ac": _AC_STATE}
            )
        )
        hass.services.async_call = AsyncMock()
        now = time.time()
        history = MagicMock()
        history.read_history.return_value = []
        history.read_detail.return_value = [
            {
                "timestamp": str(now - minutes * 60),
                "room_temp": "23.8",
                "current_humidity": "64.5",
                "outdoor_temp": "20.5",
            }
            for minutes in range(150, 0, -3)
        ]

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._history_store = history
        data = await coordinator._async_update_data()

        # The room has been in the early zone for 2.5 h: DRY starts on the
        # first cycle after a restart instead of waiting two more hours.
        assert data["rooms"]["living_room_abc12345"]["mold_prevention_strategy"] == "dry"
        history.read_detail.assert_any_call("living_room_abc12345", 3 * 3600)
        # Warm humid air on an average wall: well below 80 % surface RH.
        assert data["rooms"]["living_room_abc12345"]["mold_exposure_hours_7d"] == 0.0


class TestHumidityComfortAndCoilDrying:
    def _coordinator(self, hass, mock_config_entry):
        hass.data = {"roommind": {"store": _make_store_mock({})}}
        return _create_coordinator(hass, mock_config_entry)

    @pytest.mark.parametrize(
        ("room_mode", "night", "force_off", "expected"),
        [
            ("off", False, True, True),  # OFF room can still be dried
            (None, False, False, True),
            ("dry", False, True, False),  # manual DRY untouched
            ("fan_only", False, True, False),
            ("off", True, True, False),  # quiet at night
        ],
    )
    def test_comfort_dry_gates(self, hass, mock_config_entry, room_mode, night, force_off, expected):
        coordinator = self._coordinator(hass, mock_config_entry)
        room = {
            "humidity_comfort_enabled": True,
            "humidity_target": 55,
            "room_hvac_mode": room_mode,
            "night_mode_enabled": night,
            "night_start": "00:00",
            "night_end": "23:59",
        }
        result = coordinator._humidity_dry_requested("bed", room, 24.0, 64.0, "idle", False, force_off)
        assert result is expected

    @pytest.mark.parametrize(("humidity", "expected"), [(50.0, True), (64.0, False)])
    def test_coil_drying_fan_only_in_dry_air(self, hass, mock_config_entry, humidity, expected):
        from custom_components.roommind.const import TargetTemps

        coordinator = self._coordinator(hass, mock_config_entry)
        coordinator._previous_modes["bed"] = "cooling"
        room = {"smart_ventilation_enabled": True}
        active = coordinator._smart_ventilation_active(
            "bed", room, "idle", TargetTemps(heat=None, cool=24.0), 24.0, humidity, False, False
        )
        assert active is expected
