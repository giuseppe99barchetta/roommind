from pathlib import Path

root = Path(__file__).resolve().parents[1]

# The first patch intentionally inserted a parenthesized conditional after an
# f-string. Add the missing concatenation before formatting/linting.
p = root / "custom_components/roommind/managers/mold_manager.py"
text = p.read_text(encoding="utf-8")
old = '                                f"Mold prevention active in {area_name}: "\n                                (\n'
new = '                                f"Mold prevention active in {area_name}: "\n                                + (\n'
if old not in text:
    raise SystemExit("mold notification anchor not found")
p.write_text(text.replace(old, new, 1), encoding="utf-8")

# The correction script originally carried a broader version of the same fix.
# It is unnecessary after the exact normalization above; remove that first
# replace block from the temporary working copy before executing it.
p = root / "scripts/apply_energy_mold_v2_corrections.py"
text = p.read_text(encoding="utf-8")
start = text.index('replace(\n    "custom_components/roommind/managers/mold_manager.py",')
end = text.index("# Coordinator remembers only", start)
text = text[:start] + text[end:]
p.write_text(text, encoding="utf-8")
