"""strings.json and translations/en.json must describe the same keys (U4)."""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent / "custom_components" / "roommind"


def _keys(data: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for key, value in data.items():
        keys |= _keys(value, f"{prefix}{key}.") if isinstance(value, dict) else {prefix + key}
    return keys


def test_en_translation_matches_strings():
    strings = json.loads((ROOT / "strings.json").read_text(encoding="utf-8"))
    english = json.loads((ROOT / "translations" / "en.json").read_text(encoding="utf-8"))
    assert _keys(english) == _keys(strings)
