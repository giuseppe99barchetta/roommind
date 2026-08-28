from pathlib import Path
import json

for locale in ("en", "de", "fr"):
    path = Path(f"frontend/src/locales/{locale}.json")
    data = json.loads(path.read_text())
    nested = data.pop("settings", None)
    if isinstance(nested, dict):
        for key, value in nested.items():
            data[f"settings.{key}"] = value
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")

print("temperature rounding locale keys flattened")
