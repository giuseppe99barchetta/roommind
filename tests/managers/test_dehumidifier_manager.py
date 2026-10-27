"""Physical device arbitration, interlocks and service contracts."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.managers.dehumidifier_manager import DehumidifierManager
from custom_components.roommind.managers.power_budget_manager import PowerBudgetManager


@pytest.fixture
def control(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("custom_components.roommind.managers.dehumidifier_manager.monotonic", lambda: clock[0])
    monkeypatch.setattr("custom_components.roommind.managers.dehumidifier_manager.night_phase", lambda *args: "day")
    states = {"switch.dryer": SimpleNamespace(state="off", attributes={})}
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get), services=SimpleNamespace(async_call=AsyncMock()))
    manager = DehumidifierManager(hass)
    rooms = {
        "bed": {
            "dehumidifier": {"entity_id": "switch.dryer", "served_area_ids": ["bath"], "min_off_minutes": 0},
            "humidity_comfort_enabled": True,
        },
        "bath": {"humidity_comfort_enabled": True},
    }
    return manager, rooms, states, clock


def prepare(control, humidities=None, molds=None, settings=None, windows=None):
    manager, rooms, _, _ = control
    humidity = humidities or {"bed": 55.0, "bath": 65.0}
    manager.prepare(rooms, settings or {}, humidity, windows or {})
    manager.collect(rooms, humidity, molds or {}, {})
    return manager


async def start_automatic_run(control):
    """Start through RoomMind, then acknowledge the physical ON feedback."""
    manager, _, states, clock = control
    prepare(control)
    await manager.apply(PowerBudgetManager())
    assert manager.hass.services.async_call.call_args.args[1] == "turn_on"
    states["switch.dryer"].state = "on"
    clock[0] += 61
    prepare(control)
    manager.hass.services.async_call.reset_mock()


@pytest.mark.asyncio
async def test_shared_bath_request_starts_only_one_device(control):
    manager = prepare(control)
    await manager.apply(PowerBudgetManager())
    assert manager.assignments == {"bath": "switch.dryer"}
    call = manager.hass.services.async_call.call_args
    assert call.args == ("switch", "turn_on", {"entity_id": "switch.dryer"})
    assert manager.room_status("bath")["devices"][0]["state"] == "off"
    assert manager.room_status("bath")["devices"][0]["action"] is None


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.asyncio
async def test_local_wins_then_running_shared_regardless_of_room_order(control, reverse):
    manager, rooms, states, _ = control
    await start_automatic_run(control)
    rooms["bath"]["dehumidifier"] = {"entity_id": "switch.local", "min_off_minutes": 0}
    states["switch.local"] = SimpleNamespace(state="off", attributes={})
    if reverse:
        control = manager, dict(reversed(list(rooms.items()))), states, control[3]
    prepare(control)
    assert manager.assignments["bath"] == "switch.local"
    states["switch.local"].state = "unavailable"
    prepare(control)
    assert manager.assignments["bath"] == "switch.dryer"


@pytest.mark.asyncio
async def test_floor_stops_immediately_and_holds_until_fifty(control):
    manager, _, states, clock = control
    await start_automatic_run(control)
    manager = prepare(control, {"bed": 45.0, "bath": 70.0})
    await manager.apply(PowerBudgetManager())
    assert manager.devices["switch.dryer"]["reason"] == "humidity_floor"
    assert manager.hass.services.async_call.call_args.args[1] == "turn_off"
    states["switch.dryer"].state = "off"
    clock[0] += 61
    prepare(control, {"bed": 49.0, "bath": 70.0})
    assert not manager.assignments
    prepare(control, {"bed": 50.0, "bath": 70.0})
    assert manager.assignments == {"bath": "switch.dryer"}


@pytest.mark.parametrize("host_open,remote_open,blocked", [(True, False, True), (False, True, False)])
def test_only_host_window_blocks(control, host_open, remote_open, blocked):
    manager = prepare(control, windows={"bed": host_open, "bath": remote_open})
    assert bool(manager.assignments) is not blocked
    assert manager.suppress_ac_dry("bath")


@pytest.mark.parametrize("risk", ["ok", "critical"])
def test_host_night_blocks_comfort_but_allows_mold(control, monkeypatch, risk):
    """Quiet hours pause comfort only; any mold request (even from the 65 % zone) runs."""
    monkeypatch.setattr("custom_components.roommind.managers.dehumidifier_manager.night_phase", lambda *args: "night")
    manager = prepare(control)
    assert not manager.assignments
    assert manager.devices["switch.dryer"]["reason"] == "night"
    mold = {"bath": (risk, 85, True, "dehumidifier", None)}
    prepare(control, molds=mold)
    assert manager.assignments == {"bath": "switch.dryer"}


@pytest.mark.parametrize("comfort,mold_target,expected", [(55.0, 47.0, 47.0), (45.0, 50.0, 45.0), (55.0, None, 55.0)])
def test_mold_run_aims_device_humidistat_at_the_wall(comfort, mold_target, expected):
    """A mold run sets the drier of the comfort target and what the wall needs."""
    states = {
        "humidifier.dry": SimpleNamespace(
            state="off", attributes={"device_class": "dehumidifier", "min_humidity": 35, "max_humidity": 85}
        )
    }
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get), services=SimpleNamespace(async_call=AsyncMock()))
    manager = DehumidifierManager(hass)
    rooms = {
        "bed": {
            "dehumidifier": {"entity_id": "humidifier.dry", "min_off_minutes": 0},
            "humidity_comfort_enabled": True,
            "humidity_target": comfort,
        }
    }
    manager.prepare(rooms, {}, {"bed": 57.0}, {})
    manager.collect(rooms, {"bed": 57.0}, {"bed": ("warning", 72, True, "dehumidifier", mold_target)}, {})
    assert manager.devices["humidifier.dry"]["target_humidity"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["manual", "disabled", "unavailable"])
async def test_no_commands_for_manual_disabled_or_missing_device(control, kind):
    manager, rooms, states, _ = control
    if kind == "manual":
        rooms["bed"]["dehumidifier"]["mode"] = "manual"
    elif kind == "unavailable":
        states["switch.dryer"].state = "unavailable"
    prepare(control, settings={"climate_control_active": kind != "disabled"})
    await manager.apply(PowerBudgetManager())
    manager.hass.services.async_call.assert_not_awaited()
    assert manager.suppress_ac_dry("bath") is (kind != "unavailable")


@pytest.mark.asyncio
async def test_missing_remote_reading_drops_just_its_request(control):
    manager = prepare(control, {"bed": 65, "bath": None})
    assert manager.assignments == {"bed": "switch.dryer"}
    prepare(control, {"bed": None, "bath": 70})
    assert manager.devices["switch.dryer"]["reason"] == "sensor"
    assert not manager.assignments


def test_hysteresis_zero_tolerance_and_active_profile(control):
    manager, rooms, _, _ = control
    rooms["bath"].update(
        humidity_tolerance=0, active_profile="work", comfort_profiles={"work": {"humidity_target": 60}}
    )
    prepare(control, {"bed": 55, "bath": 62.5})
    assert not manager.assignments
    prepare(control, {"bed": 55, "bath": 63})
    assert "bath" in manager.assignments
    prepare(control, {"bed": 55, "bath": 62.5})
    assert "bath" in manager.assignments
    prepare(control, {"bed": 55, "bath": 62})
    assert not manager.assignments


@pytest.mark.asyncio
async def test_restart_waits_minimum_off_time(control):
    manager, rooms, _, clock = control
    rooms["bed"]["dehumidifier"]["min_off_minutes"] = 5
    prepare(control)
    await manager.apply(PowerBudgetManager())
    manager.hass.services.async_call.assert_not_awaited()
    clock[0] += 300
    prepare(control)
    await manager.apply(PowerBudgetManager())
    assert manager.hass.services.async_call.call_args.args[1] == "turn_on"


@pytest.mark.asyncio
async def test_min_run_does_not_override_missing_host_sensor(control):
    manager, _, _, _ = control
    await start_automatic_run(control)
    prepare(control, {"bed": 55, "bath": 55})
    await manager.apply(PowerBudgetManager())
    assert manager.devices["switch.dryer"]["reason"] == "min_run"
    prepare(control, {"bed": None, "bath": 55})
    await manager.apply(PowerBudgetManager())
    assert manager.hass.services.async_call.call_args.args[1] == "turn_off"


@pytest.mark.asyncio
async def test_native_setpoint_and_internal_sensor_fallback(control):
    manager, rooms, states, _ = control
    rooms["bed"]["dehumidifier"]["entity_id"] = "humidifier.native"
    states["humidifier.native"] = SimpleNamespace(
        state="off",
        attributes={
            "device_class": "dehumidifier",
            "current_humidity": 58,
            "min_humidity": 40,
            "max_humidity": 80,
            "target_humidity_step": 10,
            "humidity": 65,
        },
    )
    assert manager.room_humidity(rooms["bed"], None) == 58
    external = {**rooms["bed"], "humidity_sensor": "sensor.external"}
    assert manager.room_humidity(external, None) is None
    prepare(control)
    await manager.apply(PowerBudgetManager())
    calls = manager.hass.services.async_call.call_args_list
    assert calls[0].args == ("humidifier", "set_humidity", {"entity_id": "humidifier.native", "humidity": 50})
    assert calls[1].args[1] == "turn_on"
    assert manager.devices["humidifier.native"]["humidity_floor"] == 50


@pytest.mark.asyncio
async def test_power_budget_requires_nominal_power_and_reserves_once(control):
    manager, rooms, _, _ = control
    budget = MagicMock(spec=PowerBudgetManager)
    budget.request_heat_pump.return_value = False
    prepare(control)
    await manager.apply(budget)
    assert manager.devices["switch.dryer"]["reason"] == "power_budget"
    manager.hass.services.async_call.assert_not_awaited()
    rooms["bed"]["dehumidifier"]["power_watts"] = 250
    budget.request_heat_pump.return_value = True
    prepare(control, {"bed": 65, "bath": 70})
    await manager.apply(budget)
    assert budget.request_heat_pump.call_args.args == ("dehumidifier:switch.dryer", 250, False)
    assert manager.hass.services.async_call.await_count == 1


@pytest.mark.asyncio
async def test_service_error_isolated_to_device(control):
    manager, rooms, states, _ = control
    rooms["bath"]["dehumidifier"] = {"entity_id": "switch.other", "min_off_minutes": 0}
    states["switch.other"] = SimpleNamespace(state="off", attributes={})
    manager.hass.services.async_call.side_effect = [RuntimeError("offline"), None]
    prepare(control, {"bed": 65, "bath": 70})
    await manager.apply(PowerBudgetManager())
    assert manager.hass.services.async_call.await_count == 2
    assert manager.devices["switch.dryer"]["reason"] == "error"
    assert manager.devices["switch.other"]["commanded"] is True


@pytest.mark.asyncio
async def test_release_stops_owned_device_but_unchanged_registration_is_untouched(control):
    manager, rooms, _, _ = control
    await start_automatic_run(control)
    old = deepcopy(rooms["bed"]["dehumidifier"])
    await manager.release(old, deepcopy(old), True)
    manager.hass.services.async_call.assert_not_awaited()
    await manager.release(old, None, True)
    assert manager.hass.services.async_call.call_args.args[1] == "turn_off"


def test_manual_device_never_triggers_fallback_even_when_unavailable(control):
    manager, rooms, states, _ = control
    rooms["bed"]["dehumidifier"]["mode"] = "manual"
    states["switch.dryer"].state = "unavailable"
    prepare(control)
    assert manager.suppress_ac_dry("bath")


@pytest.mark.asyncio
async def test_min_off_applies_while_physical_off_feedback_is_delayed(control):
    manager, rooms, states, clock = control
    await start_automatic_run(control)
    rooms["bed"]["dehumidifier"].update(min_off_minutes=5, min_run_minutes=0)
    prepare(control, {"bed": 55, "bath": 55})
    await manager.apply(PowerBudgetManager())
    assert manager.hass.services.async_call.call_args.args[1] == "turn_off"
    manager.hass.services.async_call.reset_mock()
    clock[0] += 1
    prepare(control)
    await manager.apply(PowerBudgetManager())
    assert manager.devices["switch.dryer"]["reason"] == "min_off"
    manager.hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_loss_of_only_requesting_sensor_overrides_min_run(control):
    manager, _, _, _ = control
    await start_automatic_run(control)
    prepare(control)
    await manager.apply(PowerBudgetManager())
    prepare(control, {"bed": 55, "bath": None})
    await manager.apply(PowerBudgetManager())
    assert manager.devices["switch.dryer"]["reason"] == "sensor"
    assert manager.hass.services.async_call.call_args.args[1] == "turn_off"


def test_window_open_and_close_delays_are_respected(control, monkeypatch):
    manager, rooms, _, clock = control
    monkeypatch.setattr("custom_components.roommind.managers.window_manager.time.time", lambda: clock[0])
    rooms["bed"].update(window_open_delay=60, window_close_delay=30)
    prepare(control)
    clock[0] += 1
    prepare(control, windows={"bed": True})
    assert manager.assignments
    clock[0] += 60
    prepare(control, windows={"bed": True})
    assert not manager.assignments
    prepare(control, windows={"bed": False})
    assert not manager.assignments
    clock[0] += 30
    prepare(control, windows={"bed": False})
    assert manager.assignments


@pytest.mark.asyncio
async def test_native_local_target_follows_active_room_profile(control):
    manager, rooms, states, _ = control
    rooms["bed"].update(active_profile="work", comfort_profiles={"work": {"humidity_target": 60}})
    rooms["bed"]["dehumidifier"].update(entity_id="humidifier.native", served_area_ids=[])
    states["humidifier.native"] = SimpleNamespace(
        state="off", attributes={"device_class": "dehumidifier", "humidity": 50}
    )
    prepare(control, {"bed": 70, "bath": 55})
    await manager.apply(PowerBudgetManager())
    assert manager.hass.services.async_call.call_args_list[0].args[2]["humidity"] == 60


@pytest.mark.asyncio
async def test_humidifier_with_wrong_class_is_never_controlled(control):
    manager, rooms, states, _ = control
    rooms["bed"]["dehumidifier"]["entity_id"] = "humidifier.wrong"
    states["humidifier.wrong"] = SimpleNamespace(state="on", attributes={"device_class": "humidifier"})
    prepare(control)
    await manager.apply(PowerBudgetManager())
    manager.hass.services.async_call.assert_not_awaited()


def test_reconnection_requires_a_known_minimum_off_interval(control):
    manager, rooms, states, clock = control
    rooms["bed"]["dehumidifier"]["min_off_minutes"] = 5
    states["switch.dryer"].state = "unavailable"
    prepare(control)
    clock[0] += 600
    states["switch.dryer"].state = "off"
    prepare(control)
    assert manager.devices["switch.dryer"]["reason"] == "min_off"
    assert not manager.assignments


def test_sensor_outage_does_not_clear_host_floor_hysteresis(control):
    manager = prepare(control, {"bed": 45, "bath": 70})
    assert manager.devices["switch.dryer"]["reason"] == "humidity_floor"
    prepare(control, {"bed": None, "bath": 70})
    prepare(control, {"bed": 49, "bath": 70})
    assert manager.devices["switch.dryer"]["reason"] == "humidity_floor"


@pytest.mark.asyncio
@pytest.mark.parametrize("entity_id", ["switch.dryer", "humidifier.native"])
@pytest.mark.parametrize("already_on", [False, True])
@pytest.mark.parametrize("constraint", ["none", "floor", "sensor", "window", "night", "power_budget"])
async def test_manual_run_is_untouched(control, monkeypatch, entity_id, already_on, constraint):
    """Laundry runs retain power and native settings regardless of automatic demand."""
    manager, rooms, states, clock = control
    rooms["bed"]["dehumidifier"]["entity_id"] = entity_id
    states[entity_id] = SimpleNamespace(
        state="on" if already_on else "off", attributes={"device_class": "dehumidifier", "humidity": 35}
    )
    if not already_on:
        prepare(control, {"bed": 55, "bath": 55})
        await manager.apply(PowerBudgetManager())
        states[entity_id].state = "on"
    budget = MagicMock(spec=PowerBudgetManager)
    budget.request_heat_pump.return_value = constraint != "power_budget"
    if constraint == "night":
        monkeypatch.setattr(
            "custom_components.roommind.managers.dehumidifier_manager.night_phase", lambda *args: "night"
        )
    humidity = {"bed": 45 if constraint == "floor" else None if constraint == "sensor" else 55, "bath": 70}
    # Demand must never transfer ownership; later satisfied demand must not stop it.
    for readings in (humidity, {"bed": 55, "bath": 55}):
        clock[0] += 600
        prepare(control, readings, windows={"bed": constraint == "window"})
        await manager.apply(budget)
        assert manager.devices[entity_id]["reason"] == "manual"
        assert manager.suppress_ac_dry("bath")
        assert not manager.assignments
    manager.hass.services.async_call.assert_not_awaited()
    budget.request_heat_pump.assert_not_called()


@pytest.mark.asyncio
async def test_automatic_run_stops_when_demand_is_satisfied(control):
    manager, _, _, clock = control
    await start_automatic_run(control)
    clock[0] += 300
    prepare(control, {"bed": 55, "bath": 55})
    await manager.apply(PowerBudgetManager())
    assert manager.hass.services.async_call.call_args.args[1] == "turn_off"


@pytest.mark.asyncio
async def test_manual_restart_does_not_inherit_automatic_run(control):
    manager, _, states, clock = control
    await start_automatic_run(control)
    states["switch.dryer"].state = "off"
    prepare(control, {"bed": 55, "bath": 55})
    states["switch.dryer"].state = "on"
    clock[0] += 600
    prepare(control)
    await manager.apply(PowerBudgetManager())
    prepare(control, windows={"bed": True})
    await manager.apply(PowerBudgetManager())
    manager.hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_automatic_control_resumes_after_manual_run_is_turned_off(control):
    manager, _, states, _ = control
    states["switch.dryer"].state = "on"
    prepare(control)
    await manager.apply(PowerBudgetManager())
    manager.hass.services.async_call.assert_not_awaited()
    states["switch.dryer"].state = "off"
    prepare(control)
    await manager.apply(PowerBudgetManager())
    assert manager.hass.services.async_call.call_args.args[1] == "turn_on"
    assert manager.assignments == {"bath": "switch.dryer"}


@pytest.mark.asyncio
async def test_manual_restart_overrides_pending_off(control):
    manager, _, states, clock = control
    await start_automatic_run(control)
    prepare(control, windows={"bed": True})
    await manager.apply(PowerBudgetManager())
    assert manager.hass.services.async_call.call_args.args[1] == "turn_off"
    states["switch.dryer"].state = "off"
    prepare(control, windows={"bed": True})
    states["switch.dryer"].state = "on"
    manager.hass.services.async_call.reset_mock()
    clock[0] += 1
    prepare(control)
    await manager.apply(PowerBudgetManager())
    assert manager.devices["switch.dryer"]["reason"] == "manual"
    manager.hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_mode_relinquishes_ownership_when_auto_is_restored(control):
    manager, rooms, _, _ = control
    await start_automatic_run(control)
    rooms["bed"]["dehumidifier"]["mode"] = "manual"
    prepare(control)
    await manager.apply(PowerBudgetManager())
    rooms["bed"]["dehumidifier"]["mode"] = "auto"
    prepare(control, windows={"bed": True})
    await manager.apply(PowerBudgetManager())
    manager.hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_release_to_manual_relinquishes_ownership_immediately(control):
    manager, rooms, _, _ = control
    await start_automatic_run(control)
    old = deepcopy(rooms["bed"]["dehumidifier"])
    await manager.release(old, {**old, "mode": "manual"}, True)
    prepare(control, windows={"bed": True})
    await manager.apply(PowerBudgetManager())
    await manager.release(old, None, True)
    manager.hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("prepared", [False, True])
async def test_release_preserves_manual_run(control, prepared):
    manager, rooms, states, _ = control
    states["switch.dryer"].state = "on"
    if prepared:
        prepare(control)
    await manager.release(rooms["bed"]["dehumidifier"], None, True)
    manager.hass.services.async_call.assert_not_awaited()
