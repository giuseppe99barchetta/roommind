from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
p = ROOT / "custom_components/roommind/managers/energy_manager.py"
text = p.read_text(encoding="utf-8")
text = text.replace(
    'if prediction is None and mode in ("heating", "cooling", "dry") and nominal_w and nominal_w > 0:',
    'if prediction is None and mode in ("heating", "cooling", "dry", "fan_only") and nominal_w and nominal_w > 0:',
)
old = '''        for entity_id, models in state.device_models.items():
            prediction, _ = self._predict_stats(models.get(mode), features)
            if prediction is not None:
                result[entity_id] = round(prediction, 1)
'''
new = '''        for entity_id, models in state.device_models.items():
            model = models.get(mode)
            prediction, _ = self._predict_stats(model, features)
            # Before ridge regression has enough usable samples, keep analytics
            # useful with a conservative observed-power fallback. The learned
            # model replaces this automatically once coefficients are available.
            if prediction is None and model is not None and model.n > 0:
                prediction = model.observed_max_w
            if prediction is not None:
                result[entity_id] = round(prediction, 1)
'''
if old not in text:
    raise SystemExit("predict_device_power anchor missing")
text = text.replace(old, new, 1)
text = text.replace('mode in ("heating", "cooling", "dry")', 'mode in ("heating", "cooling", "dry", "fan_only")')
p.write_text(text, encoding="utf-8")
print("energy analytics refinement applied")
