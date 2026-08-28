from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"pattern not found in {path}: {old[:120]!r}")
    p.write_text(text.replace(old, new, count))


def append_once(path: str, marker: str, text_to_append: str) -> None:
    p = Path(path)
    text = p.read_text()
    if marker not in text:
        p.write_text(text + text_to_append)


# ---------------------------------------------------------------------------
# Backend temperature quantization helpers
# ---------------------------------------------------------------------------
p = Path("custom_components/roommind/utils/temp_utils.py")
text = p.read_text()
text = text.replace("from homeassistant.core import HomeAssistant\n", "from homeassistant.core import HomeAssistant\n\nfrom ..const import DOMAIN\n")
append = '''\n\nTEMPERATURE_ROUNDING_MODES = {"nearest", "down", "up"}\nDEFAULT_TEMPERATURE_ROUNDING_MODE = "nearest"\n\n\ndef get_temperature_rounding_mode(hass: HomeAssistant) -> str:\n    """Return the global physical-device temperature rounding preference."""\n    try:\n        store = hass.data.get(DOMAIN, {}).get("store")\n        mode = store.get_settings().get("temperature_rounding_mode") if store else None\n    except (AttributeError, TypeError):\n        mode = None\n    return mode if mode in TEMPERATURE_ROUNDING_MODES else DEFAULT_TEMPERATURE_ROUNDING_MODE\n\n\ndef quantize_temperature_to_step(value: float, step: float | None, mode: str = "nearest") -> float:\n    """Quantize *value* to *step* using deterministic up/down/nearest rounding."""\n    import math\n\n    if step is None or step <= 0:\n        return float(value)\n    if mode not in TEMPERATURE_ROUNDING_MODES:\n        mode = DEFAULT_TEMPERATURE_ROUNDING_MODE\n\n    ratio = float(value) / float(step)\n    epsilon = 1e-9\n    if mode == "down":\n        units = math.floor(ratio + epsilon)\n    elif mode == "up":\n        units = math.ceil(ratio - epsilon)\n    else:\n        # Half-up instead of Python's bankers rounding: 26.5 -> 27 for step 1.\n        units = math.floor(ratio + 0.5 + epsilon)\n    return round(units * float(step), 3)\n\n\ndef quantize_temperature_for_entity(\n    hass: HomeAssistant,\n    entity_id: str,\n    value: float,\n    *,\n    fallback_step: float | None = None,\n) -> float:\n    """Quantize an HA-unit setpoint to a climate entity's supported step."""\n    state = hass.states.get(entity_id)\n    attrs = state.attributes if state is not None else {}\n    raw_step = attrs.get("target_temp_step", fallback_step)\n    try:\n        step = float(raw_step) if raw_step is not None else None\n    except (TypeError, ValueError):\n        step = fallback_step\n\n    result = quantize_temperature_to_step(value, step, get_temperature_rounding_mode(hass))\n    for key, fn in (("min_temp", max), ("max_temp", min)):\n        raw = attrs.get(key)\n        if raw is not None:\n            try:\n                result = fn(result, float(raw))\n            except (TypeError, ValueError):\n                pass\n    return round(result, 3)\n'''
if "def quantize_temperature_to_step(" not in text:
    text += append
p.write_text(text)

# ---------------------------------------------------------------------------
# Canonical climate manual routing: quantize every physical setpoint.
# ---------------------------------------------------------------------------
p = Path("custom_components/roommind/climate.py")
text = p.read_text()
text = text.replace(
    "from .utils.temp_utils import celsius_to_ha_temp\n",
    "from .utils.temp_utils import celsius_to_ha_temp, quantize_temperature_for_entity\n",
)
text = text.replace(
'''        if direction == "heat":\n            target = celsius_to_ha_temp(hass, heat)\n            for entity_id in trvs:\n                await hass.services.async_call(\n                    "climate",\n                    "set_temperature",\n                    {"entity_id": entity_id, "temperature": target},''',
'''        if direction == "heat":\n            raw_target = celsius_to_ha_temp(hass, heat)\n            for entity_id in trvs:\n                target = quantize_temperature_for_entity(hass, entity_id, raw_target, fallback_step=0.5)\n                await hass.services.async_call(\n                    "climate",\n                    "set_temperature",\n                    {"entity_id": entity_id, "temperature": target},''')
text = text.replace(
'''                if resolve_hvac_mode("heat", modes) is not None:\n                    await hass.services.async_call(\n                        "climate",\n                        "set_temperature",\n                        {"entity_id": entity_id, "temperature": target},''',
'''                if resolve_hvac_mode("heat", modes) is not None:\n                    target = quantize_temperature_for_entity(hass, entity_id, raw_target, fallback_step=1.0)\n                    await hass.services.async_call(\n                        "climate",\n                        "set_temperature",\n                        {"entity_id": entity_id, "temperature": target},''')
text = text.replace(
'''        if direction in ("cool", "dry"):\n            target = celsius_to_ha_temp(hass, cool)\n            for entity_id in acs:\n                await hass.services.async_call(\n                    "climate",\n                    "set_temperature",\n                    {"entity_id": entity_id, "temperature": target},''',
'''        if direction in ("cool", "dry"):\n            raw_target = celsius_to_ha_temp(hass, cool)\n            for entity_id in acs:\n                target = quantize_temperature_for_entity(hass, entity_id, raw_target, fallback_step=1.0)\n                await hass.services.async_call(\n                    "climate",\n                    "set_temperature",\n                    {"entity_id": entity_id, "temperature": target},''')
text = text.replace(
'''        if mode in ("heat", "heat_cool", "auto"):\n            ha_heat = celsius_to_ha_temp(hass, heat)\n            for entity_id in trvs:''',
'''        if mode in ("heat", "heat_cool", "auto"):\n            ha_heat = celsius_to_ha_temp(hass, heat)\n            for entity_id in trvs:''')
text = text.replace(
'''                    await hass.services.async_call(\n                        "climate",\n                        "set_temperature",\n                        {"entity_id": entity_id, "temperature": ha_heat},''',
'''                    trv_target = quantize_temperature_for_entity(hass, entity_id, ha_heat, fallback_step=0.5)\n                    await hass.services.async_call(\n                        "climate",\n                        "set_temperature",\n                        {"entity_id": entity_id, "temperature": trv_target},''', 1)
text = text.replace(
'''                data.update(\n                    target_temp_low=celsius_to_ha_temp(hass, heat),\n                    target_temp_high=celsius_to_ha_temp(hass, cool),\n                )''',
'''                data.update(\n                    target_temp_low=quantize_temperature_for_entity(\n                        hass, entity_id, celsius_to_ha_temp(hass, heat), fallback_step=1.0\n                    ),\n                    target_temp_high=quantize_temperature_for_entity(\n                        hass, entity_id, celsius_to_ha_temp(hass, cool), fallback_step=1.0\n                    ),\n                )''')
text = text.replace(
'''                target = cool if mode == "cool" else heat\n                data["temperature"] = celsius_to_ha_temp(hass, target)''',
'''                target = cool if mode == "cool" else heat\n                data["temperature"] = quantize_temperature_for_entity(\n                    hass, entity_id, celsius_to_ha_temp(hass, target), fallback_step=1.0\n                )''')
p.write_text(text)

# ---------------------------------------------------------------------------
# MPC automatic control: apply the same global preference when snapping to a
# physical entity's reported target_temp_step.
# ---------------------------------------------------------------------------
p = Path("custom_components/roommind/control/mpc_controller.py")
text = p.read_text()
text = text.replace(
    "from ..utils.temp_utils import celsius_delta_to_ha, celsius_to_ha_temp\n",
    "from ..utils.temp_utils import (\n    celsius_delta_to_ha,\n    celsius_to_ha_temp,\n    get_temperature_rounding_mode,\n    quantize_temperature_to_step,\n)\n",
)
text = text.replace(
'''def _snap_to_step(value: float, step: float | None) -> float:\n    if step is None or step <= 0:\n        return value\n    return round(round(value / step) * step, 2)''',
'''def _snap_to_step(hass: HomeAssistant, value: float, step: float | None) -> float:\n    return quantize_temperature_to_step(value, step, get_temperature_rounding_mode(hass))''')
text = text.replace("_snap_to_step(ha_t, float(step))", "_snap_to_step(self.hass, ha_t, float(step))")
text = text.replace('_snap_to_step(data["temperature"], step)', '_snap_to_step(self.hass, data["temperature"], step)')
text = text.replace('_snap_to_step(data["target_temp_low"], step)', '_snap_to_step(self.hass, data["target_temp_low"], step)')
text = text.replace('_snap_to_step(data["target_temp_high"], step)', '_snap_to_step(self.hass, data["target_temp_high"], step)')
p.write_text(text)

# ---------------------------------------------------------------------------
# Websocket global setting contract
# ---------------------------------------------------------------------------
p = Path("custom_components/roommind/websocket_api.py")
text = p.read_text()
text = text.replace(
    '    "climate_control_active",\n',
    '    "climate_control_active",\n    "temperature_rounding_mode",\n',
    1,
)
text = text.replace(
    '    vol.Optional("climate_control_active"): bool,\n',
    '    vol.Optional("climate_control_active"): bool,\n    vol.Optional("temperature_rounding_mode"): vol.In(["nearest", "down", "up"]),\n',
    1,
)
p.write_text(text)

# ---------------------------------------------------------------------------
# Frontend types and settings state/save wiring
# ---------------------------------------------------------------------------
p = Path("frontend/src/types/index.ts")
text = p.read_text().replace(
    '  climate_control_active?: boolean;\n',
    '  climate_control_active?: boolean;\n  temperature_rounding_mode?: "nearest" | "down" | "up";\n',
    1,
)
p.write_text(text)

p = Path("frontend/src/components/rs-settings.ts")
text = p.read_text()
text = text.replace(
    '  @state() private _climateControlActive = true;\n',
    '  @state() private _climateControlActive = true;\n  @state() private _temperatureRoundingMode: "nearest" | "down" | "up" = "nearest";\n',
    1,
)
text = text.replace(
    '      this._climateControlActive = s.climate_control_active ?? true;\n',
    '      this._climateControlActive = s.climate_control_active ?? true;\n      this._temperatureRoundingMode = s.temperature_rounding_mode ?? "nearest";\n',
    1,
)
text = text.replace(
    '          .climateControlActive=${this._climateControlActive}\n',
    '          .climateControlActive=${this._climateControlActive}\n          .temperatureRoundingMode=${this._temperatureRoundingMode}\n',
    1,
)
text = text.replace(
    '        climate_control_active: this._climateControlActive,\n',
    '        climate_control_active: this._climateControlActive,\n        temperature_rounding_mode: this._temperatureRoundingMode,\n',
    1,
)
p.write_text(text)

p = Path("frontend/src/components/settings/rs-settings-general.ts")
text = p.read_text()
text = text.replace(
    'import { localize } from "../../utils/localize";\n',
    'import { localize } from "../../utils/localize";\nimport "../shared/rs-radio-group";\n',
    1,
)
text = text.replace(
    '  @property({ type: Boolean }) public climateControlActive = true;\n',
    '  @property({ type: Boolean }) public climateControlActive = true;\n  @property({ type: String }) public temperatureRoundingMode: "nearest" | "down" | "up" = "nearest";\n',
    1,
)
needle = '''      </div>\n    `;\n  }'''
replacement = '''      </div>\n\n      <div class="settings-section">\n        <div class="toggle-text">\n          <span class="toggle-label">${localize("settings.temperature_rounding", l)}</span>\n          <span class="toggle-hint">${localize("settings.temperature_rounding_hint", l)}</span>\n        </div>\n        <div style="margin-top: 12px">\n          <rs-radio-group\n            .options=${[\n              { value: "nearest", label: localize("settings.temperature_rounding_nearest", l) },\n              { value: "down", label: localize("settings.temperature_rounding_down", l) },\n              { value: "up", label: localize("settings.temperature_rounding_up", l) },\n            ]}\n            .selected=${this.temperatureRoundingMode}\n            @selected-changed=${(e: CustomEvent<string>) => this._fire("temperatureRoundingMode", e.detail)}\n          ></rs-radio-group>\n        </div>\n      </div>\n    `;\n  }'''
if needle not in text:
    raise SystemExit("general settings render marker not found")
text = text.replace(needle, replacement, 1)
p.write_text(text)

# Add locale keys to all bundled locales, close to climate control labels.
locale_values = {
    "en": {
        "temperature_rounding": "Physical temperature rounding",
        "temperature_rounding_hint": "When a climate device cannot represent RoomMind's 0.5° setpoint, choose how the physical target is rounded.",
        "temperature_rounding_nearest": "Nearest supported value",
        "temperature_rounding_down": "Round down (26.5° → 26°)",
        "temperature_rounding_up": "Round up (26.5° → 27°)",
    },
    "de": {
        "temperature_rounding": "Rundung der Gerätetemperatur",
        "temperature_rounding_hint": "Legt fest, wie RoomMind auf die vom Klimagerät unterstützte Schrittweite rundet.",
        "temperature_rounding_nearest": "Nächster unterstützter Wert",
        "temperature_rounding_down": "Abrunden (26,5° → 26°)",
        "temperature_rounding_up": "Aufrunden (26,5° → 27°)",
    },
    "fr": {
        "temperature_rounding": "Arrondi de la température physique",
        "temperature_rounding_hint": "Définit comment RoomMind arrondit vers le pas pris en charge par l'appareil climatique.",
        "temperature_rounding_nearest": "Valeur prise en charge la plus proche",
        "temperature_rounding_down": "Arrondir vers le bas (26,5° → 26°)",
        "temperature_rounding_up": "Arrondir vers le haut (26,5° → 27°)",
    },
}
import json
for locale, values in locale_values.items():
    path = Path(f"frontend/src/locales/{locale}.json")
    data = json.loads(path.read_text())
    settings = data.setdefault("settings", {})
    settings.update(values)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
p = Path("tests/utils/test_temp_utils.py")
text = p.read_text()
if "quantize_temperature_to_step" not in text.split("\n", 30)[0:30]:
    # Add imports to an existing from-import when possible, otherwise standalone.
    if "from custom_components.roommind.utils.temp_utils import (" in text:
        text = text.replace(
            "from custom_components.roommind.utils.temp_utils import (",
            "from custom_components.roommind.utils.temp_utils import (\n    quantize_temperature_to_step,",
            1,
        )
    else:
        text = "from custom_components.roommind.utils.temp_utils import quantize_temperature_to_step\n" + text
if "test_quantize_temperature_rounding_modes" not in text:
    text += '''\n\ndef test_quantize_temperature_rounding_modes():\n    assert quantize_temperature_to_step(26.5, 1.0, "nearest") == 27.0\n    assert quantize_temperature_to_step(26.5, 1.0, "down") == 26.0\n    assert quantize_temperature_to_step(26.5, 1.0, "up") == 27.0\n    assert quantize_temperature_to_step(26.5, 0.5, "down") == 26.5\n    assert quantize_temperature_to_step(26.25, 0.5, "nearest") == 26.5\n'''
p.write_text(text)

p = Path("tests/test_climate.py")
text = p.read_text()
if "test_canonical_manual_cool_temperature_respects_global_round_down" not in text:
    text += '''\n\n@pytest.mark.asyncio\nasync def test_canonical_manual_cool_temperature_respects_global_round_down(mock_coordinator):\n    coordinator, store = mock_coordinator\n    store.get_room.return_value = _canonical_room(\n        [{"entity_id": "climate.ac", "type": "ac"}],\n        room_hvac_mode="cool",\n        logical_heat_target=21.0,\n        logical_cool_target=26.0,\n    )\n    store.get_settings.return_value = {"temperature_rounding_mode": "down"}\n    store.async_update_room = AsyncMock()\n    coordinator.hass.states.get.return_value = MagicMock(\n        state="cool",\n        attributes={"hvac_modes": ["off", "cool"], "target_temp_step": 1.0},\n    )\n    coordinator.hass.services.async_call = AsyncMock()\n\n    await RoomMindClimate(coordinator, "living_room").async_set_temperature(temperature=26.5)\n\n    coordinator.hass.services.async_call.assert_any_await(\n        "climate",\n        "set_temperature",\n        {"entity_id": "climate.ac", "temperature": 26.0},\n        blocking=True,\n    )\n\n\n@pytest.mark.asyncio\nasync def test_canonical_manual_trv_keeps_supported_half_degree(mock_coordinator):\n    coordinator, store = mock_coordinator\n    store.get_room.return_value = _canonical_room(\n        [{"entity_id": "climate.trv", "type": "trv"}],\n        room_hvac_mode="heat",\n        logical_heat_target=20.0,\n        logical_cool_target=25.0,\n    )\n    store.get_settings.return_value = {"temperature_rounding_mode": "down"}\n    store.async_update_room = AsyncMock()\n    coordinator.hass.states.get.return_value = MagicMock(\n        state="heat",\n        attributes={"hvac_modes": ["off", "heat"], "target_temp_step": 0.5},\n    )\n    coordinator.hass.services.async_call = AsyncMock()\n\n    await RoomMindClimate(coordinator, "living_room").async_set_temperature(temperature=20.5)\n\n    coordinator.hass.services.async_call.assert_any_await(\n        "climate",\n        "set_temperature",\n        {"entity_id": "climate.trv", "temperature": 20.5},\n        blocking=True,\n    )\n'''
p.write_text(text)

print("temperature step rounding patch applied")
