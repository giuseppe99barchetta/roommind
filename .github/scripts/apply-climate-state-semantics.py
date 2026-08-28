from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"pattern not found in {path}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1))

# Expose one logical automatic mode. Physically the system is always either
# heating, cooling or idle; AUTO is the user intent that lets RoomMind choose.
replace(
    "custom_components/roommind/managers/room_climate.py",
    '''    if can_heat and can_cool:\n        modes.append("heat_cool")\n    if "auto" in ac_modes:\n        modes.append("auto")\n''',
    '''    if can_heat and can_cool:\n        modes.append("auto")\n''',
)

# Canonical entity: migrate legacy heat_cool intent to AUTO and only report
# auxiliary AC modes while the physical AC is actually in that mode.
replace(
    "custom_components/roommind/climate.py",
    '''    @property\n    def hvac_mode(self) -> HVACMode:\n        room = self._room() or {}\n        selected = room.get("room_hvac_mode")\n        if selected in self._capabilities().hvac_modes:\n            return HVACMode(selected)\n        # Existing users retain automatic RoomMind control without needing a\n        # migration write; capability rather than member state is authoritative.\n        return HVACMode.HEAT_COOL if HVACMode.HEAT_COOL in self.hvac_modes else self.hvac_modes[0]\n''',
    '''    def _physical_ac_mode(self) -> str | None:\n        acs = get_ac_eids((self._room() or {}).get("devices", []))\n        if not acs:\n            return None\n        state = self.coordinator.hass.states.get(acs[0])\n        return state.state if state is not None else None\n\n    @property\n    def hvac_mode(self) -> HVACMode:\n        room = self._room() or {}\n        selected = room.get("room_hvac_mode")\n        # Backward compatibility for rooms persisted before AUTO replaced the\n        # misleading HEAT_COOL label on the canonical entity.\n        if selected == "heat_cool":\n            selected = "auto"\n\n        # FAN_ONLY and DRY are direct physical AC modes, not autonomous RoomMind\n        # control states. A persisted value must never make an AC that is really\n        # off look active after restart or an external power-off.\n        if selected in ("fan_only", "dry"):\n            return HVACMode(selected) if self._physical_ac_mode() == selected else HVACMode.OFF\n\n        if selected in self._capabilities().hvac_modes:\n            return HVACMode(selected)\n        # A configured room starts in logical AUTO when both directions are\n        # available; AUTO means RoomMind may choose heat/cool, not that either is\n        # currently running.\n        return HVACMode.AUTO if HVACMode.AUTO in self.hvac_modes else self.hvac_modes[0]\n''',
)

# AUTO is now the only automatic dual-direction mode in the canonical entity.
replace(
    "custom_components/roommind/climate.py",
    'if mode in (HVACMode.HEAT_COOL, HVACMode.AUTO, HVACMode.HEAT, HVACMode.COOL, HVACMode.DRY):',
    'if mode in (HVACMode.AUTO, HVACMode.HEAT, HVACMode.COOL, HVACMode.DRY):',
)
replace(
    "custom_components/roommind/climate.py",
    'if mode in (HVACMode.HEAT_COOL, HVACMode.AUTO):\n            return (heat + cool) / 2.0',
    'if mode == HVACMode.AUTO:\n            return (heat + cool) / 2.0',
)
replace(
    "custom_components/roommind/climate.py",
    'if selected in (HVACMode.HEAT_COOL, HVACMode.AUTO):',
    'if selected == HVACMode.AUTO:',
)

# Do not directly power both heating and cooling hardware when the user chooses
# AUTO. Persist the intent, then let the coordinator choose one direction.
replace(
    "custom_components/roommind/climate.py",
    '''        await self.coordinator.hass.data[DOMAIN]["store"].async_update_room(self._area_id, updates)\n\n        # This entity is also RoomMind's manual/HomeKit control surface.  Manual\n        # commands must work even when global or per-room automatic climate\n        # control is disabled; those switches govern autonomous RoomMind logic,\n        # not explicit user intent.\n        await self._async_apply_manual_hvac_mode(mode, heat, cool)\n        await self.coordinator.async_request_refresh()\n''',
    '''        await self.coordinator.hass.data[DOMAIN]["store"].async_update_room(self._area_id, updates)\n\n        # Explicit HEAT/COOL/OFF/FAN_ONLY/DRY are direct manual commands. AUTO\n        # is different: it is permission for RoomMind to choose one direction,\n        # so it must never directly switch both heating and cooling hardware on.\n        if mode != "auto":\n            await self._async_apply_manual_hvac_mode(mode, heat, cool)\n        await self.coordinator.async_request_refresh()\n''',
)

# Legacy HEAT_COOL callers are accepted as AUTO, but it is no longer exposed.
replace(
    "custom_components/roommind/climate.py",
    '''    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:\n        if hvac_mode not in self.hvac_modes:\n            raise ValueError(f"Unsupported room HVAC mode: {hvac_mode}")\n        heat, cool = self._logical_targets()\n        mode = hvac_mode.value\n''',
    '''    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:\n        if hvac_mode == HVACMode.HEAT_COOL and HVACMode.AUTO in self.hvac_modes:\n            hvac_mode = HVACMode.AUTO\n        if hvac_mode not in self.hvac_modes:\n            raise ValueError(f"Unsupported room HVAC mode: {hvac_mode}")\n        heat, cool = self._logical_targets()\n        mode = hvac_mode.value\n''',
)

# Turn-on should prefer AUTO, not the old HEAT_COOL label.
replace(
    "custom_components/roommind/climate.py",
    'fallback = HVACMode.HEAT_COOL if HVACMode.HEAT_COOL in self.hvac_modes else HVACMode.HEAT',
    'fallback = HVACMode.AUTO if HVACMode.AUTO in self.hvac_modes else HVACMode.HEAT',
)

# Tests: update expected automatic mode and add physical-state regression tests.
p = Path("tests/test_climate.py")
text = p.read_text()
text = text.replace('{"off", "heat", "cool", "heat_cool", "dry", "fan_only"}', '{"off", "heat", "cool", "auto", "dry", "fan_only"}')
text = text.replace('room_hvac_mode="heat_cool"', 'room_hvac_mode="auto"')
text = text.replace('assert written["room_hvac_mode"] == "heat_cool"', 'assert written["room_hvac_mode"] == "auto"')
text = text.replace(
    '''    for mode in ("heat", "cool", "dry"):\n        store.get_room.return_value = _canonical_room(''',
    '''    for mode in ("heat", "cool", "dry"):\n        ac.state = "dry" if mode == "dry" else "cool"\n        store.get_room.return_value = _canonical_room(''',
)
text = text.replace('assert entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE\n    assert not entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE\n    assert entity.target_temperature_low == 21.0\n    assert entity.target_temperature_high == 26.0', 'assert entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE\n    assert not entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE\n    assert entity.target_temperature == 23.5\n    assert entity.target_temperature_low is None\n    assert entity.target_temperature_high is None')

append = r'''\n\ndef test_canonical_persisted_fan_only_reports_off_when_physical_ac_is_off(mock_coordinator):\n    coordinator, store = mock_coordinator\n    ac = MagicMock(state="off", attributes={"hvac_modes": ["off", "cool", "dry", "fan_only"]})\n    coordinator.hass.states.get.return_value = ac\n    store.get_room.return_value = _canonical_room(\n        [{"entity_id": "climate.ac", "type": "ac"}], room_hvac_mode="fan_only"\n    )\n    entity = RoomMindClimate(coordinator, "living_room")\n\n    assert entity.hvac_mode == HVACMode.OFF\n    assert entity.hvac_action is None\n\n\ndef test_canonical_persisted_dry_reports_off_when_physical_ac_is_off(mock_coordinator):\n    coordinator, store = mock_coordinator\n    ac = MagicMock(state="off", attributes={"hvac_modes": ["off", "cool", "dry", "fan_only"]})\n    coordinator.hass.states.get.return_value = ac\n    store.get_room.return_value = _canonical_room(\n        [{"entity_id": "climate.ac", "type": "ac"}], room_hvac_mode="dry"\n    )\n    entity = RoomMindClimate(coordinator, "living_room")\n\n    assert entity.hvac_mode == HVACMode.OFF\n    assert entity.hvac_action is None\n\n\ndef test_canonical_legacy_heat_cool_is_exposed_as_auto(mock_coordinator):\n    coordinator, store = mock_coordinator\n    ac = MagicMock(state="off", attributes={"hvac_modes": ["off", "heat", "cool", "fan_only"]})\n    coordinator.hass.states.get.return_value = ac\n    store.get_room.return_value = _canonical_room(\n        [{"entity_id": "climate.ac", "type": "ac"}], room_hvac_mode="heat_cool"\n    )\n    entity = RoomMindClimate(coordinator, "living_room")\n\n    assert HVACMode.AUTO in entity.hvac_modes\n    assert HVACMode.HEAT_COOL not in entity.hvac_modes\n    assert entity.hvac_mode == HVACMode.AUTO\n'''
if 'test_canonical_persisted_fan_only_reports_off_when_physical_ac_is_off' not in text:
    text += append
p.write_text(text)
