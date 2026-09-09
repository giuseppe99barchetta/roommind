"""Snapshot tests for coordinator._async_process_room return dict.

These tests call _async_process_room directly and verify the return dict
to catch regressions during future coordinator decomposition.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import HVACMode

from custom_components.roommind.climate import RoomMindClimate

from .conftest import (
    MANAGED_ROOM,
    SAMPLE_ROOM,
    _create_coordinator,
    _make_store_mock,
    make_mock_states_get,
)


def _setup_coordinator(hass, mock_config_entry, rooms, settings=None):
    """Wire up hass, store, and create coordinator."""
    store = _make_store_mock(rooms)
    if settings:
        store.get_settings.return_value = settings
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    return coordinator, store


# Keys that every normal (non-outdoor) room return dict must contain.
NORMAL_ROOM_KEYS = {
    "area_id",
    "current_temp",
    "current_temp_raw",
    "current_humidity",
    "target_temp",
    "heat_target",
    "cool_target",
    "mode",
    "commanded_mode",
    "heating_power",
    "device_setpoint",
    "window_open",
    "override_active",
    "override_type",
    "override_heat",
    "override_cool",
    "override_until",
    "override_suppressed",
    "active_schedule_index",
    "confidence",
    "mpc_active",
    "presence_away",
    "force_off",
    "mold_risk_level",
    "mold_surface_rh",
    "mold_prevention_active",
    "mold_prevention_delta",
    "mold_prevention_strategy",
    "shading_factor",
    "q_occupancy",
    "n_observations",
    "blind_position",
    "cover_auto_paused",
    "cover_override_until",
    "cover_forced_reason",
    "cover_reason",
    "active_cover_schedule_index",
    "active_heat_sources",
    "heat_source",
    "heat_source_reason",
    "compressor_protection_active",
    "compressor_protection_reason",
    "active_profile",
    "anomalies",
    "comfort_score",
    "humidity_action",
    "night_mode_active",
    "night_setback_progress",
    "power_budget_blocked",
    "preconditioning_active",
    "preconditioning_planned_at",
    "preconditioning_started_at",
    "predicted_temp",
    "smart_ventilation_active",
    "smart_ventilation_until",
    "window_impact_c",
    "window_open_minutes",
    "window_recovery_minutes",
    "window_recovery_progress",
}

OUTDOOR_ROOM_KEYS = {
    "area_id",
    "current_temp",
    "current_temp_raw",
    "current_humidity",
    "target_temp",
    "heat_target",
    "cool_target",
    "mode",
    "heating_power",
    "device_setpoint",
    "window_open",
    "override_active",
    "override_type",
    "override_heat",
    "override_cool",
    "override_until",
    "override_suppressed",
    "active_schedule_index",
    "confidence",
    "mpc_active",
    "presence_away",
    "force_off",
    "mold_risk_level",
    "mold_surface_rh",
    "mold_prevention_active",
    "mold_prevention_delta",
    "shading_factor",
    "n_observations",
    "blind_position",
    "cover_auto_paused",
    "cover_forced_reason",
    "active_cover_schedule_index",
    "q_occupancy",
    "active_heat_sources",
    "compressor_protection_active",
    "compressor_protection_reason",
}


class TestProcessRoomSnapshot:
    """Snapshot tests for _async_process_room return dict."""

    @pytest.mark.asyncio
    async def test_stale_apply_cannot_override_newer_manual_dry_command(self, hass, mock_config_entry):
        """An update computed before fan_only -> dry cannot append an OFF."""
        area_id = "living_room_abc12345"
        room = {
            **SAMPLE_ROOM,
            "area_id": area_id,
            "thermostats": [],
            "acs": ["climate.living_room_ac"],
            "devices": [{"entity_id": "climate.living_room_ac", "type": "ac"}],
            "room_hvac_mode": "fan_only",
        }
        stale_room = {**room, "room_hvac_mode": "off"}
        coordinator, store = _setup_coordinator(
            hass,
            mock_config_entry,
            {area_id: room},
            {"climate_control_active": False},
        )
        store.get_room.return_value = room
        store.async_update_room = AsyncMock(side_effect=lambda _area_id, updates: room.update(updates))
        coordinator.async_request_refresh = AsyncMock()

        physical = MagicMock(
            state="fan_only",
            attributes={"hvac_modes": ["off", "cool", "heat", "dry", "fan_only", "auto"]},
        )
        hass.states.get = MagicMock(return_value=physical)
        dry_started = asyncio.Event()
        finish_dry = asyncio.Event()

        async def apply_service(_domain, service, data, **_kwargs):
            if service == "set_hvac_mode" and data["hvac_mode"] == "dry":
                physical.state = "dry"
                dry_started.set()
                await finish_dry.wait()
            elif service == "set_hvac_mode":
                physical.state = data["hvac_mode"]

        hass.services.async_call = AsyncMock(side_effect=apply_service)

        async def apply_stale_decision(_room, _settings, _forecast, *, command_generation):
            apply_control = command_generation == coordinator._manual_command_generations.get(area_id, 0)
            if apply_control:
                await hass.services.async_call(
                    "climate",
                    "set_hvac_mode",
                    {"entity_id": "climate.living_room_ac", "hvac_mode": "off"},
                    blocking=True,
                )
            return {}

        coordinator._async_process_room_locked = AsyncMock(side_effect=apply_stale_decision)
        entity = RoomMindClimate(coordinator, area_id)

        manual = asyncio.create_task(entity.async_set_hvac_mode(HVACMode.DRY))
        await dry_started.wait()
        stale_apply = asyncio.create_task(
            coordinator._async_process_room(
                stale_room,
                store.get_settings(),
                [],
                command_generation=0,
            )
        )
        finish_dry.set()
        await manual
        await stale_apply

        assert physical.state == "dry"
        hvac_modes = [call.args[2]["hvac_mode"] for call in hass.services.async_call.await_args_list]
        assert hvac_modes == ["dry"]
        assert coordinator._async_process_room_locked.await_args.kwargs["command_generation"] == 0
        assert coordinator._manual_command_generations[area_id] == 2

    @pytest.mark.asyncio
    async def test_current_generation_keeps_automatic_control_enabled(self, hass, mock_config_entry):
        """A current coordinator decision is still applied normally."""
        coordinator, store = _setup_coordinator(
            hass,
            mock_config_entry,
            {"living_room_abc12345": SAMPLE_ROOM},
        )

        async def apply_current_decision(_room, _settings, _forecast, *, command_generation):
            return {
                "apply_control": command_generation
                == coordinator._manual_command_generations.get("living_room_abc12345", 0)
            }

        coordinator._async_process_room_locked = AsyncMock(side_effect=apply_current_decision)

        result = await coordinator._async_process_room(
            SAMPLE_ROOM,
            store.get_settings(),
            [],
            command_generation=0,
        )

        assert result["apply_control"] is True
        assert coordinator._async_process_room_locked.await_args.kwargs["command_generation"] == 0

    @pytest.mark.asyncio
    async def test_normal_heating(self, hass, mock_config_entry):
        """temp=18, schedule=on: should heat toward comfort_temp=21."""
        coordinator, store = _setup_coordinator(
            hass,
            mock_config_entry,
            {"living_room_abc12345": SAMPLE_ROOM},
        )
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(temp="18.0", humidity="55.0"),
        )

        settings = store.get_settings()
        result = await coordinator._async_process_room(SAMPLE_ROOM, settings, [])

        # All expected keys present
        assert set(result.keys()) == NORMAL_ROOM_KEYS

        assert result["area_id"] == "living_room_abc12345"
        assert result["current_temp"] == 18.0
        assert result["target_temp"] == pytest.approx(21.0)
        assert result["heat_target"] == pytest.approx(21.0)
        assert result["mode"] == "heating"
        assert result["heating_power"] > 0
        assert result["window_open"] is False
        assert result["override_active"] is False
        assert result["presence_away"] is False
        assert result["force_off"] is False
        assert result["mold_risk_level"] == "ok"
        assert result["mold_prevention_active"] is False
        assert result["mold_prevention_delta"] == 0
        assert result["q_occupancy"] == 0.0

    @pytest.mark.asyncio
    async def test_idle_at_target(self, hass, mock_config_entry):
        """temp=21 (at comfort_temp), schedule=on: target_temp=21, mode idle."""
        coordinator, store = _setup_coordinator(
            hass,
            mock_config_entry,
            {"living_room_abc12345": SAMPLE_ROOM},
        )
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(temp="21.0", humidity="55.0"),
        )

        settings = store.get_settings()
        result = await coordinator._async_process_room(SAMPLE_ROOM, settings, [])

        assert result["area_id"] == "living_room_abc12345"
        assert result["current_temp"] == 21.0
        assert result["target_temp"] == pytest.approx(21.0)
        assert result["heat_target"] == pytest.approx(21.0)
        # At target, bang-bang controller should be idle
        assert result["mode"] == "idle"
        assert result["heating_power"] == 0

    @pytest.mark.asyncio
    async def test_device_setpoint_mixed_direct_proportional_cooling(self, hass, mock_config_entry):
        """AC (direct) + TRV (proportional) in the same room, cooling mode.

        Regression test: device_setpoint must reflect what async_apply()
        actually sends to the AC (the real cool_target), not the TRV's
        presence dragging the whole room into the proportional boost
        formula. Before the fix, this returned ~16.0 (AC_COOLING_BOOST_TARGET)
        instead of the real target of 24.0.
        """
        room = {
            **SAMPLE_ROOM,
            "area_id": "bedroom_mixed_xyz",
            "thermostats": ["climate.bedroom_trv"],
            "acs": ["climate.bedroom_ac"],
            "devices": [
                {
                    "entity_id": "climate.bedroom_trv",
                    "type": "trv",
                    "role": "auto",
                    "heating_system_type": "radiator",
                    "setpoint_mode": "proportional",
                    "idle_action": "off",
                },
                {
                    "entity_id": "climate.bedroom_ac",
                    "type": "ac",
                    "role": "auto",
                    "heating_system_type": "",
                    "setpoint_mode": "direct",
                    "idle_action": "fan_only",
                },
            ],
            "climate_mode": "cool_only",
        }
        coordinator, store = _setup_coordinator(
            hass,
            mock_config_entry,
            {"bedroom_mixed_xyz": room},
        )
        # current_temp (26.0) well above comfort_cool (24.0) -> strong cooling
        # demand (power_fraction near 1.0), which is what previously drove the
        # proportional formula all the way down to the boost floor.
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(temp="26.0", humidity="55.0"),
        )

        settings = store.get_settings()
        result = await coordinator._async_process_room(room, settings, [])

        assert result["mode"] == "cooling"
        assert result["cool_target"] == pytest.approx(24.0)
        assert result["device_setpoint"] == pytest.approx(24.0)

    @pytest.mark.asyncio
    async def test_window_open(self, hass, mock_config_entry):
        """Window sensor on: window_open=True, mode=idle."""
        room = {
            **SAMPLE_ROOM,
            "window_sensors": ["binary_sensor.w1"],
        }
        coordinator, store = _setup_coordinator(
            hass,
            mock_config_entry,
            {"living_room_abc12345": room},
        )
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="18.0",
                humidity="55.0",
                window_sensors={"binary_sensor.w1": "on"},
            ),
        )

        settings = store.get_settings()
        result = await coordinator._async_process_room(room, settings, [])

        assert result["window_open"] is True
        assert result["mode"] == "idle"
        assert result["heating_power"] == 0

    @pytest.mark.asyncio
    async def test_outdoor_room(self, hass, mock_config_entry):
        """is_outdoor=True: returns reduced key set, mode=idle, force_off=False."""
        room = {
            **SAMPLE_ROOM,
            "is_outdoor": True,
        }
        coordinator, store = _setup_coordinator(
            hass,
            mock_config_entry,
            {"living_room_abc12345": room},
        )
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(temp="18.0", humidity="55.0"),
        )

        settings = store.get_settings()
        result = await coordinator._async_process_room(room, settings, [])

        assert set(result.keys()) == OUTDOOR_ROOM_KEYS
        assert result["mode"] == "idle"
        assert result["force_off"] is False  # NOT True!
        assert result["target_temp"] is None
        assert result["override_active"] is False
        # Outdoor rooms now include q_occupancy and active_heat_sources for consistency
        assert result["q_occupancy"] == 0.0
        assert result["active_heat_sources"] is None

    @pytest.mark.asyncio
    async def test_climate_control_disabled(self, hass, mock_config_entry):
        """climate_control_enabled=False: mode=idle, heating_power=0."""
        room = {**SAMPLE_ROOM, "climate_control_enabled": False}
        coordinator, store = _setup_coordinator(
            hass,
            mock_config_entry,
            {"living_room_abc12345": room},
        )
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(temp="18.0", humidity="55.0"),
        )

        settings = store.get_settings()
        result = await coordinator._async_process_room(room, settings, [])

        assert result["mode"] == "idle"
        assert result["heating_power"] == 0
        # All normal keys should still be present
        assert set(result.keys()) == NORMAL_ROOM_KEYS

    @pytest.mark.asyncio
    async def test_managed_mode(self, hass, mock_config_entry):
        """MANAGED_ROOM with device temp: target_temp is not None."""
        coordinator, store = _setup_coordinator(
            hass,
            mock_config_entry,
            {"living_room_abc12345": MANAGED_ROOM},
        )
        # Provide device temperature via climate entity's current_temperature
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp=None,  # No external sensor
                humidity="55.0",
                extra={
                    "climate.living_room": (
                        "heat",
                        {
                            "current_temperature": 19.0,
                            "temperature": 21.0,
                            "hvac_modes": ["off", "heat"],
                            "max_temp": 30,
                            "min_temp": 5,
                        },
                    ),
                },
            ),
        )

        settings = store.get_settings()
        result = await coordinator._async_process_room(MANAGED_ROOM, settings, [])

        assert result["target_temp"] is not None
        # Managed mode should still return all normal keys
        assert set(result.keys()) == NORMAL_ROOM_KEYS
