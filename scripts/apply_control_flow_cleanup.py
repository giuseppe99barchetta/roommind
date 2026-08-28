from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise RuntimeError(f"pattern not found in {path}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1))


# ---------------------------------------------------------------------------
# climate.py: canonical entity only + manual safety + multi-AC
# ---------------------------------------------------------------------------
p = Path("custom_components/roommind/climate.py")
text = p.read_text()
text = text.replace("    is_override_active,\n", "")
text = text.replace(
    '    return [RoomMindClimate(coordinator, area_id), RoomMindOverrideClimate(coordinator, area_id)]',
    '    return [RoomMindClimate(coordinator, area_id)]',
)
start = text.index("class RoomMindOverrideClimate")
end = text.index("class RoomMindClimate")
text = text[:start] + text[end:]
text = text.replace(
    "class RoomMindClimate(RoomMindOverrideClimate):",
    "class RoomMindClimate(CoordinatorEntity, ClimateEntity):",
)
needle = '''    def _capabilities(self) -> RoomClimateCapabilities:\n        return room_capabilities(self.coordinator.hass, self._room() or {})\n'''
insert = '''    def _room(self) -> dict | None:\n        store = self.coordinator.hass.data[DOMAIN]["store"]\n        return store.get_room(self._area_id)\n\n    @property\n    def current_temperature(self) -> float | None:\n        data = self.coordinator.data\n        if not data:\n            return None\n        room_data = data.get("rooms", {}).get(self._area_id)\n        if not room_data:\n            return None\n        val = room_data.get("current_temp")\n        return float(val) if isinstance(val, (int, float)) else None\n\n    def _capabilities(self) -> RoomClimateCapabilities:\n        return room_capabilities(self.coordinator.hass, self._room() or {})\n'''
if needle not in text:
    raise RuntimeError("climate capabilities insertion point missing")
text = text.replace(needle, insert, 1)
text = text.replace(
'''    def _physical_ac_mode(self) -> str | None:\n        acs = get_ac_eids((self._room() or {}).get("devices", []))\n        if not acs:\n            return None\n        state = self.coordinator.hass.states.get(acs[0])\n        return state.state if state is not None else None\n''',
'''    def _physical_ac_modes(self) -> tuple[str, ...]:\n        modes: list[str] = []\n        for entity_id in get_ac_eids((self._room() or {}).get("devices", [])):\n            state = self.coordinator.hass.states.get(entity_id)\n            if state is not None and state.state not in ("unknown", "unavailable"):\n                modes.append(state.state)\n        return tuple(modes)\n''',
1,
)
text = text.replace(
'            return HVACMode(selected) if self._physical_ac_mode() == selected else HVACMode.OFF',
'            return HVACMode(selected) if selected in self._physical_ac_modes() else HVACMode.OFF',
1,
)

# Add a common guard before direct hardware activation.
needle = '''    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:\n'''
guard = '''    def _manual_activation_guard(self, mode: str) -> None:\n        """Apply hard safety guards to explicit manual heat/cool/dry activation.\n\n        Manual commands intentionally bypass schedules, presence, windows and MPC\n        policy, but they must not bypass compressor minimum-off or the configured\n        electrical power budget. OFF and FAN_ONLY are always allowed.\n        """\n        if mode not in ("heat", "cool", "dry"):\n            return\n        room = self._room() or {}\n        hass = self.coordinator.hass\n        acs = get_ac_eids(room.get("devices", []))\n        if not acs:\n            return\n        store = hass.data[DOMAIN]["store"]\n        settings = store.get_settings()\n\n        compressor = self.coordinator._compressor_manager\n        compressor.load_groups(settings.get("compressor_groups", []))\n        for entity_id in acs:\n            state = hass.states.get(entity_id)\n            already_running = bool(\n                state and state.state not in ("off", "unknown", "unavailable", "fan_only")\n            )\n            if not already_running and not compressor.check_can_activate(entity_id):\n                raise ValueError(f"Compressor minimum-off protection blocks {entity_id}")\n\n        if not settings.get("power_budget_enabled", False):\n            return\n        running_loads: dict[str, float] = {}\n        for area_id, other in store.get_rooms().items():\n            other_acs = get_ac_eids(other.get("devices", []))\n            if any(\n                (st := hass.states.get(eid))\n                and st.state not in ("off", "unknown", "unavailable", "fan_only")\n                for eid in other_acs\n            ):\n                running_loads[area_id] = float(other.get("heat_pump_power_watts", 0) or 0)\n        budget = self.coordinator._power_budget_manager\n        budget.begin_cycle(hass, settings, running_loads)\n        already_running_room = self._area_id in running_loads\n        if not budget.request_heat_pump(\n            self._area_id,\n            float(room.get("heat_pump_power_watts", 0) or 0),\n            already_running_room,\n        ):\n            raise ValueError("RoomMind power budget blocks this climate activation")\n\n    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:\n'''
if needle not in text:
    raise RuntimeError("async_set_hvac_mode insertion point missing")
text = text.replace(needle, guard, 1)

old = '''        await self.coordinator.hass.data[DOMAIN]["store"].async_update_room(self._area_id, updates)\n\n        # Explicit HEAT/COOL/OFF/FAN_ONLY/DRY are direct manual commands. AUTO\n        # is different: it is permission for RoomMind to choose one direction,\n        # so it must never directly switch both heating and cooling hardware on.\n        if mode != "auto":\n            await self._async_apply_manual_hvac_mode(mode, heat, cool)\n        await self.coordinator.async_request_refresh()\n'''
new = '''        # Explicit HEAT/COOL/OFF/FAN_ONLY/DRY are direct manual commands. AUTO\n        # is different: it is permission for RoomMind to choose one direction,\n        # so it must never directly switch both heating and cooling hardware on.\n        # Validate hard safety before persisting a mode that could not be applied.\n        if mode != "auto":\n            self._manual_activation_guard(mode)\n            await self._async_apply_manual_hvac_mode(mode, heat, cool)\n        await self.coordinator.hass.data[DOMAIN]["store"].async_update_room(self._area_id, updates)\n        await self.coordinator.async_request_refresh()\n'''
if old not in text:
    raise RuntimeError("manual HVAC mode block missing")
text = text.replace(old, new, 1)

# Guard direct temperature changes too: some integrations wake a device on set_temperature.
old = '''        # A setpoint changed through the canonical entity is an explicit user\n        # command (HA/HomeKit). Persisting it is not enough: forward it to the\n        # physical device that is currently responsible for that direction.\n        await self._async_apply_manual_temperature(selected, heat, cool)\n'''
new = '''        # A setpoint changed through the canonical entity is an explicit user\n        # command (HA/HomeKit). Persisting it is not enough: forward it to the\n        # physical device that is currently responsible for that direction.\n        if selected in (HVACMode.HEAT, HVACMode.COOL, HVACMode.DRY):\n            self._manual_activation_guard(selected.value)\n        await self._async_apply_manual_temperature(selected, heat, cool)\n'''
if old not in text:
    raise RuntimeError("manual temperature comment block missing")
text = text.replace(old, new, 1)

# Apply manual HVAC mode to every AC, not only acs[0], and keep compressor state in sync.
old_start = '''        if not acs:\n            return\n        entity_id = acs[0]\n        state = hass.states.get(entity_id)\n        supported = state.attributes.get("hvac_modes", []) if state else []\n        resolved = resolve_hvac_mode(mode, supported)\n        if resolved is None:\n            return\n        await hass.services.async_call(\n            "climate",\n            "set_hvac_mode",\n            {"entity_id": entity_id, "hvac_mode": resolved},\n            blocking=True,\n        )\n        if mode in ("cool", "heat", "heat_cool", "auto"):\n            data: dict[str, Any] = {"entity_id": entity_id}\n            if mode in ("heat_cool", "auto") and state and state.attributes.get("target_temp_low") is not None:\n                data.update(\n                    target_temp_low=quantize_temperature_for_entity(\n                        hass, entity_id, celsius_to_ha_temp(hass, heat), fallback_step=1.0\n                    ),\n                    target_temp_high=quantize_temperature_for_entity(\n                        hass, entity_id, celsius_to_ha_temp(hass, cool), fallback_step=1.0\n                    ),\n                )\n            else:\n                target = cool if mode == "cool" else heat\n                data["temperature"] = quantize_temperature_for_entity(\n                    hass, entity_id, celsius_to_ha_temp(hass, target), fallback_step=1.0\n                )\n            await hass.services.async_call("climate", "set_temperature", data, blocking=True)\n'''
new_start = '''        if not acs:\n            return\n        compressor = self.coordinator._compressor_manager\n        for entity_id in acs:\n            state = hass.states.get(entity_id)\n            supported = state.attributes.get("hvac_modes", []) if state else []\n            resolved = resolve_hvac_mode(mode, supported)\n            if resolved is None:\n                continue\n            await hass.services.async_call(\n                "climate",\n                "set_hvac_mode",\n                {"entity_id": entity_id, "hvac_mode": resolved},\n                blocking=True,\n            )\n            if mode in ("cool", "heat", "heat_cool", "auto"):\n                data: dict[str, Any] = {"entity_id": entity_id}\n                if mode in ("heat_cool", "auto") and state and state.attributes.get("target_temp_low") is not None:\n                    data.update(\n                        target_temp_low=quantize_temperature_for_entity(\n                            hass, entity_id, celsius_to_ha_temp(hass, heat), fallback_step=1.0\n                        ),\n                        target_temp_high=quantize_temperature_for_entity(\n                            hass, entity_id, celsius_to_ha_temp(hass, cool), fallback_step=1.0\n                        ),\n                    )\n                else:\n                    target = cool if mode == "cool" else heat\n                    data["temperature"] = quantize_temperature_for_entity(\n                        hass, entity_id, celsius_to_ha_temp(hass, target), fallback_step=1.0\n                    )\n                await hass.services.async_call("climate", "set_temperature", data, blocking=True)\n            compressor.update_member(entity_id, mode in ("heat", "cool", "dry"))\n'''
if old_start not in text:
    raise RuntimeError("single AC manual block missing")
text = text.replace(old_start, new_start, 1)

# OFF must update compressor tracking after the explicit user shutdown.
text = text.replace(
'''        if mode == "off":\n            for entity_id in get_all_entity_ids(devices):\n                await async_turn_off_climate(hass, entity_id, area_id=self._area_id)\n            return\n''',
'''        if mode == "off":\n            for entity_id in get_all_entity_ids(devices):\n                await async_turn_off_climate(hass, entity_id, area_id=self._area_id)\n                self.coordinator._compressor_manager.update_member(entity_id, False)\n            return\n''',
1,
)

# Fan/swing options should be applied consistently to all configured ACs.
old = '''        store = self.coordinator.hass.data[DOMAIN]["store"]\n        await store.async_update_room(self._area_id, {key: value})\n        await self.coordinator.hass.services.async_call(\n            "climate", service, {"entity_id": acs[0], service_key: value}, blocking=True\n        )\n'''
new = '''        store = self.coordinator.hass.data[DOMAIN]["store"]\n        await store.async_update_room(self._area_id, {key: value})\n        for entity_id in acs:\n            await self.coordinator.hass.services.async_call(\n                "climate", service, {"entity_id": entity_id, service_key: value}, blocking=True\n            )\n'''
if old not in text:
    raise RuntimeError("single AC option block missing")
text = text.replace(old, new, 1)
p.write_text(text)

# ---------------------------------------------------------------------------
# coordinator.py: remove override entity, manual mode wins over mold prevention
# ---------------------------------------------------------------------------
replace(
    "custom_components/roommind/coordinator.py",
    '    "_override",\n',
    '',
)
replace(
    "custom_components/roommind/coordinator.py",
    '# Climate entities (override control): always create',
    '# Canonical room climate entity: always create',
)
old = '''        # Apply mold prevention temperature delta (heating target only).\n        # Safety: mold prevention overrides "off" to prevent structural damage.\n        force_off = targets.heat is None and targets.cool is None or requested_hvac_mode in ("off", "dry", "fan_only")\n        if mold_prevention_active_room and mold_prevention_temp_delta > 0:\n            if force_off:\n                eco_heat = room.get("eco_heat", room.get("eco_temp", DEFAULT_ECO_HEAT))\n                eco_cool = room.get("eco_cool", DEFAULT_ECO_COOL)\n                targets = TargetTemps(\n                    heat=eco_heat + mold_prevention_temp_delta,\n                    cool=eco_cool,\n                )\n                force_off = False\n            elif targets.heat is not None:\n                targets = TargetTemps(\n                    heat=targets.heat + mold_prevention_temp_delta,\n                    cool=targets.cool,\n                )\n'''
new = '''        # Apply mold prevention only while RoomMind owns thermal control.\n        # An explicit manual OFF/FAN_ONLY/DRY command is authoritative and must\n        # never be silently replaced by autonomous heating. The mold risk level\n        # remains visible, but prevention is reported active only when applied.\n        manual_aux_or_off = requested_hvac_mode in ("off", "dry", "fan_only")\n        force_off = targets.heat is None and targets.cool is None or manual_aux_or_off\n        mold_prevention_effective = bool(\n            mold_prevention_active_room and mold_prevention_temp_delta > 0 and not manual_aux_or_off\n        )\n        if mold_prevention_effective and targets.heat is not None:\n            targets = TargetTemps(\n                heat=targets.heat + mold_prevention_temp_delta,\n                cool=targets.cool,\n            )\n        mold_prevention_active_room = mold_prevention_effective\n'''
replace("custom_components/roommind/coordinator.py", old, new)

# ---------------------------------------------------------------------------
# Boiler: disabled master means zero demand, not abandoning the state machine.
# ---------------------------------------------------------------------------
replace(
    "custom_components/roommind/managers/boiler_manager.py",
'''        if not settings.get("climate_control_active", True):\n            return\n        self.demand_rooms = set(demand_rooms)\n''',
'''        if not settings.get("climate_control_active", True):\n            demand_rooms = set()\n        self.demand_rooms = set(demand_rooms)\n''',
)
replace(
    "custom_components/roommind/managers/boiler_manager.py",
'''            if not demand:\n                self.state, self._state_since = BoilerState.OFF, now\n''',
'''            if not demand:\n                await self._set_boiler(settings, False)\n                await self._set_bypass(settings, False)\n                self.path_safe = False\n                self.state, self._state_since = BoilerState.OFF, now\n''',
)

# ---------------------------------------------------------------------------
# Valve protection: disabling climate control must finish active cycles safely.
# ---------------------------------------------------------------------------
replace(
    "custom_components/roommind/managers/valve_manager.py",
'''        store = self.hass.data.get(DOMAIN, {}).get("store")\n        if store is not None and not store.get_settings().get("climate_control_active", True):\n            return\n        if not self._cycling:\n            return\n''',
'''        store = self.hass.data.get(DOMAIN, {}).get("store")\n        if not self._cycling:\n            return\n        if store is not None and not store.get_settings().get("climate_control_active", True):\n            now = time.time()\n            for eid in list(self._cycling):\n                await self._async_close_valve(eid, rooms_devices, log_context="because climate control was disabled")\n                self._cycling.pop(eid, None)\n                self._last_actuation[eid] = now\n                self._actuation_dirty = True\n            return\n''',
)

# ---------------------------------------------------------------------------
# MPC final actuator: use global rounding even if target_temp_step is absent.
# ---------------------------------------------------------------------------
replace(
    "custom_components/roommind/control/mpc_controller.py",
'''        if service == "set_temperature" and state:\n            step = state.attributes.get("target_temp_step")\n            if step is not None:\n                step = float(step)\n''',
'''        if service == "set_temperature" and state:\n            fallback_step = 1.0 if eid in self.acs else (0.5 if eid in self.thermostats else None)\n            raw_step = state.attributes.get("target_temp_step", fallback_step)\n            step = float(raw_step) if raw_step is not None else None\n            if step is not None:\n''',
)

# ---------------------------------------------------------------------------
# Tests: focused regression coverage for the changed semantics.
# ---------------------------------------------------------------------------
Path("tests/test_control_flow_cleanup.py").write_text(r'''from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.climate import RoomMindClimate, _create_room_climates
from custom_components.roommind.managers.boiler_manager import BoilerManager, BoilerState
from custom_components.roommind.managers.valve_manager import ValveManager


def test_only_canonical_climate_is_created():
    coordinator = MagicMock()
    climates = _create_room_climates(coordinator, "studio")
    assert len(climates) == 1
    assert isinstance(climates[0], RoomMindClimate)


@pytest.mark.asyncio
async def test_boiler_master_off_does_not_abandon_running_boiler():
    hass = MagicMock()
    hass.states.get.return_value = SimpleNamespace(state="heat")
    hass.services.async_call = AsyncMock()
    manager = BoilerManager(hass)
    manager.state = BoilerState.ON
    manager.path_safe = True
    manager._set_bypass = AsyncMock(return_value=True)
    manager._set_boiler = AsyncMock(return_value=True)

    await manager.async_reconcile(
        {
            "climate_control_active": False,
            "boiler_entity": "climate.boiler",
            "boiler_shutdown_delay_seconds": 60,
        },
        {"studio"},
    )

    manager._set_boiler.assert_awaited_with(
        {
            "climate_control_active": False,
            "boiler_entity": "climate.boiler",
            "boiler_shutdown_delay_seconds": 60,
        },
        False,
    )
    assert manager.state == BoilerState.POSTSTOP
    assert manager.demand_rooms == set()


@pytest.mark.asyncio
async def test_valve_cycle_is_closed_when_master_is_disabled():
    hass = MagicMock()
    store = MagicMock()
    store.get_settings.return_value = {"climate_control_active": False}
    hass.data = {"roommind": {"store": store}}
    manager = ValveManager(hass)
    manager._cycling = {"climate.trv": 1.0}
    manager._async_close_valve = AsyncMock()

    await manager.async_finish_cycles({"climate.trv": []})

    manager._async_close_valve.assert_awaited_once()
    assert manager._cycling == {}
    assert manager.actuation_dirty is True
''')
