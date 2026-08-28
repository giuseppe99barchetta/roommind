from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"anchor not found in {path}: {old[:80]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# Coordinator: shared room display name + energy eligibility helpers and lifecycle.
replace_once(
    "custom_components/roommind/coordinator.py",
    '''def _get_area_name(hass: HomeAssistant, area_id: str) -> str:\n    """Get human-readable area name from area registry."""\n    try:\n        area_reg = ar.async_get(hass)\n        area = area_reg.async_get_area(area_id)\n        return area.name if area else area_id\n    except Exception:  # noqa: BLE001\n        return area_id\n\n\n''',
    '''def _get_area_name(hass: HomeAssistant, area_id: str) -> str:\n    """Get human-readable area name from area registry."""\n    try:\n        area_reg = ar.async_get(hass)\n        area = area_reg.async_get_area(area_id)\n        return area.name if area else area_id\n    except Exception:  # noqa: BLE001\n        return area_id\n\n\ndef _get_room_display_name(hass: HomeAssistant, area_id: str) -> str:\n    """Return the configured room label with a user-friendly capitalized fallback."""\n    name: str | None = None\n    try:\n        store = hass.data.get(DOMAIN, {}).get("store")\n        room = store.get_room(area_id) if store else None\n        if room:\n            configured = room.get("display_name")\n            if isinstance(configured, str) and configured.strip():\n                name = configured.strip()\n    except Exception:  # noqa: BLE001\n        pass\n    if not name:\n        name = _get_area_name(hass, area_id).strip() or area_id.replace("_", " ")\n    return name[:1].upper() + name[1:]\n\n\ndef _room_has_power_sensor(room: dict) -> bool:\n    """Return whether the room has an AC with a configured consumption sensor."""\n    if room.get("is_outdoor", False):\n        return False\n    return any(\n        device.get("type") == "ac"\n        and isinstance(device.get("power_sensor_entity_id"), str)\n        and bool(device["power_sensor_entity_id"].strip())\n        for device in room.get("devices", [])\n        if isinstance(device, dict)\n    )\n\n\n''',
)
replace_once(
    "custom_components/roommind/coordinator.py",
    '''# Suffixes only valid when the room has covers configured.\nCOVER_ENTITY_SUFFIXES = ("_cover_auto", "_cover_paused")\n''',
    '''# Suffixes only valid when the room has covers configured.\nCOVER_ENTITY_SUFFIXES = ("_cover_auto", "_cover_paused")\n# Energy entities exist only when an indoor room has an AC power sensor configured.\nENERGY_ENTITY_SUFFIXES = ("_power", "_energy_today", "_predicted_power", "_predicted_energy_1h")\n''',
)
replace_once(
    "custom_components/roommind/coordinator.py",
    '''        # Track which rooms already have entity platform entities registered\n        self._entity_areas: set[str] = set()\n''',
    '''        # Track which rooms already have entity platform entities registered\n        self._entity_areas: set[str] = set()\n        self._energy_entity_areas: set[str] = set()\n''',
)
replace_once(
    "custom_components/roommind/coordinator.py",
    '''        if self._history_store is not None:\n            for area_id in rooms:\n                if not self._energy_manager.needs_bootstrap(area_id):\n                    continue\n''',
    '''        if self._history_store is not None:\n            for area_id, room in rooms.items():\n                if not _room_has_power_sensor(room):\n                    continue\n                if not self._energy_manager.needs_bootstrap(area_id):\n                    continue\n''',
)
replace_once(
    "custom_components/roommind/coordinator.py",
    '''            room = rooms.get(area_id, {})\n            if room.get("is_outdoor", False):\n                continue\n            room_state.update(self._energy_manager.update_room(area_id, room, room_state, self.outdoor_temp_effective))\n''',
    '''            room = rooms.get(area_id, {})\n            if not _room_has_power_sensor(room):\n                continue\n            room_state.update(self._energy_manager.update_room(area_id, room, room_state, self.outdoor_temp_effective))\n''',
)
replace_once(
    "custom_components/roommind/coordinator.py",
    '''        if area_id not in self._entity_areas and hasattr(self, "async_add_entities") and self.async_add_entities:\n            from .sensor import _create_room_entities\n\n            entities = _create_room_entities(self, area_id)\n            self.async_add_entities(entities)\n            self._entity_areas.add(area_id)\n\n''',
    '''        has_energy_entities = _room_has_power_sensor(room)\n        if area_id not in self._entity_areas and hasattr(self, "async_add_entities") and self.async_add_entities:\n            from .sensor import _create_room_entities\n\n            entities = _create_room_entities(self, area_id, room)\n            self.async_add_entities(entities)\n            self._entity_areas.add(area_id)\n            if has_energy_entities:\n                self._energy_entity_areas.add(area_id)\n        elif (\n            has_energy_entities\n            and area_id not in self._energy_entity_areas\n            and hasattr(self, "async_add_entities")\n            and self.async_add_entities\n        ):\n            from .sensor import _create_room_energy_entities\n\n            self.async_add_entities(_create_room_energy_entities(self, area_id))\n            self._energy_entity_areas.add(area_id)\n\n        if not has_energy_entities and area_id in self._energy_entity_areas:\n            from homeassistant.helpers import entity_registry as er\n\n            registry = er.async_get(self.hass)\n            energy_uids = {f"{DOMAIN}_{area_id}{suffix}" for suffix in ENERGY_ENTITY_SUFFIXES}\n            for entity_entry in list(registry.entities.values()):\n                if entity_entry.unique_id in energy_uids:\n                    registry.async_remove(entity_entry.entity_id)\n            self._energy_entity_areas.discard(area_id)\n            self._energy_manager.remove_room(area_id)\n\n''',
)
replace_once(
    "custom_components/roommind/coordinator.py",
    '''        self._entity_areas.discard(area_id)\n        self._mode_on_since.pop(area_id, None)\n''',
    '''        self._entity_areas.discard(area_id)\n        self._energy_entity_areas.discard(area_id)\n        self._mode_on_since.pop(area_id, None)\n''',
)
replace_once(
    "custom_components/roommind/coordinator.py",
    '''            if suffix in COVER_ENTITY_SUFFIXES and not rooms[area_id].get("covers"):\n                # Cover entity for a room without covers configured — orphaned.\n                to_remove.append(entity_entry.entity_id)\n''',
    '''            if suffix in COVER_ENTITY_SUFFIXES and not rooms[area_id].get("covers"):\n                # Cover entity for a room without covers configured — orphaned.\n                to_remove.append(entity_entry.entity_id)\n                continue\n            if suffix in ENERGY_ENTITY_SUFFIXES and not _room_has_power_sensor(rooms[area_id]):\n                # Energy sensors are invalid without an explicitly configured AC power sensor.\n                to_remove.append(entity_entry.entity_id)\n''',
)

# Sensors: split always-present and energy-only entities and use room display names.
p = ROOT / "custom_components/roommind/sensor.py"
text = p.read_text(encoding="utf-8")
text = text.replace(
    "from .coordinator import RoomMindCoordinator",
    "from .coordinator import RoomMindCoordinator, _get_room_display_name, _room_has_power_sensor",
)
old = '''def _create_room_entities(coordinator: RoomMindCoordinator, area_id: str) -> list[SensorEntity]:\n    """Create the standard set of sensor entities for a room."""\n    return [\n        RoomMindTargetTemperatureSensor(coordinator, area_id),\n        RoomMindModeSensor(coordinator, area_id),\n        RoomMindHeatSourceSensor(coordinator, area_id),\n        RoomMindHeatSourceReasonSensor(coordinator, area_id),\n        RoomMindPowerSensor(coordinator, area_id),\n        RoomMindEnergyTodaySensor(coordinator, area_id),\n        RoomMindPredictedPowerSensor(coordinator, area_id),\n        RoomMindPredictedEnergySensor(coordinator, area_id),\n    ]\n'''
new = '''def _create_room_energy_entities(coordinator: RoomMindCoordinator, area_id: str) -> list[SensorEntity]:\n    """Create sensors backed by a configured AC consumption sensor."""\n    return [\n        RoomMindPowerSensor(coordinator, area_id),\n        RoomMindEnergyTodaySensor(coordinator, area_id),\n        RoomMindPredictedPowerSensor(coordinator, area_id),\n        RoomMindPredictedEnergySensor(coordinator, area_id),\n    ]\n\n\ndef _create_room_entities(\n    coordinator: RoomMindCoordinator, area_id: str, room: dict | None = None\n) -> list[SensorEntity]:\n    """Create room sensors, adding energy entities only when they are meaningful."""\n    if room is None:\n        store = coordinator.hass.data[DOMAIN]["store"]\n        room = store.get_room(area_id) or {}\n    entities: list[SensorEntity] = [\n        RoomMindTargetTemperatureSensor(coordinator, area_id),\n        RoomMindModeSensor(coordinator, area_id),\n        RoomMindHeatSourceSensor(coordinator, area_id),\n        RoomMindHeatSourceReasonSensor(coordinator, area_id),\n    ]\n    if _room_has_power_sensor(room):\n        entities.extend(_create_room_energy_entities(coordinator, area_id))\n    return entities\n'''
if old not in text:
    raise SystemExit("sensor factory anchor not found")
text = text.replace(old, new, 1)
old = '''    for area_id in rooms:\n        entities.extend(_create_room_entities(coordinator, area_id))\n        coordinator._entity_areas.add(area_id)\n'''
new = '''    for area_id, room in rooms.items():\n        entities.extend(_create_room_entities(coordinator, area_id, room))\n        coordinator._entity_areas.add(area_id)\n        if _room_has_power_sensor(room):\n            coordinator._energy_entity_areas.add(area_id)\n'''
if old not in text:
    raise SystemExit("sensor setup anchor not found")
text = text.replace(old, new, 1)
text = text.replace('self._attr_name = f"{area_id} {name_label}"', 'self._attr_name = f"{_get_room_display_name(coordinator.hass, area_id)} {name_label}"')
p.write_text(text, encoding="utf-8")

# Human-readable room names on every per-room entity platform. Entity IDs stay stable/lowercase.
for rel in (
    "custom_components/roommind/climate.py",
    "custom_components/roommind/switch.py",
    "custom_components/roommind/binary_sensor.py",
):
    p = ROOT / rel
    text = p.read_text(encoding="utf-8")
    text = text.replace("from .coordinator import RoomMindCoordinator", "from .coordinator import RoomMindCoordinator, _get_room_display_name")
    text = text.replace('self._attr_name = f"{area_id} Override"', 'self._attr_name = f"{_get_room_display_name(coordinator.hass, area_id)} Override"')
    text = text.replace('self._attr_name = area_id', 'self._attr_name = _get_room_display_name(coordinator.hass, area_id)')
    text = text.replace('self._attr_name = f"{area_id} Cover Auto"', 'self._attr_name = f"{_get_room_display_name(coordinator.hass, area_id)} Cover Auto"')
    text = text.replace('self._attr_name = f"{area_id} Climate Control"', 'self._attr_name = f"{_get_room_display_name(coordinator.hass, area_id)} Climate Control"')
    text = text.replace('self._attr_name = f"{area_id} Cover Paused"', 'self._attr_name = f"{_get_room_display_name(coordinator.hass, area_id)} Cover Paused"')
    p.write_text(text, encoding="utf-8")

# Focused regression tests.
p = ROOT / "tests/test_sensor.py"
text = p.read_text(encoding="utf-8") if p.exists() else ""
if "test_energy_entities_require_configured_ac_power_sensor" not in text:
    text += '''\n\ndef test_energy_entities_require_configured_ac_power_sensor(mock_coordinator):\n    from custom_components.roommind.sensor import _create_room_entities\n\n    coordinator, _store = mock_coordinator\n    plain = {"area_id": "sala", "devices": [{"entity_id": "climate.ac", "type": "ac"}]}\n    measured = {\n        "area_id": "sala",\n        "devices": [\n            {\n                "entity_id": "climate.ac",\n                "type": "ac",\n                "power_sensor_entity_id": "sensor.ac_power",\n            }\n        ],\n    }\n    outdoor = {**measured, "is_outdoor": True}\n\n    assert len(_create_room_entities(coordinator, "sala", plain)) == 4\n    assert len(_create_room_entities(coordinator, "sala", measured)) == 8\n    assert len(_create_room_entities(coordinator, "terrazzo", outdoor)) == 4\n\n\ndef test_room_entity_name_uses_display_name(mock_coordinator):\n    from custom_components.roommind.sensor import RoomMindPowerSensor\n\n    coordinator, store = mock_coordinator\n    store.get_room.return_value = {"display_name": "Sala"}\n    entity = RoomMindPowerSensor(coordinator, "sala")\n    assert entity.name == "Sala AC Power"\n'''
    p.write_text(text, encoding="utf-8")

print("entity energy scoping fix applied")
