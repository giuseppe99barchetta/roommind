from pathlib import Path
import json
import re


def sub(path: str, pattern: str, replacement: str, count: int = 1, flags: int = 0) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    new, n = re.subn(pattern, replacement, text, count=count, flags=flags)
    if n != count:
        raise SystemExit(f"{path}: pattern matched {n}, expected {count}: {pattern[:100]!r}")
    p.write_text(new, encoding="utf-8")


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if text.count(old) < count:
        raise SystemExit(f"{path}: block missing: {old[:100]!r}")
    p.write_text(text.replace(old, new, count), encoding="utf-8")


# --- Backend persistence ---
replace("custom_components/roommind/websocket_api.py", '    "window_close_delay",\n', '    "window_close_delay",\n    "keep_fan_only_on_window_open",\n')
replace(
    "custom_components/roommind/websocket_api.py",
    '        vol.Optional("window_close_delay"): vol.Coerce(int),\n',
    '        vol.Optional("window_close_delay"): vol.Coerce(int),\n        vol.Optional("keep_fan_only_on_window_open"): bool,\n',
)

# Boiler reconciliation can issue climate/switch commands outside room control.
sub(
    "custom_components/roommind/managers/boiler_manager.py",
    r'(    async def async_reconcile\(self, settings: dict, demand_rooms: set\[str\]\) -> None:\n        """[^\n]+"""\n)',
    r'\1        if not settings.get("climate_control_active", True):\n            return\n',
)

# Valve protection is an independent actuator and must obey the master switch.
replace(
    "custom_components/roommind/managers/valve_manager.py",
    '    DEFAULT_COMFORT_HEAT,\n',
    '    DEFAULT_COMFORT_HEAT,\n    DOMAIN,\n',
)
replace(
    "custom_components/roommind/managers/valve_manager.py",
    '        if not self._cycling:\n            return\n        now = time.time()\n',
    '        store = self.hass.data.get(DOMAIN, {}).get("store")\n        if store is not None and not store.get_settings().get("climate_control_active", True):\n            return\n        if not self._cycling:\n            return\n        now = time.time()\n',
)
replace(
    "custom_components/roommind/managers/valve_manager.py",
    '        """Scan for TRV valves that have been idle too long and start cycling them."""\n        if not settings.get("valve_protection_enabled", False):\n',
    '        """Scan for TRV valves that have been idle too long and start cycling them."""\n        if not settings.get("climate_control_active", True):\n            return\n        if not settings.get("valve_protection_enabled", False):\n',
)

# Auxiliary routing defense-in-depth.
replace(
    "custom_components/roommind/managers/room_climate.py",
    'from ..const import make_roommind_context',
    'from ..const import DOMAIN, make_roommind_context',
)
replace(
    "custom_components/roommind/managers/room_climate.py",
    '    """Route dry/fan-only and optional AC controls only to the configured AC."""\n    acs = get_ac_eids(room.get("devices", []))\n',
    '    """Route dry/fan-only and optional AC controls only to the configured AC."""\n    store = hass.data.get(DOMAIN, {}).get("store")\n    if store is not None:\n        settings = store.get_settings()\n        if not settings.get("climate_control_active", True) or not room.get("climate_control_enabled", True):\n            return\n\n    acs = get_ac_eids(room.get("devices", []))\n',
)

# Direct fan/swing calls from climate.roommind_* must persist settings only when disabled.
replace(
    "custom_components/roommind/climate.py",
    '        await self.coordinator.hass.data[DOMAIN]["store"].async_update_room(self._area_id, {key: value})\n        await self.coordinator.hass.services.async_call(\n            "climate", service, {"entity_id": acs[0], service_key: value}, blocking=True\n        )\n',
    '        store = self.coordinator.hass.data[DOMAIN]["store"]\n        await store.async_update_room(self._area_id, {key: value})\n        settings = store.get_settings()\n        room = store.get_room(self._area_id) or {}\n        if not settings.get("climate_control_active", True) or not room.get("climate_control_enabled", True):\n            return\n        await self.coordinator.hass.services.async_call(\n            "climate", service, {"entity_id": acs[0], service_key: value}, blocking=True\n        )\n',
)

# --- Frontend ---
replace(
    "frontend/src/types/index.ts",
    '  window_close_delay: number;\n',
    '  window_close_delay: number;\n  keep_fan_only_on_window_open?: boolean;\n',
)

sensor = "frontend/src/components/rs-sensor-section.ts"
replace(sensor, '  @property({ type: Number }) public windowCloseDelay = 0;\n', '  @property({ type: Number }) public windowCloseDelay = 0;\n  @property({ type: Boolean }) public keepFanOnlyOnWindowOpen = true;\n')
replace(
    sensor,
    '      .delay-view {\n',
    '      .fan-window-toggle { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 10px; padding: 9px 10px; border-radius: 9px; background: rgba(255,255,255,0.025); }\n      .fan-window-toggle-text { min-width: 0; }\n      .fan-window-toggle-label { display: block; color: var(--primary-text-color); font-size: 12.5px; font-weight: 500; }\n      .fan-window-toggle-hint { display: block; color: var(--secondary-text-color); font-size: 11px; line-height: 1.4; margin-top: 2px; }\n\n      .delay-view {\n',
)
replace(
    sensor,
    '      ${this.heatingSystemType === "underfloor" && this.windowOpenDelay < 300\n',
    '      <div class="fan-window-toggle">\n        <div class="fan-window-toggle-text">\n          <span class="fan-window-toggle-label">${localize("devices.keep_fan_only_window", lang)}</span>\n          <span class="fan-window-toggle-hint">${localize("devices.keep_fan_only_window_hint", lang)}</span>\n        </div>\n        <ha-switch .checked=${this.keepFanOnlyOnWindowOpen} @change=${this._onKeepFanOnlyWindowChange}></ha-switch>\n      </div>\n      ${this.heatingSystemType === "underfloor" && this.windowOpenDelay < 300\n',
)
replace(
    sensor,
    '  private _onWindowOpenDelayChange = (e: Event) => {\n',
    '  private _onKeepFanOnlyWindowChange = (e: Event) => {\n    const value = (e.target as HTMLElement & { checked: boolean }).checked;\n    this.dispatchEvent(new CustomEvent("sensor-changed", { detail: { key: "keep_fan_only_on_window_open", value }, bubbles: true, composed: true }));\n  };\n\n  private _onWindowOpenDelayChange = (e: Event) => {\n',
)

room = "frontend/src/components/rs-room-detail.ts"
replace(room, '  @state() private _windowCloseDelay = 0;\n', '  @state() private _windowCloseDelay = 0;\n  @state() private _keepFanOnlyOnWindowOpen = true;\n')
replace(room, '      this._windowCloseDelay = this.config.window_close_delay ?? 0;\n', '      this._windowCloseDelay = this.config.window_close_delay ?? 0;\n      this._keepFanOnlyOnWindowOpen = this.config.keep_fan_only_on_window_open ?? true;\n')
replace(room, '      this._windowCloseDelay = 0;\n', '      this._windowCloseDelay = 0;\n      this._keepFanOnlyOnWindowOpen = true;\n')
# Both view and edit sensor components have the same property sequence.
replace(room, '.windowCloseDelay=${this._windowCloseDelay}\n', '.windowCloseDelay=${this._windowCloseDelay}\n                    .keepFanOnlyOnWindowOpen=${this._keepFanOnlyOnWindowOpen}\n', 1)
# Second instance has 12-space indentation; normalize the inserted line separately.
p = Path(room)
text = p.read_text(encoding="utf-8")
needle = '            .windowCloseDelay=${this._windowCloseDelay}\n            .heatingSystemType='
if needle not in text:
    raise SystemExit("room detail second sensor component not found")
text = text.replace(needle, '            .windowCloseDelay=${this._windowCloseDelay}\n            .keepFanOnlyOnWindowOpen=${this._keepFanOnlyOnWindowOpen}\n            .heatingSystemType=', 1)
p.write_text(text, encoding="utf-8")
replace(room, 'CustomEvent<{ key: string; value: string | string[] | number }>', 'CustomEvent<{ key: string; value: string | string[] | number | boolean }>')
replace(
    room,
    '    } else if (key === "window_close_delay") {\n      this._windowCloseDelay = value as number;\n    }\n',
    '    } else if (key === "window_close_delay") {\n      this._windowCloseDelay = value as number;\n    } else if (key === "keep_fan_only_on_window_open") {\n      this._keepFanOnlyOnWindowOpen = value as boolean;\n    }\n',
)
replace(room, '        climate_control_enabled: this._climateControlEnabled,\n', '        climate_control_enabled: this._climateControlEnabled,\n        keep_fan_only_on_window_open: this._keepFanOnlyOnWindowOpen,\n')

translations = {
    "en": ("Keep fan-only with open window", "Heating and cooling pause, but an AC already in fan-only mode stays on."),
    "de": ("Nur Lüften bei offenem Fenster beibehalten", "Heizen und Kühlen werden pausiert, aber ein Klimagerät im Nur-Lüften-Modus bleibt eingeschaltet."),
    "fr": ("Maintenir la ventilation seule si la fenêtre est ouverte", "Le chauffage et le refroidissement sont suspendus, mais un climatiseur en ventilation seule reste allumé."),
}
for locale, values in translations.items():
    p = Path(f"frontend/src/locales/{locale}.json")
    data = json.loads(p.read_text(encoding="utf-8"))
    data.setdefault("devices", {})["keep_fan_only_window"] = values[0]
    data["devices"]["keep_fan_only_window_hint"] = values[1]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
