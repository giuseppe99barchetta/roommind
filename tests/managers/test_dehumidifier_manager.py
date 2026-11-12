"""Physical device arbitration, interlocks and service contracts."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.managers.dehumidifier_manager import DehumidifierManager, fan_level
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
    manager.collect(rooms, humidity, molds or {})
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
    manager.collect(rooms, {"bed": 57.0}, {"bed": ("warning", 72, True, "dehumidifier", mold_target)})
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
async def test_midea_five_percent_step_does_not_reissue_commands(control, monkeypatch):
    """Midea omits the step in HA: 51% must be commanded as 50%, not retried every minute."""
    manager, rooms, states, clock = control
    rooms["bed"].update(humidity_target=55)
    rooms["bed"]["dehumidifier"].update(entity_id="humidifier.midea", served_area_ids=[], min_off_minutes=0)
    states["humidifier.midea"] = SimpleNamespace(
        state="off",
        attributes={"device_class": "dehumidifier", "min_humidity": 35, "max_humidity": 85, "humidity": 45},
    )
    manager.hass.data = {}
    registry = SimpleNamespace(
        async_get=lambda eid: SimpleNamespace(platform="midea") if eid == "humidifier.midea" else None
    )
    monkeypatch.setattr("custom_components.roommind.managers.dehumidifier_manager.er.async_get", lambda hass: registry)
    humidity = {"bed": 65, "bath": 55}
    molds = {"bed": ("warning", 75, True, "dehumidifier", 51)}

    prepare(control, humidity, molds=molds)
    assert manager.devices["humidifier.midea"]["target_humidity"] == 50
    await manager.apply(PowerBudgetManager())
    calls = [call.args[:3] for call in manager.hass.services.async_call.call_args_list]
    assert ("humidifier", "set_humidity", {"entity_id": "humidifier.midea", "humidity": 50}) in calls
    assert ("humidifier", "turn_on", {"entity_id": "humidifier.midea"}) in calls

    states["humidifier.midea"].state = "on"
    states["humidifier.midea"].attributes["humidity"] = "50"  # Integration may return a numeric string.
    clock[0] += 61
    manager.hass.services.async_call.reset_mock()
    prepare(control, humidity, molds=molds)
    await manager.apply(PowerBudgetManager())
    manager.hass.services.async_call.assert_not_awaited()

    # A genuinely drier mold target must still result in a new device command.
    molds["bed"] = ("warning", 75, True, "dehumidifier", 49)
    prepare(control, humidity, molds=molds)
    await manager.apply(PowerBudgetManager())
    assert manager.hass.services.async_call.call_args.args[:3] == (
        "humidifier",
        "set_humidity",
        {"entity_id": "humidifier.midea", "humidity": 45},
    )


def test_mold_demand_stops_when_air_is_well_below_comfort_target(control):
    manager, rooms, _, _ = control
    rooms["bed"].update(humidity_target=56)
    molds = {"bed": ("warning", 75, True, "dehumidifier", 45)}

    prepare(control, {"bed": 52.0, "bath": 50.0}, molds=molds)
    assert manager.requests.get("bed") == "mold"

    prepare(control, {"bed": 51.0, "bath": 50.0}, molds=molds)  # target - 5
    assert "bed" not in manager.requests

    prepare(control, {"bed": 52.5, "bath": 50.0}, molds=molds)  # hysteresis: still stopped
    assert "bed" not in manager.requests

    prepare(control, {"bed": 53.5, "bath": 50.0}, molds=molds)  # above target - 3: resumes
    assert manager.requests.get("bed") == "mold"


def test_mold_demand_unaffected_without_comfort_target(control):
    manager, rooms, _, _ = control
    rooms["bed"]["humidity_comfort_enabled"] = False
    prepare(control, {"bed": 40.0, "bath": 40.0}, molds={"bed": ("warning", 75, True, "dehumidifier", 45)})
    assert manager.requests.get("bed") == "mold"


def test_non_midea_without_reported_step_keeps_precise_target(control, monkeypatch):
    """Do not impose Midea's five-percent increments on other humidifier platforms."""
    manager, _, states, _ = control
    states["humidifier.native"] = SimpleNamespace(
        state="off",
        attributes={"device_class": "dehumidifier", "min_humidity": 35, "max_humidity": 85},
    )
    manager.hass.data = {}
    registry = SimpleNamespace(async_get=lambda eid: SimpleNamespace(platform="other"))
    monkeypatch.setattr("custom_components.roommind.managers.dehumidifier_manager.er.async_get", lambda hass: registry)
    assert manager._native_target("humidifier.native", 51) == 51


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


@pytest.mark.asyncio
async def test_user_off_is_respected_until_timeout(control):
    manager, _, states, clock = control
    await start_automatic_run(control)
    states["switch.dryer"].state = "off"
    clock[0] += 10
    prepare(control)
    await manager.apply(PowerBudgetManager())
    assert manager.devices["switch.dryer"]["reason"] == "user_off"
    assert manager.devices["switch.dryer"]["user_off_until"] is not None
    manager.hass.services.async_call.assert_not_awaited()
    clock[0] += 60 * 60
    prepare(control)
    await manager.apply(PowerBudgetManager())
    assert manager.hass.services.async_call.call_args.args[1] == "turn_on"


@pytest.mark.asyncio
async def test_user_off_ends_when_demand_ends(control):
    manager, _, states, clock = control
    await start_automatic_run(control)
    states["switch.dryer"].state = "off"
    clock[0] += 10
    prepare(control)
    assert manager.devices["switch.dryer"]["reason"] == "user_off"
    prepare(control, {"bed": 55, "bath": 55})
    clock[0] += 10
    prepare(control)
    await manager.apply(PowerBudgetManager())
    assert manager.devices["switch.dryer"]["reason"] is None
    assert manager.hass.services.async_call.call_args.args[1] == "turn_on"


def _fan_calls(manager):
    return [c.args[:3] for c in manager.hass.services.async_call.call_args_list if c.args[0] == "select"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("night", "current", "expected"),
    [(True, "high", "low"), (False, "low", "high"), (True, "low", None), (False, "high", None)],
)
async def test_fan_low_at_night_auto_by_day(control, night, current, expected):
    manager, rooms, states, _ = control
    rooms["bed"]["dehumidifier"]["fan_entity"] = "select.fan"
    states["select.fan"] = SimpleNamespace(state=current, attributes={"options": ["low", "high", "auto"]})
    prepare(control)
    manager.devices["switch.dryer"]["night"] = night
    await manager.apply(PowerBudgetManager())
    assert _fan_calls(manager) == []  # never in the turn_on cycle: it would switch the unit off
    states["switch.dryer"].state = "on"
    prepare(control)
    manager.devices["switch.dryer"]["night"] = night
    await manager.apply(PowerBudgetManager())
    want = [("select", "select_option", {"entity_id": "select.fan", "option": expected})] if expected else []
    assert _fan_calls(manager) == want


@pytest.mark.asyncio
async def test_fan_not_resent_when_device_reads_option_back_differently(control):
    manager, rooms, states, clock = control
    rooms["bed"]["dehumidifier"]["fan_entity"] = "select.fan"
    states["select.fan"] = SimpleNamespace(state="low", attributes={"options": ["low", "medium", "high"]})

    def midea_quirk(domain, service, data, **kwargs):
        if domain == "select":
            states["select.fan"].state = "medium"  # the device reports another speed than the one set

    manager.hass.services.async_call.side_effect = midea_quirk
    prepare(control)
    await manager.apply(PowerBudgetManager())  # turn_on cycle
    states["switch.dryer"].state = "on"
    for _ in range(3):
        clock[0] += 61
        prepare(control)
        await manager.apply(PowerBudgetManager())
    assert len(_fan_calls(manager)) == 1


@pytest.mark.parametrize(
    ("risk", "surface_rh", "expected"), [("critical", 90, 2), ("warning", 70, 1), ("ok", 66, 1), ("ok", 50, 0)]
)
def test_wall_risk_sets_a_minimum_fan_level(control, risk, surface_rh, expected):
    manager, _, _, _ = control
    # Air only just above target (small gap): the wall alone decides the level.
    prepare(control, {"bed": 56.0, "bath": 56.0}, molds={"bed": (risk, surface_rh, True, "dehumidifier", None)})
    assert manager.requests.get("bed") in ("mold", "comfort")
    assert manager.runtime["switch.dryer"].fan_level == expected


@pytest.mark.parametrize(
    ("gap", "previous", "expected"),
    [(1, 0, 0), (4, 0, 1), (9, 0, 2), (12, 2, 2), (8, 2, 2), (6, 2, 1), (3, 1, 1), (1.5, 1, 0), (-5, 2, 0)],
)
def test_fan_level_steps_up_at_once_and_down_with_hysteresis(gap, previous, expected):
    assert fan_level(gap, previous) == expected


@pytest.mark.asyncio
async def test_fan_untouched_without_entity_or_option(control):
    manager, rooms, states, _ = control
    prepare(control)
    manager.devices["switch.dryer"]["night"] = True
    await manager.apply(PowerBudgetManager())
    assert _fan_calls(manager) == []  # no fan_entity configured

    rooms["bed"]["dehumidifier"]["fan_entity"] = "select.fan"
    states["select.fan"] = SimpleNamespace(state="high", attributes={"options": ["medium", "high"]})
    prepare(control)
    manager.devices["switch.dryer"]["night"] = True
    await manager.apply(PowerBudgetManager())
    assert _fan_calls(manager) == []  # "low" unsupported


@pytest.mark.asyncio
async def test_user_off_blocks_mold_demand(control):
    manager, _, states, clock = control
    await start_automatic_run(control)
    states["switch.dryer"].state = "off"
    clock[0] += 10
    prepare(control, molds={"bath": (None, None, True, "dehumidifier", None)})
    await manager.apply(PowerBudgetManager())
    assert manager.devices["switch.dryer"]["reason"] == "user_off"
    manager.hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_our_off_is_not_a_user_off(control):
    manager, rooms, states, clock = control
    await start_automatic_run(control)
    rooms["bed"]["dehumidifier"]["min_run_minutes"] = 0
    prepare(control, {"bed": 55, "bath": 55})
    await manager.apply(PowerBudgetManager())
    assert manager.hass.services.async_call.call_args.args[1] == "turn_off"
    states["switch.dryer"].state = "off"
    clock[0] += 120
    prepare(control)
    assert manager.devices["switch.dryer"]["reason"] is None


async def _user_turns_off(control):
    manager, _, states, clock = control
    await start_automatic_run(control)
    states["switch.dryer"].state = "off"
    clock[0] += 10


@pytest.mark.asyncio
async def test_tank_full_off_is_not_a_user_off(control):
    manager, rooms, states, clock = control
    rooms["bed"]["dehumidifier"]["tank_full_entity"] = "binary_sensor.tank"
    states["binary_sensor.tank"] = SimpleNamespace(state="off", attributes={})
    await _user_turns_off(control)
    states["binary_sensor.tank"].state = "on"
    prepare(control)
    await manager.apply(PowerBudgetManager())
    assert manager.devices["switch.dryer"]["reason"] == "tank_full"
    manager.hass.services.async_call.assert_not_awaited()
    states["binary_sensor.tank"].state = "off"
    clock[0] += 10
    prepare(control)
    await manager.apply(PowerBudgetManager())
    assert manager.hass.services.async_call.call_args.args[1] == "turn_on"


@pytest.mark.asyncio
async def test_late_tank_full_report_cancels_user_off(control):
    manager, rooms, states, clock = control
    rooms["bed"]["dehumidifier"]["tank_full_entity"] = "binary_sensor.tank"
    states["binary_sensor.tank"] = SimpleNamespace(state="off", attributes={})
    await _user_turns_off(control)
    prepare(control)
    assert manager.devices["switch.dryer"]["reason"] == "user_off"
    states["binary_sensor.tank"].state = "on"
    prepare(control)
    states["binary_sensor.tank"].state = "off"
    prepare(control)
    assert manager.devices["switch.dryer"]["reason"] is None


@pytest.mark.asyncio
async def test_off_after_unavailable_is_not_a_user_off(control):
    manager, _, states, clock = control
    await start_automatic_run(control)
    states["switch.dryer"].state = "unavailable"
    clock[0] += 10
    prepare(control)
    states["switch.dryer"].state = "off"
    clock[0] += 10
    prepare(control)
    assert manager.devices["switch.dryer"]["reason"] is None


@pytest.mark.asyncio
async def test_sensor_dropout_keeps_user_off(control):
    manager, _, _, _ = control
    await _user_turns_off(control)
    prepare(control, {"bed": 55, "bath": None})
    prepare(control)
    assert manager.devices["switch.dryer"]["reason"] == "user_off"


@pytest.mark.asyncio
async def test_user_on_ends_user_off(control):
    manager, _, states, clock = control
    await _user_turns_off(control)
    prepare(control)
    states["switch.dryer"].state = "on"
    clock[0] += 10
    prepare(control)
    states["switch.dryer"].state = "off"
    clock[0] += 10
    prepare(control)
    assert manager.devices["switch.dryer"]["reason"] is None


@pytest.mark.asyncio
async def test_user_off_during_min_run_is_respected(control):
    manager, rooms, states, clock = control
    rooms["bed"]["dehumidifier"]["min_run_minutes"] = 30
    await _user_turns_off(control)
    prepare(control)
    await manager.apply(PowerBudgetManager())
    assert manager.devices["switch.dryer"]["reason"] == "user_off"
    manager.hass.services.async_call.assert_not_awaited()


def _native(states, mode="clothes_dry", state="off"):
    states["humidifier.native"] = SimpleNamespace(
        state=state,
        attributes={
            "device_class": "dehumidifier",
            "humidity": 50,
            "mode": mode,
            "available_modes": ["auto", "continuous", "clothes_dry"],
        },
    )


@pytest.mark.asyncio
async def test_start_mode_applied_when_roommind_starts_device(control):
    manager, rooms, states, _ = control
    rooms["bed"]["dehumidifier"].update(entity_id="humidifier.native", served_area_ids=[], start_mode="auto")
    _native(states)
    prepare(control, {"bed": 70, "bath": 55})
    await manager.apply(PowerBudgetManager())
    calls = [c.args for c in manager.hass.services.async_call.call_args_list]
    assert calls[-2][1] == "turn_on"
    assert calls[-1] == ("humidifier", "set_mode", {"entity_id": "humidifier.native", "mode": "auto"})


@pytest.mark.asyncio
@pytest.mark.parametrize("start_mode", ["", "silent", "clothes_dry"])
async def test_start_mode_skipped_when_unset_unsupported_or_already_set(control, start_mode):
    manager, rooms, states, _ = control
    rooms["bed"]["dehumidifier"].update(entity_id="humidifier.native", served_area_ids=[], start_mode=start_mode)
    _native(states)
    prepare(control, {"bed": 70, "bath": 55})
    await manager.apply(PowerBudgetManager())
    services = [c.args[1] for c in manager.hass.services.async_call.call_args_list]
    assert "turn_on" in services
    assert "set_mode" not in services


@pytest.mark.asyncio
async def test_start_mode_never_touches_a_manual_run(control):
    manager, rooms, states, _ = control
    rooms["bed"]["dehumidifier"].update(entity_id="humidifier.native", served_area_ids=[], start_mode="auto")
    _native(states, state="on")
    prepare(control, {"bed": 70, "bath": 55})
    await manager.apply(PowerBudgetManager())
    services = [c.args[1] for c in manager.hass.services.async_call.call_args_list]
    assert "set_mode" not in services


@pytest.mark.asyncio
async def test_native_target_follows_season(control, monkeypatch):
    manager, rooms, states, _ = control
    monkeypatch.setattr(
        "custom_components.roommind.managers.dehumidifier_manager.current_season", lambda hass: "winter"
    )
    rooms["bed"].update(humidity_target=55, humidity_season_targets={"winter": 48, "summer": 58})
    rooms["bed"]["dehumidifier"].update(entity_id="humidifier.native", served_area_ids=[])
    _native(states, mode="auto")
    prepare(control, {"bed": 70, "bath": 55})
    await manager.apply(PowerBudgetManager())
    assert manager.hass.services.async_call.call_args_list[0].args[2]["humidity"] == 48


@pytest.mark.asyncio
async def test_adopt_hands_a_manual_run_to_roommind(control):
    manager, _, states, clock = control
    states["switch.dryer"].state = "on"
    prepare(control)
    assert manager.devices["switch.dryer"]["reason"] == "manual"
    assert manager.adopt("switch.dryer") is True
    clock[0] += 400  # past min_run
    prepare(control, humidities={"bed": 40.0, "bath": 40.0})  # no demand any more
    await manager.apply(PowerBudgetManager())
    assert manager.hass.services.async_call.call_args.args[1] == "turn_off"


def test_adopt_refused_unless_device_runs_manually(control):
    manager, rooms, states, _ = control
    prepare(control)
    assert manager.adopt("switch.dryer") is False  # off: nothing to adopt
    assert manager.adopt("switch.missing") is False
    states["switch.dryer"].state = "on"
    rooms["bed"]["dehumidifier"]["mode"] = "manual"
    prepare(control)
    assert manager.adopt("switch.dryer") is False  # user chose manual mode in settings


def test_room_status_reports_fan_speed(control):
    manager, rooms, states, _ = control
    rooms["bed"]["dehumidifier"]["fan_entity"] = "select.fan"
    states["select.fan"] = SimpleNamespace(state="high", attributes={})
    prepare(control)
    assert manager.room_status("bath")["devices"][0]["fan_speed"] == "high"
    del states["select.fan"]
    prepare(control)
    assert manager.room_status("bath")["devices"][0]["fan_speed"] is None


@pytest.mark.asyncio
async def test_forecast_reports_minutes_power_and_heat_for_each_served_room(control):
    manager, rooms, _, _ = control
    rooms["bed"]["dehumidifier"]["power_watts"] = 200
    await start_automatic_run(control)
    device = manager.room_status("bath")["devices"][0]
    assert device["forecast_minutes"]["bed"] == 0  # already at target
    assert device["forecast_minutes"]["bath"] > 0
    assert device["forecast_power_w"] == 200
    assert device["forecast_learned"] is False


def test_forecast_is_empty_when_device_idle(control):
    prepare(control, humidities={"bed": 40.0, "bath": 40.0})
    device = control[0].room_status("bath")["devices"][0]
    assert device["forecast_minutes"] is None
    assert device["forecast_heat_c"] is None


@pytest.mark.asyncio
async def test_drying_rate_is_learned_over_a_ten_minute_run(control):
    manager, _, _, clock = control
    await start_automatic_run(control)
    before = list(manager.runtime["switch.dryer"].k)
    clock[0] += 601
    prepare(control, humidities={"bed": 50.0, "bath": 64.0})  # bath stays above the high-fan step
    runtime = manager.runtime["switch.dryer"]
    level = 0  # no fan entity: a single bucket
    assert runtime.k_n[level] == 1
    assert runtime.k[level] != before[level]
    assert manager.room_status("bath")["devices"][0]["forecast_learned"] is True


@pytest.mark.asyncio
async def test_window_without_a_visible_drop_keeps_measuring(control):
    manager, _, _, clock = control
    await start_automatic_run(control)
    clock[0] += 601
    prepare(control, humidities={"bed": 55.0, "bath": 65.0})  # sensor still shows no change
    runtime = manager.runtime["switch.dryer"]
    assert sum(runtime.k_n) == 0
    anchor = runtime.anchors["bed"]
    clock[0] += 601
    prepare(control, humidities={"bed": 50.0, "bath": 65.0})
    assert runtime.k_n[0] == 1 and runtime.anchors["bed"] != anchor


def test_single_speed_unit_has_no_forecast_while_paused(control):
    manager, _, states, _ = control
    states["switch.dryer"].state = "on"
    prepare(control, windows={"bed": True})
    assert manager.room_status("bath")["devices"][0]["forecast_minutes"] is None


def test_learned_rates_survive_runtime_reset_and_restore_from_storage(control):
    manager, _, _, _ = control
    prepare(control)
    manager.runtime["switch.dryer"].k[1] = 0.9
    manager.runtime["switch.dryer"].k_n[1] = 4
    manager.runtime.clear()  # reconfigure drops runtime, not what was learned
    prepare(control)
    assert manager.runtime["switch.dryer"].k[1] == 0.9

    fresh = DehumidifierManager(manager.hass)
    fresh.load_learned({**manager.learned, "switch.bad": {"k": [9, 9, 9], "k_n": [1, 1, 1]}, "x": "junk"})
    assert fresh.learned["switch.dryer"]["k"] == manager.learned["switch.dryer"]["k"]
    assert fresh.learned["switch.dryer"]["k_n"] == [0, 4, 0]
    assert "switch.bad" not in fresh.learned and "x" not in fresh.learned


@pytest.mark.asyncio
async def test_served_room_learns_its_own_rate_and_is_flagged_until_then(control):
    manager, _, _, clock = control
    await start_automatic_run(control)
    device = manager.room_status("bath")["devices"][0]
    assert device["forecast_learned"] is False  # bath only has the damped host default
    assert manager.learned["switch.dryer"]["areas"] == {}
    clock[0] += 601
    prepare(control, humidities={"bed": 50.0, "bath": 64.0})
    assert manager.learned["switch.dryer"]["areas"]["bath"]["k_n"][0] == 1
    assert manager.dirty is True


@pytest.mark.asyncio
async def test_measured_power_overrides_nominal_and_handles_kw(control):
    manager, rooms, states, _ = control
    rooms["bed"]["dehumidifier"].update(power_watts=200, power_entity="sensor.p")
    states["sensor.p"] = SimpleNamespace(state="0.15", attributes={"unit_of_measurement": "kW"})
    await start_automatic_run(control)
    device = manager.room_status("bath")["devices"][0]
    assert device["measured_power_w"] == 150 and device["forecast_power_w"] == 150
    states["sensor.p"].state = "unavailable"
    prepare(control)
    device = manager.room_status("bath")["devices"][0]
    assert device["measured_power_w"] is None and device["forecast_power_w"] == 200


@pytest.mark.asyncio
async def test_completed_run_records_predicted_vs_actual_and_flags_unreachable(control):
    manager, rooms, _, clock = control
    await start_automatic_run(control)
    assert manager.runtime["switch.dryer"].run["area"] == "bath"
    predicted = manager.runtime["switch.dryer"].run["predicted"]
    clock[0] += 1800
    prepare(control, humidities={"bed": 50.0, "bath": 55.0})  # demand over: comfort stops
    assert manager.learned["switch.dryer"]["runs"] == [{"predicted": predicted, "actual": 30}]
    assert manager.room_status("bath")["devices"][0]["last_run"]["actual"] == 30

    manager.learned["switch.dryer"]["k"] = [0.001] * 3
    manager.runtime["switch.dryer"].k = manager.learned["switch.dryer"]["k"]
    prepare(control, humidities={"bed": 70.0, "bath": 80.0})
    assert manager.room_status("bath")["devices"][0]["forecast_unreachable"] is True


def test_heat_estimate_includes_latent_heat_and_steady_state_without_eta():
    from custom_components.roommind.utils.dehumidifier_forecast import heat_gain_c

    assert heat_gain_c(360.0, None) == 3.6
    assert heat_gain_c(360.0, 10_000) == 3.6
    assert heat_gain_c(360.0, 0.0) == 0.0


def test_load_learned_validates_areas_and_runs(control):
    manager, _, _, _ = control
    good = {"k": [0.2, 0.3, 0.4], "k_n": [1, 0, 0]}
    manager.load_learned(
        {
            "switch.dryer": {
                **good,
                "areas": {"bath": good, "bad": {"k": [0], "k_n": [0]}},
                "runs": [{"predicted": 60, "actual": 80}, {"predicted": "x"}, "junk"],
            }
        }
    )
    entry = manager.learned["switch.dryer"]
    assert list(entry["areas"]) == ["bath"]
    assert entry["runs"] == [{"predicted": 60.0, "actual": 80.0}]


@pytest.mark.asyncio
async def test_energy_sensor_is_not_read_as_power(control):
    manager, rooms, states, _ = control
    rooms["bed"]["dehumidifier"]["power_entity"] = "sensor.p"
    states["sensor.p"] = SimpleNamespace(state="12.3", attributes={"unit_of_measurement": "kWh"})
    await start_automatic_run(control)
    assert manager.room_status("bath")["devices"][0]["measured_power_w"] is None


@pytest.mark.asyncio
async def test_interrupted_run_is_not_recorded_and_removed_device_is_forgotten(control):
    manager, rooms, _, clock = control
    await start_automatic_run(control)
    clock[0] += 120
    prepare(control, humidities={"bed": 50.0, "bath": 55.0}, windows={"bed": True})  # window stops it, at target
    assert manager.learned["switch.dryer"]["runs"] == []
    rooms["bed"].pop("dehumidifier")
    prepare(control)
    assert "switch.dryer" not in manager.learned and manager.dirty is True
