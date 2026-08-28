from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"anchor not found in {path}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1))


replace_once(
    "custom_components/roommind/climate.py",
    '''    @property\n    def supported_features(self) -> ClimateEntityFeature:\n        caps = self._capabilities()\n        features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF\n        if "heat_cool" in caps.hvac_modes or "auto" in caps.hvac_modes:\n            features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE\n        if any(mode in caps.hvac_modes for mode in ("heat", "cool")):\n            features |= ClimateEntityFeature.TARGET_TEMPERATURE\n        if caps.fan_modes:\n            features |= ClimateEntityFeature.FAN_MODE\n        if caps.swing_modes:\n            features |= ClimateEntityFeature.SWING_MODE\n        if caps.swing_horizontal_modes:\n            features |= ClimateEntityFeature.SWING_HORIZONTAL_MODE\n        return features\n''',
    '''    @property\n    def supported_features(self) -> ClimateEntityFeature:\n        caps = self._capabilities()\n        mode = self.hvac_mode\n        features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF\n\n        # Temperature controls must describe the currently selected operating\n        # mode, not every capability the room happens to have. In particular,\n        # OFF and FAN_ONLY have no meaningful temperature setpoint.\n        if mode in (HVACMode.HEAT_COOL, HVACMode.AUTO):\n            features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE\n        elif mode in (HVACMode.HEAT, HVACMode.COOL, HVACMode.DRY):\n            features |= ClimateEntityFeature.TARGET_TEMPERATURE\n\n        if caps.fan_modes:\n            features |= ClimateEntityFeature.FAN_MODE\n        if caps.swing_modes:\n            features |= ClimateEntityFeature.SWING_MODE\n        if caps.swing_horizontal_modes:\n            features |= ClimateEntityFeature.SWING_HORIZONTAL_MODE\n        return features\n''',
)

replace_once(
    "custom_components/roommind/climate.py",
    '''    @property\n    def target_temperature_low(self) -> float | None:\n        return self._logical_targets()[0]\n\n    @property\n    def target_temperature_high(self) -> float | None:\n        return self._logical_targets()[1]\n''',
    '''    @property\n    def target_temperature_low(self) -> float | None:\n        if self.hvac_mode not in (HVACMode.HEAT_COOL, HVACMode.AUTO):\n            return None\n        return self._logical_targets()[0]\n\n    @property\n    def target_temperature_high(self) -> float | None:\n        if self.hvac_mode not in (HVACMode.HEAT_COOL, HVACMode.AUTO):\n            return None\n        return self._logical_targets()[1]\n''',
)

replace_once(
    "custom_components/roommind/climate.py",
    '''    async def async_set_temperature(self, **kwargs: Any) -> None:\n        heat, cool = self._logical_targets()\n''',
    '''    async def async_set_temperature(self, **kwargs: Any) -> None:\n        selected = self.hvac_mode\n        if selected in (HVACMode.OFF, HVACMode.FAN_ONLY):\n            raise ValueError(f"Temperature cannot be set while RoomMind is in {selected.value} mode")\n\n        heat, cool = self._logical_targets()\n''',
)

replace_once(
    "custom_components/roommind/climate.py",
    '''        selected = self.hvac_mode\n        if low is not None or high is not None:\n''',
    '''        if low is not None or high is not None:\n''',
)

p = Path("tests/test_climate.py")
text = p.read_text()
marker = "\ndef test_canonical_trv_only_does_not_expose_ac_modes"
if marker not in text:
    raise SystemExit("test insertion marker not found")
block = r'''

def test_canonical_fan_only_hides_all_temperature_controls(mock_coordinator):
    coordinator, store = mock_coordinator
    ac = MagicMock(
        state="fan_only",
        attributes={"hvac_modes": ["off", "cool", "dry", "fan_only"], "fan_modes": ["low", "high"]},
    )
    coordinator.hass.states.get.return_value = ac
    store.get_room.return_value = _canonical_room(
        [{"entity_id": "climate.ac", "type": "ac"}],
        room_hvac_mode="fan_only",
        logical_heat_target=19.3,
        logical_cool_target=26.0,
    )
    entity = RoomMindClimate(coordinator, "living_room")

    assert entity.target_temperature is None
    assert entity.target_temperature_low is None
    assert entity.target_temperature_high is None
    assert not entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE
    assert not entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    assert entity.supported_features & ClimateEntityFeature.FAN_MODE


def test_canonical_mode_specific_temperature_features(mock_coordinator):
    coordinator, store = mock_coordinator
    ac = MagicMock(
        state="cool",
        attributes={"hvac_modes": ["off", "heat", "cool", "heat_cool", "dry", "fan_only"]},
    )
    coordinator.hass.states.get.return_value = ac

    for mode in ("heat", "cool", "dry"):
        store.get_room.return_value = _canonical_room(
            [{"entity_id": "climate.ac", "type": "ac"}], room_hvac_mode=mode
        )
        entity = RoomMindClimate(coordinator, "living_room")
        assert entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE
        assert not entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        assert entity.target_temperature_low is None
        assert entity.target_temperature_high is None

    store.get_room.return_value = _canonical_room(
        [{"entity_id": "climate.ac", "type": "ac"}], room_hvac_mode="heat_cool"
    )
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    assert not entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE
    assert entity.target_temperature_low == 21.0
    assert entity.target_temperature_high == 26.0


@pytest.mark.asyncio
async def test_canonical_fan_only_rejects_temperature_changes(mock_coordinator):
    coordinator, store = mock_coordinator
    coordinator.hass.states.get.return_value = MagicMock(
        state="fan_only",
        attributes={"hvac_modes": ["off", "cool", "fan_only"]},
    )
    store.get_room.return_value = _canonical_room(
        [{"entity_id": "climate.ac", "type": "ac"}], room_hvac_mode="fan_only"
    )
    store.async_update_room = AsyncMock()
    entity = RoomMindClimate(coordinator, "living_room")

    with pytest.raises(ValueError, match="fan_only"):
        await entity.async_set_temperature(temperature=23.0)
    store.async_update_room.assert_not_awaited()

'''
p.write_text(text.replace(marker, block + marker, 1))
