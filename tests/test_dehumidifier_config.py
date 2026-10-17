"""Persisted registration validation and safe device removal through the API."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol

from custom_components.roommind.const import DOMAIN
from custom_components.roommind.managers.dehumidifier_manager import DehumidifierManager, DeviceRuntime
from custom_components.roommind.websocket_api import websocket_delete_room, websocket_save_room


@pytest.fixture
def registration(hass, store, monkeypatch):
    registry = MagicMock()
    registry.async_get.return_value = None
    monkeypatch.setattr("custom_components.roommind.websocket_api.er.async_get", lambda _: registry)
    hass.data = {DOMAIN: {"store": store}}
    hass.states.get.return_value = SimpleNamespace(state="on", attributes={"device_class": "dehumidifier"})
    hass.services.async_call = AsyncMock()
    connection = MagicMock()
    return hass, store, connection, registry


async def save(registration, area="bed", **changes):
    hass, _, connection, _ = registration
    msg = websocket_save_room._ws_schema({"id": 1, "type": "roommind/rooms/save", "area_id": area, **changes})
    await websocket_save_room.__wrapped__(hass, connection, msg)


@pytest.mark.asyncio
async def test_registration_defaults_roundtrip_and_old_room_compatibility(registration):
    _, store, conn, _ = registration
    await store.async_load()
    await store.async_save_room("bath", {})
    await save(registration, dehumidifier={"entity_id": "switch.dryer", "served_area_ids": ["bath"]})
    conn.send_error.assert_not_called()
    room = store.get_room("bed")
    assert room["humidity_comfort_enabled"] is False
    assert room["dehumidifier"] == {
        "entity_id": "switch.dryer",
        "served_area_ids": ["bath"],
        "mode": "auto",
        "min_run_minutes": 5,
        "min_off_minutes": 5,
        "power_watts": 0,
    }
    assert store.get_room("bath")["dehumidifier"] is None
    await save(registration, display_name="Bedroom")
    assert store.get_room("bed")["dehumidifier"] == room["dehumidifier"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entity_id",
    ["climate.ac", "switch.", "humidifier.roommind_bed_dehumidification", "switch.roommind_bed_dehumidification"],
)
async def test_invalid_or_own_entity_rejected(registration, entity_id):
    _, store, conn, _ = registration
    await store.async_load()
    await save(registration, dehumidifier={"entity_id": entity_id})
    assert conn.send_error.call_args.args[1] == "invalid_dehumidifier"
    assert store.get_room("bed") is None


@pytest.mark.asyncio
async def test_renamed_roommind_entity_rejected_by_registry(registration):
    _, store, conn, registry = registration
    await store.async_load()
    registry.async_get.return_value = SimpleNamespace(platform=DOMAIN)
    await save(registration, dehumidifier={"entity_id": "humidifier.renamed"})
    assert conn.send_error.called


@pytest.mark.asyncio
async def test_humidifier_class_and_duplicate_owner_rejected(registration):
    hass, store, conn, _ = registration
    await store.async_load()
    hass.states.get.return_value = SimpleNamespace(state="off", attributes={"device_class": "humidifier"})
    await save(registration, dehumidifier={"entity_id": "humidifier.wrong"})
    assert conn.send_error.called
    conn.reset_mock()
    await save(registration, dehumidifier={"entity_id": "switch.dryer"})
    await save(registration, area="bath", dehumidifier={"entity_id": "switch.dryer"})
    assert conn.send_error.call_args.args[1] == "invalid_dehumidifier"
    assert store.get_room("bath") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("served", ["missing", "garden"])
async def test_missing_or_outdoor_beneficiary_rejected(registration, served):
    _, store, conn, _ = registration
    await store.async_load()
    await store.async_save_room("garden", {"is_outdoor": True})
    await save(registration, dehumidifier={"entity_id": "switch.dryer", "served_area_ids": [served]})
    assert conn.send_error.called


@pytest.mark.parametrize(
    "field,value", [("mode", "bogus"), ("min_off_minutes", -1), ("min_run_minutes", 1441), ("power_watts", -10)]
)
def test_invalid_settings_fail_schema(field, value):
    with pytest.raises(vol.Invalid):
        websocket_save_room._ws_schema(
            {
                "id": 1,
                "type": "roommind/rooms/save",
                "area_id": "bed",
                "dehumidifier": {"entity_id": "switch.dryer", field: value},
            }
        )


@pytest.mark.asyncio
async def test_non_finite_setting_rejected(registration):
    _, store, conn, _ = registration
    await store.async_load()
    with pytest.raises(vol.Invalid):
        await save(registration, dehumidifier={"entity_id": "switch.dryer", "power_watts": float("nan")})


def attach_coordinator(hass, *, owned=False):
    coordinator = SimpleNamespace(
        _dehumidifier_manager=DehumidifierManager(hass), async_room_added=AsyncMock(), async_room_removed=AsyncMock()
    )
    hass.data[DOMAIN]["coordinator"] = coordinator
    if owned:
        coordinator._dehumidifier_manager.runtime["switch.dryer"] = DeviceRuntime(True, 0, 0, owned_on=True)
    return coordinator


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["replace", "remove", "delete"])
@pytest.mark.parametrize("owned", [False, True])
async def test_removal_stops_only_roommind_runs(registration, operation, owned):
    hass, store, conn, _ = registration
    await store.async_load()
    await save(registration, dehumidifier={"entity_id": "switch.dryer"})
    attach_coordinator(hass, owned=owned)
    if operation == "delete":
        await websocket_delete_room.__wrapped__(hass, conn, {"id": 2, "area_id": "bed"})
        assert store.get_room("bed") is None
    else:
        await save(registration, dehumidifier={"entity_id": "switch.new"} if operation == "replace" else None)
    if owned:
        assert hass.services.async_call.call_args.args == ("switch", "turn_off", {"entity_id": "switch.dryer"})
    else:
        hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_transition_leaves_hardware_and_setpoint_untouched(registration):
    hass, store, conn, _ = registration
    await store.async_load()
    await save(registration, dehumidifier={"entity_id": "humidifier.dryer"})
    attach_coordinator(hass)
    await save(registration, dehumidifier={"entity_id": "humidifier.dryer", "mode": "manual"})
    conn.send_error.assert_not_called()
    hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_stop_preserves_old_registration(registration):
    hass, store, conn, _ = registration
    await store.async_load()
    await save(registration, dehumidifier={"entity_id": "switch.dryer"})
    attach_coordinator(hass, owned=True)
    hass.services.async_call.side_effect = RuntimeError("offline")
    await save(registration, dehumidifier=None)
    assert conn.send_error.call_args.args[1] == "device_error"
    assert store.get_room("bed")["dehumidifier"]["entity_id"] == "switch.dryer"


@pytest.mark.asyncio
async def test_delete_beneficiary_prunes_membership_without_stopping_device(registration):
    hass, store, conn, _ = registration
    await store.async_load()
    await store.async_save_room("bath", {})
    await save(registration, dehumidifier={"entity_id": "switch.dryer", "served_area_ids": ["bath"]})
    attach_coordinator(hass)
    await websocket_delete_room.__wrapped__(hass, conn, {"id": 2, "area_id": "bath"})
    assert store.get_room("bed")["dehumidifier"]["served_area_ids"] == []
    hass.services.async_call.assert_not_awaited()
