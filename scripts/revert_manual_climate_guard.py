from pathlib import Path

path = Path("custom_components/roommind/climate.py")
text = path.read_text(encoding="utf-8")
old = '''        settings = store.get_settings()\n        room = store.get_room(self._area_id) or {}\n        if not settings.get("climate_control_active", True) or not room.get("climate_control_enabled", True):\n            return\n'''
if old not in text:
    raise SystemExit("manual climate guard not found")
path.write_text(text.replace(old, "", 1), encoding="utf-8")
