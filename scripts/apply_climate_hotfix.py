from pathlib import Path
import json


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"{path}: expected block not found: {old[:120]!r}")
    p.write_text(text.replace(old, new, count), encoding="utf-8")


# Persist per-room fan-only/window option.
replace(
    "custom_components/roommind/websocket_api.py",
    '    "window_close_delay",\n    "comfort_temp",',
    '    "window_close_delay",\n    "keep_fan_only_on_window_open",\n    "comfort_temp",',
)
replace(
    "custom_components/roommind/websocket_api.py",
    '        vol.Optional("window_close_delay"): vol.Coerce(int),\n        vol.Optional("comfort_temp"):',
    '        vol.Optional("window_close_delay"): vol.Coerce(int),\n        vol.Optional("keep_fan_only_on_window_open"): bool,\n        vol.Optional("comfort_temp"):',
)

# Boiler reconcile must not send commands while the global master switch is off.
replace(
    "custom_components/roommind/managers/boiler_manager.py",
    'from ..const import make_roommind_context',
    'from ..const import DOMAIN, make_roommind_context',
)
replace(
    "custom_components/roommind/managers/boiler_manager.py",
    '''    async def async_reconcile(self, settings: dict, demand_rooms: set[str]) -> None:\n        """Reconcile boiler output with current room demand."""\n''',
    '''    async def async_reconcile(self, settings: dict, demand_rooms: set[str]) -> None:\n        """Reconcile boiler output with current room demand."""\n        if not settings.get("climate_control_active", True):\n            return\n''',
)

# Valve protection can actuate TRVs independently of the normal controller.
replace(
    "custom_components/roommind/managers/valve_manager.py",
    '    DEFAULT_COMFORT_HEAT,\n',
    '    DEFAULT_COMFORT_HEAT,\n    DOMAIN,\n',
)
replace(
    "custom_components/roommind/managers/valve_manager.py",
    '''    async def async_finish_cycles(\n        self,\n        rooms_devices: dict[str, list[dict]] | None = None,\n    ) -> None:\n        """End valve protection cycles that have exceeded their duration.\n''',
    '''    async def async_finish_cycles(\n        self,\n        rooms_devices: dict[str, list[dict]] | None = None,\n    ) -> None:\n        """End valve protection cycles that have exceeded their duration.\n''',
)
# Insert guard after async_finish_cycles docstring, using the first stable code line.
replace(
    "custom_components/roommind/managers/valve_manager.py",
    '''        if not self._cycling:\n            return\n        now = time.time()\n''',
    '''        store = self.hass.data.get(DOMAIN, {}).get("store")\n        if store is not None and not store.get_settings().get("climate_control_active", True):\n            return\n        if not self._cycling:\n            return\n        now = time.time()\n''',
)
replace(
    "custom_components/roommind/managers/valve_manager.py",
    '''    async def async_check_and_cycle(self, rooms: dict, settings: dict) -> None:\n        """Scan for TRV valves that have been idle too long and start cycling them."""\n        if not settings.get("valve_protection_enabled", False):\n''',
    '''    async def async_check_and_cycle(self, rooms: dict, settings: dict) -> None:\n        """Scan for TRV valves that have been idle too long and start cycling them."""\n        if not settings.get("climate_control_active", True):\n            return\n        if not settings.get("valve_protection_enabled", False):\n''',
)

# Auxiliary AC routing must obey both global and per-room control switches.
replace(
    "custom_components/roommind/managers/room_climate.py",
    'from ..const import make_roommind_context',
    'from ..const import DOMAIN, make_roommind_context',
)
replace(
    "custom_components/roommind/managers/room_climate.py",
    '''async def async_apply_ac_auxiliary_mode(hass: HomeAssistant, room: dict) -> None:\n    """Route dry/fan-only and optional AC controls only to the configured AC."""\n    acs = get_ac_eids(room.get("devices", []))\n''',
    '''async def async_apply_ac_auxiliary_mode(hass: HomeAssistant, room: dict) -> None:\n    """Route dry/fan-only and optional AC controls only to the configured AC."""\n    store = hass.data.get(DOMAIN, {}).get("store")\n    if store is not None:\n        settings = store.get_settings()\n        if not settings.get("climate_control_active", True) or not room.get("climate_control_enabled", True):\n            return\n\n    acs = get_ac_eids(room.get("devices", []))\n''',
)

# Direct fan/swing controls persist the chosen value but do not touch hardware
# while global or room control is disabled.
replace(
    "custom_components/roommind/climate.py",
    '''        await self.coordinator.hass.data[DOMAIN]["store"].async_update_room(self._area_id, {key: value})\n        await self.coordinator.hass.services.async_call(\n            "climate", service, {"entity_id": acs[0], service_key: value}, blocking=True\n        )\n''',
    '''        store = self.coordinator.hass.data[DOMAIN]["store"]\n        await store.async_update_room(self._area_id, {key: value})\n        settings = store.get_settings()\n        room = store.get_room(self._area_id) or {}\n        if not settings.get("climate_control_active", True) or not room.get("climate_control_enabled", True):\n            return\n        await self.coordinator.hass.services.async_call(\n            "climate", service, {"entity_id": acs[0], service_key: value}, blocking=True\n        )\n''',
)

# Frontend model.
replace(
    "frontend/src/types/index.ts",
    '  window_close_delay: number;\n  climate_mode: ClimateMode;',
    '  window_close_delay: number;\n  keep_fan_only_on_window_open?: boolean;\n  climate_mode: ClimateMode;',
)

# Window UI toggle.
replace(
    "frontend/src/components/rs-sensor-section.ts",
    '  @property({ type: Number }) public windowCloseDelay = 0;\n  @property({ type: String }) public heatingSystemType = "";',
    '  @property({ type: Number }) public windowCloseDelay = 0;\n  @property({ type: Boolean }) public keepFanOnlyOnWindowOpen = true;\n  @property({ type: String }) public heatingSystemType = "";',
)
replace(
    "frontend/src/components/rs-sensor-section.ts",
    '''      .delay-view {\n        font-size: 12px;\n''',
    '''      .fan-window-toggle {\n        display: flex;\n        align-items: center;\n        justify-content: space-between;\n        gap: 12px;\n        margin-top: 10px;\n        padding: 9px 10px;\n        border-radius: 9px;\n        background: rgba(255, 255, 255, 0.025);\n      }\n\n      .fan-window-toggle-text { min-width: 0; }\n      .fan-window-toggle-label {\n        display: block;\n        color: var(--primary-text-color);\n        font-size: 12.5px;\n        font-weight: 500;\n      }\n      .fan-window-toggle-hint {\n        display: block;\n        color: var(--secondary-text-color);\n        font-size: 11px;\n        line-height: 1.4;\n        margin-top: 2px;\n      }\n\n      .delay-view {\n        font-size: 12px;\n''',
)
replace(
    "frontend/src/components/rs-sensor-section.ts",
    '''      </div>\n      ${this.heatingSystemType === "underfloor" && this.windowOpenDelay < 300\n''',
    '''      </div>\n      <div class="fan-window-toggle">\n        <div class="fan-window-toggle-text">\n          <span class="fan-window-toggle-label">${localize("devices.keep_fan_only_window", lang)}</span>\n          <span class="fan-window-toggle-hint">${localize("devices.keep_fan_only_window_hint", lang)}</span>\n        </div>\n        <ha-switch .checked=${this.keepFanOnlyOnWindowOpen} @change=${this._onKeepFanOnlyWindowChange}></ha-switch>\n      </div>\n      ${this.heatingSystemType === "underfloor" && this.windowOpenDelay < 300\n''',
)
marker = '  private _onWindowOpenDelayChange = (e: Event) => {\n'
p = Path("frontend/src/components/rs-sensor-section.ts")
text = p.read_text(encoding="utf-8")
if marker not in text:
    raise SystemExit("sensor event marker not found")
handler = '''  private _onKeepFanOnlyWindowChange = (e: Event) => {\n    const value = (e.target as HTMLElement & { checked: boolean }).checked;\n    this.dispatchEvent(\n      new CustomEvent("sensor-changed", {\n        detail: { key: "keep_fan_only_on_window_open", value },\n        bubbles: true,\n        composed: true,\n      }),\n    );\n  };\n\n'''
p.write_text(text.replace(marker, handler + marker, 1), encoding="utf-8")

# Room detail state and save payload.
replace(
    "frontend/src/components/rs-room-detail.ts",
    '  @state() private _windowCloseDelay = 0;\n  @state() private _climateMode:',
    '  @state() private _windowCloseDelay = 0;\n  @state() private _keepFanOnlyOnWindowOpen = true;\n  @state() private _climateMode:',
)
replace(
    "frontend/src/components/rs-room-detail.ts",
    '      this._windowCloseDelay = this.config.window_close_delay ?? 0;\n      this._climateMode =',
    '      this._windowCloseDelay = this.config.window_close_delay ?? 0;\n      this._keepFanOnlyOnWindowOpen = this.config.keep_fan_only_on_window_open ?? true;\n      this._climateMode =',
)
replace(
    "frontend/src/components/rs-room-detail.ts",
    '      this._windowCloseDelay = 0;\n      this._climateMode = "auto";',
    '      this._windowCloseDelay = 0;\n      this._keepFanOnlyOnWindowOpen = true;\n      this._climateMode = "auto";',
)
p = Path("frontend/src/components/rs-room-detail.ts")
text = p.read_text(encoding="utf-8")
for old, new in (
    (
        '                    .windowCloseDelay=${this._windowCloseDelay}\n                    .heatingSystemType=',
        '                    .windowCloseDelay=${this._windowCloseDelay}\n                    .keepFanOnlyOnWindowOpen=${this._keepFanOnlyOnWindowOpen}\n                    .heatingSystemType=',
    ),
    (
        '            .windowCloseDelay=${this._windowCloseDelay}\n            .heatingSystemType=',
        '            .windowCloseDelay=${this._windowCloseDelay}\n            .keepFanOnlyOnWindowOpen=${this._keepFanOnlyOnWindowOpen}\n            .heatingSystemType=',
    ),
):
    if old not in text:
        raise SystemExit(f"room detail wiring block missing: {old!r}")
    text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")
replace(
    "frontend/src/components/rs-room-detail.ts",
    '  private _onSensorChanged(e: CustomEvent<{ key: string; value: string | string[] | number }>) {',
    '  private _onSensorChanged(e: CustomEvent<{ key: string; value: string | string[] | number | boolean }>) {',
)
replace(
    "frontend/src/components/rs-room-detail.ts",
    '''    } else if (key === "window_close_delay") {\n      this._windowCloseDelay = value as number;\n    }\n''',
    '''    } else if (key === "window_close_delay") {\n      this._windowCloseDelay = value as number;\n    } else if (key === "keep_fan_only_on_window_open") {\n      this._keepFanOnlyOnWindowOpen = value as boolean;\n    }\n''',
)
replace(
    "frontend/src/components/rs-room-detail.ts",
    '        climate_control_enabled: this._climateControlEnabled,\n        covers_auto_enabled:',
    '        climate_control_enabled: this._climateControlEnabled,\n        keep_fan_only_on_window_open: this._keepFanOnlyOnWindowOpen,\n        covers_auto_enabled:',
)

# Locales.
translations = {
    "en": (
        "Keep fan-only with open window",
        "Heating and cooling pause, but an AC already in fan-only mode stays on.",
    ),
    "de": (
        "Nur Lüften bei offenem Fenster beibehalten",
        "Heizen und Kühlen werden pausiert, aber ein Klimagerät im Nur-Lüften-Modus bleibt eingeschaltet.",
    ),
    "fr": (
        "Maintenir la ventilation seule si la fenêtre est ouverte",
        "Le chauffage et le refroidissement sont suspendus, mais un climatiseur en ventilation seule reste allumé.",
    ),
}
for locale, (label, hint) in translations.items():
    path = Path(f"frontend/src/locales/{locale}.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    devices = data.setdefault("devices", {})
    devices["keep_fan_only_window"] = label
    devices["keep_fan_only_window_hint"] = hint
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
