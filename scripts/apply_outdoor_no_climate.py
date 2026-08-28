from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# climate.py: skip outdoor rooms during platform startup.
p = ROOT / "custom_components/roommind/climate.py"
text = p.read_text(encoding="utf-8")
old = '''    for area_id in rooms:\n        entities.extend(_create_room_climates(coordinator, area_id))\n        coordinator._climate_entity_areas.add(area_id)\n'''
new = '''    for area_id, room in rooms.items():\n        if room.get("is_outdoor", False):\n            continue\n        entities.extend(_create_room_climates(coordinator, area_id))\n        coordinator._climate_entity_areas.add(area_id)\n'''
if old not in text:
    raise SystemExit("climate startup anchor not found")
p.write_text(text.replace(old, new, 1), encoding="utf-8")

# coordinator.py: don't create climate dynamically for outdoor rooms, remove an
# existing canonical climate if a room is converted to outdoor, and cleanup
# stale outdoor climates on startup.
p = ROOT / "custom_components/roommind/coordinator.py"
text = p.read_text(encoding="utf-8")
old = '''        # Canonical room climate entity: always create\n        if (\n            area_id not in self._climate_entity_areas\n            and hasattr(self, "async_add_climate_entities")\n            and self.async_add_climate_entities\n        ):\n            from .climate import _create_room_climates\n\n            self.async_add_climate_entities(_create_room_climates(self, area_id))\n            self._climate_entity_areas.add(area_id)\n'''
new = '''        # Outdoor areas are sensor/analytics-only and must never expose a\n        # canonical climate entity. If an existing room is converted to outdoor,\n        # remove its previously registered climate immediately.\n        if room.get("is_outdoor", False):\n            from homeassistant.helpers import entity_registry as er\n\n            registry = er.async_get(self.hass)\n            climate_uid = f"{DOMAIN}_{area_id}"\n            for entity_entry in list(registry.entities.values()):\n                if entity_entry.unique_id == climate_uid:\n                    registry.async_remove(entity_entry.entity_id)\n            self._climate_entity_areas.discard(area_id)\n        elif (\n            area_id not in self._climate_entity_areas\n            and hasattr(self, "async_add_climate_entities")\n            and self.async_add_climate_entities\n        ):\n            from .climate import _create_room_climates\n\n            self.async_add_climate_entities(_create_room_climates(self, area_id))\n            self._climate_entity_areas.add(area_id)\n'''
if old not in text:
    raise SystemExit("dynamic climate anchor not found")
text = text.replace(old, new, 1)
old = '''            area_id, suffix = match\n            if suffix in COVER_ENTITY_SUFFIXES and not rooms[area_id].get("covers"):\n'''
new = '''            area_id, suffix = match\n            if suffix == "" and rooms[area_id].get("is_outdoor", False):\n                # Canonical climate is invalid for outdoor areas.\n                to_remove.append(entity_entry.entity_id)\n                continue\n            if suffix in COVER_ENTITY_SUFFIXES and not rooms[area_id].get("covers"):\n'''
if old not in text:
    raise SystemExit("cleanup anchor not found")
p.write_text(text.replace(old, new, 1), encoding="utf-8")

# Tests.
p = ROOT / "tests/test_climate.py"
text = p.read_text(encoding="utf-8")
insert = '''\n\n@pytest.mark.asyncio\nasync def test_setup_skips_outdoor_room(mock_coordinator):\n    coordinator, store = mock_coordinator\n    store.get_rooms.return_value = {\n        "living_room": {"is_outdoor": False},\n        "terrace": {"is_outdoor": True},\n    }\n    coordinator.hass.data[DOMAIN]["entry"] = coordinator\n    entry = MagicMock(entry_id="entry")\n    add_entities = MagicMock()\n\n    await async_setup_entry(coordinator.hass, entry, add_entities)\n\n    created = add_entities.call_args.args[0]\n    assert [entity._area_id for entity in created] == ["living_room"]\n    assert coordinator._climate_entity_areas == {"living_room"}\n'''
anchor = '\n\ndef _canonical_room(devices, **overrides):\n'
if anchor not in text:
    raise SystemExit("test climate anchor not found")
text = text.replace(anchor, insert + anchor, 1)
p.write_text(text, encoding="utf-8")

p = ROOT / "tests/coordinator/test_entity_cleanup.py"
text = p.read_text(encoding="utf-8")
text += '''\n\ndef test_cleanup_removes_canonical_climate_for_outdoor_room(hass, mock_config_entry):\n    from homeassistant.helpers import entity_registry as er\n\n    coordinator = _create_coordinator(hass, mock_config_entry)\n    store = MagicMock()\n    store.get_rooms.return_value = {"terrace": {"area_id": "terrace", "is_outdoor": True}}\n    hass.data = {DOMAIN: {"store": store}}\n    registry = er.async_get(hass)\n    registry.async_get_or_create("climate", DOMAIN, f"{DOMAIN}_terrace", suggested_object_id="roommind_terrace")\n\n    coordinator.cleanup_orphaned_entities()\n\n    assert registry.async_get("climate.roommind_terrace") is None\n'''
p.write_text(text, encoding="utf-8")

print("outdoor climate exclusion applied")
