from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"{path}: expected block not found: {old[:120]!r}")
    p.write_text(text.replace(old, new, count), encoding="utf-8")


# 1. Make auxiliary routing native to MPCController.async_apply.
replace(
    "custom_components/roommind/control/mpc_controller.py",
    '''        _exclude = exclude_eids or set()\n        thermostats = [e for e in self.thermostats if e not in _exclude]\n''',
    '''        _exclude = set(exclude_eids or set())\n\n        # Auxiliary AC modes are thermally idle but must not receive an\n        # intermediate OFF from the normal idle path.  Keep this routing here\n        # (rather than monkey-patching MPCController from room_climate.py) so\n        # the controller has a single explicit source of truth.\n        requested_hvac_mode = self.room_config.get("room_hvac_mode")\n        keep_fan_on_window_open = self.room_config.get("keep_fan_only_on_window_open", True)\n        auxiliary_allowed = (requested_hvac_mode == "dry" and not window_open) or (\n            requested_hvac_mode == "fan_only" and (not window_open or keep_fan_on_window_open)\n        )\n        if auxiliary_allowed:\n            _exclude.update(self.acs)\n\n        thermostats = [e for e in self.thermostats if e not in _exclude]\n''',
)
# Ensure all AC loops honour the existing exclusion set too.
text_path = Path("custom_components/roommind/control/mpc_controller.py")
text = text_path.read_text(encoding="utf-8")
text = text.replace("            for eid in self.acs:\n", "            for eid in [e for e in self.acs if e not in _exclude]:\n")
text_path.write_text(text, encoding="utf-8")

# 2. Remove monkey patch and make auxiliary mode helper explicit/stateless.
p = Path("custom_components/roommind/managers/room_climate.py")
text = p.read_text(encoding="utf-8")
start = text.index("# The coordinator intentionally keeps dry/fan_only thermally idle.")
end = text.index("\n\n@dataclass(frozen=True)", start)
text = text[:start] + text[end + 2:]
text = text.replace("from ..const import DOMAIN, make_roommind_context", "from ..const import make_roommind_context")
text = text.replace("from ..control.mpc_controller import MPCController\n", "")
old_func_start = text.index("async def async_apply_ac_auxiliary_mode")
new_func = '''async def async_apply_ac_auxiliary_mode(\n    hass: HomeAssistant,\n    room: dict,\n    *,\n    window_open: bool = False,\n) -> None:\n    \"\"\"Apply an automatic AC-only auxiliary mode after normal device idling.\"\"\"\n    acs = get_ac_eids(room.get("devices", []))\n    if not acs:\n        return\n    entity_id = acs[0]\n    mode = room.get("room_hvac_mode")\n    keep_fan_on_window_open = room.get("keep_fan_only_on_window_open", True)\n\n    if mode == "dry" and window_open:\n        return\n    if mode == "fan_only" and window_open and not keep_fan_on_window_open:\n        return\n\n    if mode in ("dry", "fan_only"):\n        await hass.services.async_call(\n            "climate",\n            "set_hvac_mode",\n            {"entity_id": entity_id, "hvac_mode": mode},\n            blocking=True,\n            context=make_roommind_context(),\n        )\n    for service, key in (\n        ("set_fan_mode", "room_fan_mode"),\n        ("set_swing_mode", "room_swing_mode"),\n        ("set_swing_horizontal_mode", "room_swing_horizontal_mode"),\n    ):\n        if room.get(key):\n            await hass.services.async_call(\n                "climate",\n                service,\n                {"entity_id": entity_id, service.removeprefix("set_"): room[key]},\n                blocking=True,\n                context=make_roommind_context(),\n            )\n'''
text = text[:old_func_start] + new_func + "\n"
p.write_text(text, encoding="utf-8")

# 3. Pass the already-debounced window state explicitly from coordinator.
replace(
    "custom_components/roommind/coordinator.py",
    "                    await async_apply_ac_auxiliary_mode(self.hass, room)\n",
    "                    await async_apply_ac_auxiliary_mode(self.hass, room, window_open=window_open)\n",
)

# 4. Canonical climate entity: manual commands are immediate and independent
#    of global/per-room automation switches.
p = Path("custom_components/roommind/climate.py")
text = p.read_text(encoding="utf-8")
text = text.replace(
    "from .managers.room_climate import room_capabilities",
    "from .control.mpc_controller import async_turn_off_climate, resolve_hvac_mode\nfrom .managers.room_climate import room_capabilities",
)
text = text.replace(
    "from .utils.device_utils import get_ac_eids",
    "from .utils.device_utils import get_ac_eids, get_all_entity_ids, get_trv_eids\nfrom .utils.temp_utils import celsius_to_ha_temp",
)
marker = '''    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:\n        if hvac_mode not in self.hvac_modes:\n            raise ValueError(f"Unsupported room HVAC mode: {hvac_mode}")\n        heat, cool = self._logical_targets()\n        mode = hvac_mode.value\n        updates = {"room_hvac_mode": mode, "override_until": None, "override_type": OVERRIDE_CUSTOM}\n        updates["override_heat"] = heat if mode in ("heat", "heat_cool", "auto") else None\n        updates["override_cool"] = cool if mode in ("cool", "heat_cool", "auto") else None\n        if mode == "off":\n            updates.update({"override_heat": None, "override_cool": None, "override_type": None})\n        await self.coordinator.hass.data[DOMAIN]["store"].async_update_room(self._area_id, updates)\n        await self.coordinator.async_request_refresh()\n'''
replacement = '''    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:\n        if hvac_mode not in self.hvac_modes:\n            raise ValueError(f"Unsupported room HVAC mode: {hvac_mode}")\n        heat, cool = self._logical_targets()\n        mode = hvac_mode.value\n        updates = {"room_hvac_mode": mode, "override_until": None, "override_type": OVERRIDE_CUSTOM}\n        updates["override_heat"] = heat if mode in ("heat", "heat_cool", "auto") else None\n        updates["override_cool"] = cool if mode in ("cool", "heat_cool", "auto") else None\n        if mode == "off":\n            updates.update({"override_heat": None, "override_cool": None, "override_type": None})\n        await self.coordinator.hass.data[DOMAIN]["store"].async_update_room(self._area_id, updates)\n\n        # This entity is also RoomMind's manual/HomeKit control surface.  Manual\n        # commands must work even when global or per-room automatic climate\n        # control is disabled; those switches govern autonomous RoomMind logic,\n        # not explicit user intent.\n        await self._async_apply_manual_hvac_mode(mode, heat, cool)\n        await self.coordinator.async_request_refresh()\n\n    async def _async_apply_manual_hvac_mode(self, mode: str, heat: float, cool: float) -> None:\n        room = self._room() or {}\n        devices = room.get("devices", [])\n        hass = self.coordinator.hass\n        acs = get_ac_eids(devices)\n        trvs = get_trv_eids(devices)\n\n        if mode == "off":\n            for entity_id in get_all_entity_ids(devices):\n                await async_turn_off_climate(hass, entity_id, area_id=self._area_id)\n            return\n\n        # TRVs only participate in heating-capable manual modes.\n        if mode in ("heat", "heat_cool", "auto"):\n            ha_heat = celsius_to_ha_temp(hass, heat)\n            for entity_id in trvs:\n                state = hass.states.get(entity_id)\n                modes = state.attributes.get("hvac_modes", []) if state else []\n                resolved = resolve_hvac_mode("heat", modes)\n                if resolved is not None:\n                    await hass.services.async_call(\n                        "climate", "set_hvac_mode",\n                        {"entity_id": entity_id, "hvac_mode": resolved},\n                        blocking=True,\n                    )\n                    await hass.services.async_call(\n                        "climate", "set_temperature",\n                        {"entity_id": entity_id, "temperature": ha_heat},\n                        blocking=True,\n                    )\n        else:\n            for entity_id in trvs:\n                await async_turn_off_climate(hass, entity_id, area_id=self._area_id)\n\n        if not acs:\n            return\n        entity_id = acs[0]\n        state = hass.states.get(entity_id)\n        supported = state.attributes.get("hvac_modes", []) if state else []\n        resolved = resolve_hvac_mode(mode, supported)\n        if resolved is None:\n            return\n        await hass.services.async_call(\n            "climate", "set_hvac_mode",\n            {"entity_id": entity_id, "hvac_mode": resolved},\n            blocking=True,\n        )\n        if mode in ("cool", "heat", "heat_cool", "auto"):\n            data = {"entity_id": entity_id}\n            if mode in ("heat_cool", "auto") and state and state.attributes.get("target_temp_low") is not None:\n                data.update(\n                    target_temp_low=celsius_to_ha_temp(hass, heat),\n                    target_temp_high=celsius_to_ha_temp(hass, cool),\n                )\n            else:\n                target = cool if mode == "cool" else heat\n                data["temperature"] = celsius_to_ha_temp(hass, target)\n            await hass.services.async_call("climate", "set_temperature", data, blocking=True)\n'''
if marker not in text:
    raise SystemExit("canonical async_set_hvac_mode block not found")
text = text.replace(marker, replacement, 1)
p.write_text(text, encoding="utf-8")

# 5. Regression tests for manual routing and native auxiliary behaviour.
p = Path("tests/test_climate.py")
text = p.read_text(encoding="utf-8")
addition = r'''

@pytest.mark.asyncio
@pytest.mark.parametrize("global_enabled,room_enabled", [(False, True), (True, False), (False, False)])
async def test_canonical_manual_fan_only_bypasses_automation_switches(
    mock_coordinator, global_enabled, room_enabled
):
    """Explicit fan-only commands remain manual even when automation is disabled."""
    coordinator, store = mock_coordinator
    room = _canonical_room(
        [{"entity_id": "climate.ac", "type": "ac"}],
        room_hvac_mode="off",
        climate_control_enabled=room_enabled,
    )
    store.get_room.return_value = room
    store.get_settings.return_value = {"climate_control_active": global_enabled}
    store.async_update_room = AsyncMock()
    coordinator.hass.states.get.return_value = MagicMock(
        state="off", attributes={"hvac_modes": ["off", "cool", "fan_only"]}
    )
    coordinator.hass.services.async_call = AsyncMock()

    await RoomMindClimate(coordinator, "living_room").async_set_hvac_mode(HVACMode.FAN_ONLY)

    coordinator.hass.services.async_call.assert_any_await(
        "climate", "set_hvac_mode", {"entity_id": "climate.ac", "hvac_mode": "fan_only"}, blocking=True
    )


@pytest.mark.asyncio
async def test_canonical_manual_cool_bypasses_global_automation_switch(mock_coordinator):
    coordinator, store = mock_coordinator
    store.get_room.return_value = _canonical_room(
        [{"entity_id": "climate.ac", "type": "ac"}],
        room_hvac_mode="off",
        climate_control_enabled=False,
    )
    store.get_settings.return_value = {"climate_control_active": False}
    store.async_update_room = AsyncMock()
    coordinator.hass.states.get.return_value = MagicMock(
        state="off", attributes={"hvac_modes": ["off", "cool", "fan_only"]}
    )
    coordinator.hass.services.async_call = AsyncMock()

    await RoomMindClimate(coordinator, "living_room").async_set_hvac_mode(HVACMode.COOL)

    coordinator.hass.services.async_call.assert_any_await(
        "climate", "set_hvac_mode", {"entity_id": "climate.ac", "hvac_mode": "cool"}, blocking=True
    )
    assert any(call.args[:2] == ("climate", "set_temperature") for call in coordinator.hass.services.async_call.await_args_list)


@pytest.mark.asyncio
async def test_canonical_manual_off_bypasses_global_automation_switch(mock_coordinator):
    coordinator, store = mock_coordinator
    store.get_room.return_value = _canonical_room(
        [{"entity_id": "climate.ac", "type": "ac"}],
        room_hvac_mode="cool",
        climate_control_enabled=False,
    )
    store.get_settings.return_value = {"climate_control_active": False}
    store.async_update_room = AsyncMock()
    coordinator.hass.states.get.return_value = MagicMock(
        state="cool", attributes={"hvac_modes": ["off", "cool", "fan_only"], "min_temp": 16}
    )
    coordinator.hass.services.async_call = AsyncMock()

    await RoomMindClimate(coordinator, "living_room").async_set_hvac_mode(HVACMode.OFF)

    coordinator.hass.services.async_call.assert_any_await(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.ac", "hvac_mode": "off"},
        blocking=True,
        context=pytest.ANY,
    )
'''
if "test_canonical_manual_fan_only_bypasses_automation_switches" not in text:
    text += addition
p.write_text(text, encoding="utf-8")

# pytest.ANY does not exist; use unittest.mock.ANY.
replace(
    "tests/test_climate.py",
    "from unittest.mock import AsyncMock, MagicMock",
    "from unittest.mock import ANY, AsyncMock, MagicMock",
)
replace("tests/test_climate.py", "context=pytest.ANY,", "context=ANY,")
