from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Energy manager refinements.
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

# Analytics forecast refinements.
p = ROOT / "custom_components/roommind/services/analytics_service.py"
text = p.read_text(encoding="utf-8")
text = text.replace(
    '    energy_manager = getattr(coordinator, "_energy_manager", None) if coordinator else None\n    if energy_manager and target_forecast:\n',
    '    energy_manager = vars(coordinator).get("_energy_manager") if coordinator and hasattr(coordinator, "__dict__") else None\n    has_power_sensors = any(\n        dev.get("type") == "ac" and dev.get("power_sensor_entity_id")\n        for dev in room_config.get("devices", [])\n    )\n    if energy_manager is not None and target_forecast and has_power_sensors:\n',
    1,
)
text = text.replace(
    '''            elif selected_mode in ("off", "fan_only"):\n                energy_mode = "idle"\n                target_for_energy = tf.get("target_temp")\n''',
    '''            elif selected_mode == "fan_only":\n                energy_mode = "fan_only"\n                target_for_energy = tf.get("target_temp")\n            elif selected_mode == "off":\n                energy_mode = "idle"\n                target_for_energy = tf.get("target_temp")\n''',
    1,
)
p.write_text(text, encoding="utf-8")
print("energy analytics refinement applied")
