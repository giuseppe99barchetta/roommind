from pathlib import Path
import json
import runpy

runpy.run_path("scripts/apply_climate_hotfix_v2.py", run_name="__main__")

# RoomMind locale files use flat dotted keys, not nested JSON objects.
for locale in ("en", "de", "fr"):
    path = Path(f"frontend/src/locales/{locale}.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    nested = data.pop("devices", {})
    if nested:
        data["devices.keep_fan_only_window"] = nested["keep_fan_only_window"]
        data["devices.keep_fan_only_window_hint"] = nested["keep_fan_only_window_hint"]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
