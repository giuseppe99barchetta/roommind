from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"anchor not found in {path}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "custom_components/roommind/climate.py",
    '''    @property\n    def current_temperature(self) -> float | None:\n        """Return the room's current temperature from coordinator data."""\n        data = self.coordinator.data\n        if not data:\n            return None\n        room_data = data.get("rooms", {}).get(self._area_id)\n        if not room_data:\n            return None\n        val = room_data.get("current_temp")\n        return float(val) if isinstance(val, (int, float)) else None\n\n''',
    '''    @property\n    def current_temperature(self) -> float | None:\n        """Return the room's current temperature from coordinator data."""\n        data = self.coordinator.data\n        if not data:\n            return None\n        room_data = data.get("rooms", {}).get(self._area_id)\n        if not room_data:\n            return None\n        val = room_data.get("current_temp")\n        return float(val) if isinstance(val, (int, float)) else None\n\n    @property\n    def current_humidity(self) -> float | None:\n        """Return the room's current relative humidity from coordinator data."""\n        data = self.coordinator.data\n        if not data:\n            return None\n        room_data = data.get("rooms", {}).get(self._area_id)\n        if not room_data:\n            return None\n        val = room_data.get("current_humidity")\n        return float(val) if isinstance(val, (int, float)) else None\n\n''',
)

p = ROOT / "tests/test_climate.py"
text = p.read_text(encoding="utf-8")
anchor = '''def test_current_temperature_from_coordinator_data(mock_coordinator):\n    """current_temperature reads from coordinator.data."""\n'''
idx = text.find(anchor)
if idx < 0:
    raise SystemExit("test anchor not found")
test = '''def test_current_humidity_from_coordinator_data(mock_coordinator):\n    """current_humidity reads the room humidity from coordinator data."""\n    coordinator, store = mock_coordinator\n    store.get_room.return_value = {"override_heat": None, "override_cool": None}\n    coordinator.data = {"rooms": {"living_room": {"current_humidity": 58.7}}}\n    entity = RoomMindClimate(coordinator, "living_room")\n    assert entity.current_humidity == 58.7\n\n\ndef test_current_humidity_missing_or_invalid_returns_none(mock_coordinator):\n    coordinator, store = mock_coordinator\n    store.get_room.return_value = {"override_heat": None, "override_cool": None}\n    entity = RoomMindClimate(coordinator, "living_room")\n\n    coordinator.data = {"rooms": {"living_room": {}}}\n    assert entity.current_humidity is None\n\n    coordinator.data = {"rooms": {"living_room": {"current_humidity": "unknown"}}}\n    assert entity.current_humidity is None\n\n\n'''
if "test_current_humidity_from_coordinator_data" not in text:
    text = text[:idx] + test + text[idx:]
p.write_text(text, encoding="utf-8")

print("current humidity support applied")
