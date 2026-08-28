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

# Frontend analytics type: expose learning sample count to the chart.
p = ROOT / "frontend/src/types/index.ts"
text = p.read_text(encoding="utf-8")
idx = text.find("export interface AnalyticsDataPoint")
if idx < 0:
    raise SystemExit("AnalyticsDataPoint interface missing")
head, tail = text[:idx], text[idx:]
if "energy_learning_samples?: number | null;" not in tail:
    anchor = "  predicted_power_w?: number | null;\n"
    if anchor not in tail:
        raise SystemExit("AnalyticsDataPoint predicted_power_w anchor missing")
    tail = tail.replace(anchor, anchor + "  energy_learning_samples?: number | null;\n", 1)
p.write_text(head + tail, encoding="utf-8")

# Locales: TranslationKey is derived from en.json, so the new keys must exist
# in English at compile time. Add localized values to all shipped languages.
locale_values = {
    "en": {
        "analytics.energy_title": "Energy consumption",
        "analytics.energy_subtitle": "Measured device power and learned forecast",
        "analytics.energy_room_power": "Room power",
        "analytics.energy_forecast": "Forecast",
        "analytics.energy_forecast_short": "Forecast",
        "analytics.energy_now": "Now",
        "analytics.energy_period": "Period energy",
        "analytics.energy_next_3h": "Next 3 hours",
        "analytics.energy_learning": "Learning samples",
    },
    "de": {
        "analytics.energy_title": "Energieverbrauch",
        "analytics.energy_subtitle": "Gemessene Geräteleistung und gelernte Prognose",
        "analytics.energy_room_power": "Raumleistung",
        "analytics.energy_forecast": "Prognose",
        "analytics.energy_forecast_short": "Prognose",
        "analytics.energy_now": "Jetzt",
        "analytics.energy_period": "Energie im Zeitraum",
        "analytics.energy_next_3h": "Nächste 3 Stunden",
        "analytics.energy_learning": "Lernmesswerte",
    },
    "fr": {
        "analytics.energy_title": "Consommation d’énergie",
        "analytics.energy_subtitle": "Puissance mesurée des appareils et prévision apprise",
        "analytics.energy_room_power": "Puissance de la pièce",
        "analytics.energy_forecast": "Prévision",
        "analytics.energy_forecast_short": "Prévision",
        "analytics.energy_now": "Maintenant",
        "analytics.energy_period": "Énergie sur la période",
        "analytics.energy_next_3h": "3 prochaines heures",
        "analytics.energy_learning": "Échantillons d’apprentissage",
    },
}
for lang, values in locale_values.items():
    p = ROOT / f"frontend/src/locales/{lang}.json"
    text = p.read_text(encoding="utf-8")
    missing = [(key, value) for key, value in values.items() if f'"{key}"' not in text]
    if missing:
        pos = text.rfind("\n}")
        if pos < 0:
            raise SystemExit(f"invalid locale JSON: {lang}")
        prefix = ",\n" if text[:pos].rstrip().endswith('"') else "\n"
        additions = ",\n".join(
            f'  "{key}": "{value.replace(chr(34), chr(92) + chr(34))}"' for key, value in missing
        )
        text = text[:pos].rstrip() + prefix + additions + text[pos:]
        p.write_text(text, encoding="utf-8")

print("energy analytics refinement applied")
