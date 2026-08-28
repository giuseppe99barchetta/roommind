from pathlib import Path

climate_path = Path('custom_components/roommind/climate.py')
text = climate_path.read_text()

text = text.replace(
'''        if mode in (HVACMode.HEAT_COOL, HVACMode.AUTO):\n            features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE\n        elif mode in (HVACMode.HEAT, HVACMode.COOL, HVACMode.DRY):\n            features |= ClimateEntityFeature.TARGET_TEMPERATURE\n''',
'''        if mode in (HVACMode.HEAT_COOL, HVACMode.AUTO, HVACMode.HEAT, HVACMode.COOL, HVACMode.DRY):\n            features |= ClimateEntityFeature.TARGET_TEMPERATURE\n''')

text = text.replace(
'''        heat, cool = self._logical_targets()\n        return cool if mode in (HVACMode.COOL, HVACMode.DRY) else heat\n\n    @property\n    def target_temperature_low(self) -> float | None:\n        if self.hvac_mode not in (HVACMode.HEAT_COOL, HVACMode.AUTO):\n            return None\n        return self._logical_targets()[0]\n\n    @property\n    def target_temperature_high(self) -> float | None:\n        if self.hvac_mode not in (HVACMode.HEAT_COOL, HVACMode.AUTO):\n            return None\n        return self._logical_targets()[1]\n''',
'''        heat, cool = self._logical_targets()\n        if mode in (HVACMode.HEAT_COOL, HVACMode.AUTO):\n            return (heat + cool) / 2.0\n        return cool if mode in (HVACMode.COOL, HVACMode.DRY) else heat\n\n    @property\n    def target_temperature_low(self) -> float | None:\n        return None\n\n    @property\n    def target_temperature_high(self) -> float | None:\n        return None\n''')

old = '''        if low is not None or high is not None:\n            heat = float(low if low is not None else heat)\n            cool = float(high if high is not None else cool)\n        elif single is not None:\n            if selected in (HVACMode.COOL, HVACMode.DRY):\n                cool = float(single)\n            else:\n                heat = float(single)\n        else:\n            return\n'''
new = '''        if selected in (HVACMode.HEAT_COOL, HVACMode.AUTO):\n            if single is not None:\n                center = float(single)\n            elif low is not None or high is not None:\n                effective_low = float(low if low is not None else heat)\n                effective_high = float(high if high is not None else cool)\n                if effective_high < effective_low:\n                    raise ValueError("Cooling target must be >= heating target")\n                center = (effective_low + effective_high) / 2.0\n            else:\n                return\n            # The canonical RoomMind climate exposes one user-facing setpoint.\n            # Internally keep a 2 °C neutral band to avoid heat/cool cycling.\n            heat = center - 1.0\n            cool = center + 1.0\n        else:\n            if single is None:\n                single = high if selected in (HVACMode.COOL, HVACMode.DRY) else low\n            if single is None:\n                return\n            if selected in (HVACMode.COOL, HVACMode.DRY):\n                cool = float(single)\n            else:\n                heat = float(single)\n'''
if old not in text:
    raise SystemExit('async_set_temperature block not found')
text = text.replace(old, new)
climate_path.write_text(text)

test_path = Path('tests/test_climate.py')
tests = test_path.read_text()
old_test = '''    store.get_room.return_value = _canonical_room(\n        [{"entity_id": "climate.ac", "type": "ac"}], room_hvac_mode="heat_cool"\n    )\n    entity = RoomMindClimate(coordinator, "living_room")\n    assert entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE\n    assert not entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE\n    assert entity.target_temperature_low == 21.0\n    assert entity.target_temperature_high == 26.0\n'''
new_test = '''    store.get_room.return_value = _canonical_room(\n        [{"entity_id": "climate.ac", "type": "ac"}], room_hvac_mode="heat_cool"\n    )\n    entity = RoomMindClimate(coordinator, "living_room")\n    assert entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE\n    assert not entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE\n    assert entity.target_temperature == 23.5\n    assert entity.target_temperature_low is None\n    assert entity.target_temperature_high is None\n'''
if old_test not in tests:
    raise SystemExit('mode-specific test block not found')
tests = tests.replace(old_test, new_test)

append = '''\n\n@pytest.mark.asyncio\nasync def test_canonical_heat_cool_single_setpoint_creates_two_degree_deadband(mock_coordinator):\n    coordinator, store = mock_coordinator\n    ac = MagicMock(\n        state="off",\n        attributes={"hvac_modes": ["off", "heat", "cool", "heat_cool"]},\n    )\n    coordinator.hass.states.get.return_value = ac\n    store.get_room.return_value = _canonical_room(\n        [{"entity_id": "climate.ac", "type": "ac"}],\n        room_hvac_mode="heat_cool",\n        logical_heat_target=21.0,\n        logical_cool_target=25.0,\n    )\n    store.async_update_room = AsyncMock()\n    entity = RoomMindClimate(coordinator, "living_room")\n\n    await entity.async_set_temperature(temperature=23.0)\n\n    written = store.async_update_room.await_args[0][1]\n    assert written["logical_heat_target"] == 22.0\n    assert written["logical_cool_target"] == 24.0\n    assert written["override_heat"] == 22.0\n    assert written["override_cool"] == 24.0\n    assert written["room_hvac_mode"] == "heat_cool"\n\n\ndef test_canonical_heat_cool_target_is_midpoint_for_homekit(mock_coordinator):\n    coordinator, store = mock_coordinator\n    ac = MagicMock(\n        state="off",\n        attributes={"hvac_modes": ["off", "heat", "cool", "heat_cool"]},\n    )\n    coordinator.hass.states.get.return_value = ac\n    store.get_room.return_value = _canonical_room(\n        [{"entity_id": "climate.ac", "type": "ac"}],\n        room_hvac_mode="heat_cool",\n        logical_heat_target=22.0,\n        logical_cool_target=24.0,\n    )\n    entity = RoomMindClimate(coordinator, "living_room")\n\n    assert entity.target_temperature == 23.0\n    assert entity.target_temperature_low is None\n    assert entity.target_temperature_high is None\n    assert entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE\n    assert not entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE\n'''
if 'test_canonical_heat_cool_single_setpoint_creates_two_degree_deadband' not in tests:
    tests += append

test_path.write_text(tests)
