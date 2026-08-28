from pathlib import Path
import sys

p = Path(__file__).resolve().parents[1] / "frontend/src/locales/en.json"
text = p.read_text(encoding="utf-8")
marker = '    "temperature": "Temperature",\n'
if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
    text = text.replace(marker, "", 1)
else:
    anchor = '  "analytics.temperature": "Temperature",\n'
    if marker not in text:
        if anchor not in text:
            raise SystemExit("analytics.temperature locale anchor missing")
        text = text.replace(anchor, anchor + marker, 1)
p.write_text(text, encoding="utf-8")
