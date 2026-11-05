"""Schema and range validation of the configuration websocket commands (B2, B3, B5)."""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest
import voluptuous as vol

from custom_components.roommind.const import DOMAIN
from custom_components.roommind.websocket_api import (
    websocket_override_set,
    websocket_save_room,
    websocket_save_settings,
)

_save_room = inspect.unwrap(websocket_save_room)


def _room(**fields):
    return websocket_save_room._ws_schema({"id": 1, "type": "roommind/rooms/save", "area_id": "x", **fields})


def _settings(**fields):
    return websocket_save_settings._ws_schema({"id": 1, "type": "roommind/settings/save", **fields})


def _override(**fields):
    return websocket_override_set._ws_schema(
        {"id": 1, "type": "roommind/override/set", "area_id": "x", "override_type": "custom", **fields}
    )


# --- non-finite numbers --------------------------------------------------------


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", float("nan"), float("inf")])
@pytest.mark.parametrize(
    ("build", "field"),
    [
        (_room, "comfort_heat"),
        (_room, "covers_deploy_threshold"),
        (_room, "humidity_target"),
        (_settings, "comfort_weight"),
        (_settings, "vacation_until"),
        (_settings, "outdoor_cooling_min"),
        (_override, "heat"),
        (_override, "duration"),
    ],
)
def test_non_finite_numbers_rejected(build, field, value):
    with pytest.raises(vol.Invalid):
        build(**{field: value})


# --- ranges ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "bad", "good"),
    [
        ("comfort_heat", 4, 5),
        ("comfort_cool", 36, 35),
        ("eco_heat", -50, 15),
        ("eco_cool", 99, 28),
        ("logical_heat_target", 2, 20),
        ("logical_cool_target", 40, 26),
        ("comfort_temp", 50, 21),
        ("eco_temp", 0, 17),
    ],
)
def test_room_ranges(field, bad, good):
    with pytest.raises(vol.Invalid):
        _room(**{field: bad})
    assert _room(**{field: good})[field] == good


@pytest.mark.parametrize(
    ("field", "bad", "good"),
    [
        ("comfort_weight", -5, 100),
        ("vacation_temp", 99, 15),
        ("vacation_until", -1, 0),
        ("outdoor_heating_max", -40, 22),
        ("outdoor_cooling_min", 60, 16),
    ],
)
def test_settings_ranges(field, bad, good):
    with pytest.raises(vol.Invalid):
        _settings(**{field: bad})
    assert _settings(**{field: good})[field] == good


def test_settings_vacation_until_none_still_clears():
    assert _settings(vacation_until=None)["vacation_until"] is None


@pytest.mark.parametrize(("field", "bad"), [("heat", 500), ("cool", 2), ("duration", -5)])
def test_override_ranges_rejected(field, bad):
    with pytest.raises(vol.Invalid):
        _override(**{field: bad})


@pytest.mark.parametrize("duration", [0, 2.5, None])
def test_override_duration_zero_omitted_and_positive_accepted(duration):
    fields = {"heat": 21} if duration is None else {"heat": 21, "duration": duration}
    assert _override(**fields).get("duration") == duration


# --- comfort profiles (B2) -------------------------------------------------------


def test_comfort_profiles_valid_payload_accepted():
    profiles = {
        "work": {"heat_target": 21, "cool_target": 25, "humidity_target": 55, "fan_mode": "auto", "label": "Work"},
        "away": {"heat_target": 16.5},
    }
    out = _room(comfort_profiles=profiles)["comfort_profiles"]
    assert out["work"]["heat_target"] == 21.0
    assert out["away"] == {"heat_target": 16.5}


@pytest.mark.parametrize(
    "profiles",
    [
        {"work": {"heat_target": "abc"}},
        {"work": {"heat_target": "nan"}},
        {"work": {"cool_target": 50}},
        {"work": {"humidity_target": 95}},
        {"party": {"heat_target": 21}},
        {"work": "warm"},
    ],
)
def test_comfort_profiles_invalid_payload_rejected(profiles):
    with pytest.raises(vol.Invalid):
        _room(comfort_profiles=profiles)


# --- climate entity domains (B5, review R10) -------------------------------------


@pytest.mark.parametrize("field", ["thermostats", "acs"])
def test_legacy_arrays_reject_non_climate_entities(field):
    with pytest.raises(vol.Invalid):
        _room(**{field: ["switch.heater"]})
    assert _room(**{field: ["climate.living"]})[field] == ["climate.living"]


def test_devices_reject_non_climate_entities():
    with pytest.raises(vol.Invalid):
        _room(devices=[{"entity_id": "lock.front_door", "type": "trv"}])
    assert _room(devices=[{"entity_id": "climate.trv", "type": "trv"}])["devices"][0]["entity_id"] == "climate.trv"


@pytest.mark.parametrize(
    ("field", "raw", "stored"), [("window_open_delay", -999, 0), ("window_close_delay", 7200, 3600)]
)
def test_window_delays_are_clamped(field, raw, stored):
    """Clamp rather than reject: older configs may hold delays above the new UI limit."""
    assert _room(**{field: raw})[field] == stored


def test_repro_payload_rejected():
    """The payload from the code review repro is no longer accepted."""
    with pytest.raises(vol.Invalid):
        _room(
            comfort_heat=30,
            comfort_cool=18,
            eco_heat=-50,
            window_open_delay=-999,
            active_profile="work",
            comfort_profiles={"work": {"heat_target": "abc"}},
            devices=[{"entity_id": "lock.front_door", "type": "trv"}],
        )


# --- heat/cool ordering on room save ----------------------------------------------


@pytest.fixture
def ws_hass(hass, store):
    hass.data[DOMAIN] = {"store": store}
    return hass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        {"comfort_heat": 24, "comfort_cool": 22},
        {"eco_heat": 20, "eco_cool": 18},
        {"logical_heat_target": 25, "logical_cool_target": 21},
    ],
)
async def test_save_room_rejects_cool_below_heat(ws_hass, store, fields):
    await store.async_load()
    conn = MagicMock()
    await _save_room(ws_hass, conn, {"id": 1, "area_id": "living", **fields})
    conn.send_error.assert_called_once()
    assert conn.send_error.call_args.args[1] == "invalid"
    assert store.get_room("living") is None


@pytest.mark.asyncio
async def test_save_room_rejects_partial_update_that_inverts_stored_pair(ws_hass, store):
    await store.async_load()
    conn = MagicMock()
    await _save_room(ws_hass, conn, {"id": 1, "area_id": "living", "comfort_heat": 21, "comfort_cool": 24})
    conn.send_result.assert_called_once()
    conn = MagicMock()
    await _save_room(ws_hass, conn, {"id": 2, "area_id": "living", "comfort_cool": 20})
    conn.send_error.assert_called_once()
    assert store.get_room("living")["comfort_cool"] == 24


@pytest.mark.asyncio
async def test_save_room_accepts_equal_heat_and_cool(ws_hass, store):
    await store.async_load()
    conn = MagicMock()
    await _save_room(ws_hass, conn, {"id": 1, "area_id": "living", "comfort_heat": 22, "comfort_cool": 22})
    conn.send_error.assert_not_called()
    conn.send_result.assert_called_once()


# --- legacy comfort_temp/eco_temp aliases (D1, review R11) -------------------------


async def _save(ws_hass, msg_id, area_id, **fields):
    conn = MagicMock()
    await _save_room(ws_hass, conn, {"id": msg_id, "area_id": area_id, **fields})
    conn.send_error.assert_not_called()
    return conn.send_result.call_args.args[1]["room"]


@pytest.mark.asyncio
async def test_legacy_aliases_set_canonical_fields_on_create(ws_hass, store):
    await store.async_load()
    await _save(ws_hass, 1, "living", comfort_temp=22.5, eco_temp=16.5)

    saved = store._store.async_save.call_args.args[0]["rooms"]["living"]
    assert saved["comfort_heat"] == 22.5
    assert saved["eco_heat"] == 16.5
    assert "comfort_temp" not in saved
    assert "eco_temp" not in saved


@pytest.mark.asyncio
async def test_legacy_aliases_update_canonical_fields(ws_hass, store):
    """Replaces the store-level eco_temp→eco_heat reverse-sync test."""
    await store.async_load()
    await _save(ws_hass, 1, "living", comfort_heat=21.0, comfort_cool=24.0)
    await _save(ws_hass, 2, "living", eco_temp=18.5)
    await _save(ws_hass, 3, "living", comfort_temp=22.0)

    room = store.get_room("living")
    assert room["eco_heat"] == 18.5
    assert room["comfort_heat"] == 22.0


@pytest.mark.asyncio
async def test_canonical_fields_win_over_legacy_aliases(ws_hass, store):
    await store.async_load()
    await _save(ws_hass, 1, "living", comfort_heat=22.0, comfort_temp=25.0, eco_heat=16.0, eco_temp=19.0)

    room = store.get_room("living")
    assert room["comfort_heat"] == 22.0
    assert room["eco_heat"] == 16.0


@pytest.mark.asyncio
async def test_new_room_does_not_store_legacy_temps(ws_hass, store):
    await store.async_load()
    room = await _save(ws_hass, 1, "living", comfort_heat=21.5)

    assert room["comfort_heat"] == 21.5
    assert "comfort_temp" not in room
    assert "eco_temp" not in room
