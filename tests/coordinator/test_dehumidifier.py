"""Physical humidity control runs independently of room thermal mode."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get


def setup_control(hass, entry, *, mode="heat", device_state="off", manual=False, settings=None):
    area = SAMPLE_ROOM["area_id"]
    room = {
        **SAMPLE_ROOM,
        "room_hvac_mode": mode,
        "humidity_comfort_enabled": True,
        "devices": [*SAMPLE_ROOM["devices"], {"entity_id": "climate.ac_unit", "type": "ac"}],
        "dehumidifier": {"entity_id": "switch.dryer", "mode": "manual" if manual else "auto", "min_off_minutes": 0},
    }
    store = _make_store_mock({area: room}, settings)
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(
        side_effect=make_mock_states_get(
            temp="18.0" if mode == "heat" else "27.0" if mode == "cool" else "24.0",
            humidity="80",
            outdoor_temp="24" if mode == "cool" else "10",
            extra={
                "switch.dryer": (device_state, {}),
                "climate.ac_unit": (
                    "off",
                    {"hvac_modes": ["off", "heat", "cool", "dry"], "min_temp": 16, "max_temp": 30},
                ),
            },
        )
    )
    hass.services.async_call = AsyncMock()
    return _create_coordinator(hass, entry), store, room


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,thermal", [("heat", "heating"), ("cool", "cooling"), ("off", "idle")])
async def test_dedicated_comfort_does_not_replace_thermal_mode(hass, mock_config_entry, mode, thermal):
    coordinator, _, room = setup_control(hass, mock_config_entry, mode=mode)
    result = await coordinator._async_update_data()
    live = result["rooms"][room["area_id"]]
    assert live["mode"] == thermal
    assert live["dehumidifier"]["assigned_entity_id"] == "switch.dryer"
    assert any(c.args[:2] == ("switch", "turn_on") for c in hass.services.async_call.call_args_list)
    assert not any(c.args[2].get("hvac_mode") == "dry" for c in hass.services.async_call.call_args_list)
    assert room["room_hvac_mode"] == mode


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "manual,available,expects_dry", [(False, "off", False), (True, "off", False), (False, "unavailable", True)]
)
async def test_ac_fallback_only_for_physical_unavailability(hass, mock_config_entry, manual, available, expects_dry):
    coordinator, _, _ = setup_control(hass, mock_config_entry, mode="off", device_state=available, manual=manual)
    await coordinator._async_update_data()
    assert any(c.args[2].get("hvac_mode") == "dry" for c in hass.services.async_call.call_args_list) is expects_dry


@pytest.mark.asyncio
async def test_disabled_automation_sends_no_dehumidifier_commands(hass, mock_config_entry):
    coordinator, _, _ = setup_control(hass, mock_config_entry, settings={"climate_control_active": False})
    await coordinator._async_update_data()
    assert not any(c.args[0] in ("humidifier", "switch", "climate") for c in hass.services.async_call.call_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("humidity_comfort", [False, True])
async def test_running_manual_dehumidifier_is_not_claimed_or_stopped(hass, mock_config_entry, humidity_comfort):
    coordinator, _, room = setup_control(hass, mock_config_entry, mode="off", device_state="on")
    room["humidity_comfort_enabled"] = humidity_comfort
    result = await coordinator._async_update_data()
    status = result["rooms"][room["area_id"]]["dehumidifier"]
    assert status["devices"][0]["reason"] == "manual"
    assert status["assigned_entity_id"] is None
    assert not any(c.args[0] == "switch" for c in hass.services.async_call.call_args_list)
    assert not any(c.args[2].get("hvac_mode") == "dry" for c in hass.services.async_call.call_args_list)


@pytest.mark.asyncio
async def test_mold_prefers_dedicated_without_dry_temperature_or_runtime_limits(hass, mock_config_entry):
    settings = {"mold_prevention_enabled": True, "mold_prevention_sustained_minutes": 0}
    coordinator, _, room = setup_control(hass, mock_config_entry, settings=settings)
    result = await coordinator._async_update_data()
    live = result["rooms"][room["area_id"]]
    assert live["mold_prevention_strategy"] == "dehumidifier", {
        k: live.get(k)
        for k in (
            "current_temp",
            "current_humidity",
            "mold_risk_level",
            "mold_surface_rh",
            "mold_prevention_active",
            "dehumidifier",
        )
    }
    assert live["mode"] == "heating"
    assert live["dehumidifier"]["request"] == "mold"
    coordinator._mold_manager._prevention_started[room["area_id"]] -= 4 * 3600
    result = await coordinator._async_update_data()
    assert result["rooms"][room["area_id"]]["mold_prevention_strategy"] == "dehumidifier"


@pytest.mark.asyncio
async def test_native_action_reported_without_claiming_switch_compressor_is_running(hass, mock_config_entry):
    coordinator, _, room = setup_control(hass, mock_config_entry)
    result = await coordinator._async_update_data()
    assert result["rooms"][room["area_id"]]["humidity_action"] == "idle"
