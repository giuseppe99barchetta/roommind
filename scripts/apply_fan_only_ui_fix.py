from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"anchor not found in {path}: {old[:160]!r}")
    p.write_text(text.replace(old, new, 1))


replace_once(
    "custom_components/roommind/climate.py",
    '''    @property\n    def target_temperature(self) -> float | None:\n        heat, cool = self._logical_targets()\n        return cool if self.hvac_mode in (HVACMode.COOL, HVACMode.DRY) else heat\n''',
    '''    @property\n    def target_temperature(self) -> float | None:\n        mode = self.hvac_mode\n        if mode in (HVACMode.OFF, HVACMode.FAN_ONLY):\n            return None\n        heat, cool = self._logical_targets()\n        return cool if mode in (HVACMode.COOL, HVACMode.DRY) else heat\n''',
)

p = Path("tests/test_climate.py")
text = p.read_text()
marker = '''def test_canonical_trv_only_does_not_expose_ac_modes(mock_coordinator):\n'''
if marker not in text:
    raise SystemExit("test insertion marker not found")
block = '''def test_canonical_fan_only_and_off_hide_single_temperature_target(mock_coordinator):\n    \"\"\"Modes without a thermal setpoint must not expose one in the HA climate card.\"\"\"\n    coordinator, store = mock_coordinator\n    ac = MagicMock(\n        state=\"fan_only\",\n        attributes={\"hvac_modes\": [\"off\", \"cool\", \"dry\", \"fan_only\"]},\n    )\n    coordinator.hass.states.get.return_value = ac\n    room = _canonical_room(\n        [{\"entity_id\": \"climate.ac\", \"type\": \"ac\"}],\n        logical_heat_target=19.3,\n        logical_cool_target=26.0,\n        room_hvac_mode=\"fan_only\",\n    )\n    store.get_room.return_value = room\n    entity = RoomMindClimate(coordinator, \"living_room\")\n\n    assert entity.target_temperature is None\n\n    room[\"room_hvac_mode\"] = \"off\"\n    assert entity.target_temperature is None\n\n    room[\"room_hvac_mode\"] = \"cool\"\n    assert entity.target_temperature == 26.0\n\n\n'''
p.write_text(text.replace(marker, block + marker, 1))
