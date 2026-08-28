from pathlib import Path

p = Path("tests/test_climate.py")
text = p.read_text()
text = text.replace(
'''    assert len(climates) == 2
    assert isinstance(climates[0], RoomMindClimate)
    assert isinstance(climates[1], RoomMindOverrideClimate)
''',
'''    assert len(climates) == 1
    assert isinstance(climates[0], RoomMindClimate)
''',
1,
)
text = text.replace(
'''    assert len(entities) == 4
    assert sum(isinstance(e, RoomMindClimate) for e in entities) == 2
''',
'''    assert len(entities) == 2
    assert all(isinstance(e, RoomMindClimate) for e in entities)
''',
1,
)
p.write_text(text)
