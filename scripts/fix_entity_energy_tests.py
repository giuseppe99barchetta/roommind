from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Existing tests must reflect that energy sensors are conditional, not universal.
p = ROOT / "tests/test_sensor.py"
text = p.read_text(encoding="utf-8")
text = text.replace(
    '''    assert len(room_entities) == 8\n    assert any(isinstance(e, RoomMindPowerSensor) for e in room_entities)\n    assert any(isinstance(e, RoomMindEnergyTodaySensor) for e in room_entities)\n''',
    '''    assert len(room_entities) == 4\n    assert not any(isinstance(e, RoomMindPowerSensor) for e in room_entities)\n    assert not any(isinstance(e, RoomMindEnergyTodaySensor) for e in room_entities)\n''',
    1,
)
text = text.replace(
    '''    assert sum(getattr(e, "_area_id", None) in {"room_a", "room_b"} for e in entities) == 16\n''',
    '''    assert sum(getattr(e, "_area_id", None) in {"room_a", "room_b"} for e in entities) == 8\n''',
    1,
)
text = text.replace(
    '''    assert len(entities) == 8\n    assert isinstance(entities[0], RoomMindTargetTemperatureSensor)\n    assert isinstance(entities[1], RoomMindModeSensor)\n    assert any(isinstance(e, RoomMindPowerSensor) for e in entities)\n    assert any(isinstance(e, RoomMindEnergyTodaySensor) for e in entities)\n    assert any(isinstance(e, RoomMindPredictedPowerSensor) for e in entities)\n    assert any(isinstance(e, RoomMindPredictedEnergySensor) for e in entities)\n''',
    '''    assert len(entities) == 4\n    assert isinstance(entities[0], RoomMindTargetTemperatureSensor)\n    assert isinstance(entities[1], RoomMindModeSensor)\n    assert not any(isinstance(e, RoomMindPowerSensor) for e in entities)\n    assert not any(isinstance(e, RoomMindEnergyTodaySensor) for e in entities)\n    assert not any(isinstance(e, RoomMindPredictedPowerSensor) for e in entities)\n    assert not any(isinstance(e, RoomMindPredictedEnergySensor) for e in entities)\n''',
    1,
)
old = '''def test_energy_entities_require_configured_ac_power_sensor(mock_coordinator):\n    from custom_components.roommind.sensor import _create_room_entities\n\n    coordinator, _store = mock_coordinator\n    plain = {"area_id": "sala", "devices": [{"entity_id": "climate.ac", "type": "ac"}]}\n    measured = {\n        "area_id": "sala",\n        "devices": [\n            {\n                "entity_id": "climate.ac",\n                "type": "ac",\n                "power_sensor_entity_id": "sensor.ac_power",\n            }\n        ],\n    }\n    outdoor = {**measured, "is_outdoor": True}\n\n    assert len(_create_room_entities(coordinator, "sala", plain)) == 4\n    assert len(_create_room_entities(coordinator, "sala", measured)) == 8\n    assert len(_create_room_entities(coordinator, "terrazzo", outdoor)) == 4\n\n\ndef test_room_entity_name_uses_display_name(mock_coordinator):\n    from custom_components.roommind.sensor import RoomMindPowerSensor\n\n    coordinator, store = mock_coordinator\n    store.get_room.return_value = {"display_name": "Sala"}\n    entity = RoomMindPowerSensor(coordinator, "sala")\n    assert entity.name == "Sala AC Power"\n'''
new = '''def test_energy_entities_require_configured_ac_power_sensor():\n    coordinator = _make_coordinator()\n    plain = {"area_id": "sala", "devices": [{"entity_id": "climate.ac", "type": "ac"}]}\n    measured = {\n        "area_id": "sala",\n        "devices": [\n            {\n                "entity_id": "climate.ac",\n                "type": "ac",\n                "power_sensor_entity_id": "sensor.ac_power",\n            }\n        ],\n    }\n    outdoor = {**measured, "is_outdoor": True}\n\n    assert len(_create_room_entities(coordinator, "sala", plain)) == 4\n    assert len(_create_room_entities(coordinator, "sala", measured)) == 8\n    assert len(_create_room_entities(coordinator, "terrazzo", outdoor)) == 4\n\n\ndef test_room_entity_name_uses_display_name():\n    coordinator = _make_coordinator()\n    store = MagicMock()\n    store.get_room.return_value = {"display_name": "Sala"}\n    coordinator.hass.data = {DOMAIN: {"store": store}}\n\n    entity = RoomMindPowerSensor(coordinator, "sala")\n\n    assert entity._attr_name == "Sala AC Power"\n'''
if old not in text:
    raise SystemExit("generated regression test anchor not found")
text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")

p = ROOT / "tests/coordinator/test_update_cycle.py"
text = p.read_text(encoding="utf-8")
old = '''        assert len(entities) == 8\n'''
if old not in text:
    raise SystemExit("coordinator entity-count assertion not found")
text = text.replace(old, '''        assert len(entities) == 4\n''', 1)
p.write_text(text, encoding="utf-8")

print("entity energy scoping tests aligned")
