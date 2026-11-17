import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createServer } from "vite";

let server, Settings;
const panels = {};
const NAMES = [
  "general",
  "sensors",
  "control",
  "presence",
  "vacation",
  "valve",
  "compressor",
  "mold",
  "notifications",
  "learning",
  "head-offset",
  "heating-system",
];
before(async () => {
  globalThis.window ??= { addEventListener() {}, removeEventListener() {} };
  server = await createServer({ configFile: false, server: { middlewareMode: true } });
  ({ RsSettings: Settings } = await server.ssrLoadModule("/src/components/rs-settings.ts"));
  for (const name of NAMES) {
    const mod = await server.ssrLoadModule(`/src/components/settings/rs-settings-${name}.ts`);
    panels[name] = Object.values(mod).find((v) => typeof v === "function" && v.prototype?.render);
  }
});
after(async () => {
  await server?.close();
});

const hass = {
  language: "en",
  areas: { sala: { area_id: "sala", name: "Sala" } },
  floors: { f: { floor_id: "f", name: "F" } },
  states: {},
  entities: {},
  devices: {},
  config: { unit_system: { temperature: "°C" } },
  callWS: async () => ({}),
};

function handlers(value, out = []) {
  if (typeof value === "function") out.push(value);
  else if (Array.isArray(value)) value.forEach((v) => handlers(v, out));
  else if (value && typeof value === "object" && value.strings) handlers(value.values, out);
  return out;
}

/** Every toggle / field / choice of every panel, fired; what each panel emits as settings. */
function touchEveryPanel() {
  const emitted = [];
  const props = {
    general: {},
    sensors: { outdoorTempSensor: "sensor.out" },
    control: {},
    presence: { presenceEnabled: true, presencePersons: ["person.a"] },
    vacation: { vacationActive: true },
    valve: { valveProtectionEnabled: true },
    compressor: {
      compressorGroups: [
        {
          id: "g",
          name: "G",
          members: ["climate.a"],
          min_run_minutes: 5,
          min_off_minutes: 3,
          master_entity: "",
          conflict_resolution: "heating_priority",
          action_script: "",
          enforce_uniform_mode: false,
        },
      ],
    },
    mold: {
      moldDetectionEnabled: true,
      moldPreventionEnabled: true,
      moldPreventionDehumidificationEnabled: true,
    },
    notifications: { notificationsEnabled: true, moldPreventionEnabled: true },
    learning: { rooms: { sala: { area_id: "sala", devices: [{}], temperature_sensor: "s" } } },
    "head-offset": {},
    "heating-system": {
      budgetEnabled: true,
      boilerEntity: "climate.boiler",
      bypassEntities: ["switch.b"],
    },
  };
  for (const name of NAMES) {
    const p = new panels[name]();
    p.hass = hass;
    Object.assign(p, props[name]);
    p.dispatchEvent = (e) => {
      if (e.type === "setting-changed") emitted.push({ panel: name, ...e.detail });
      return true;
    };
    for (const fn of handlers(p.render())) {
      for (const detail of [true, false, { value: 7 }, { value: "off" }]) {
        try {
          fn({
            detail,
            target: { value: "5", checked: true },
            currentTarget: { value: "5" },
            stopPropagation() {},
            preventDefault() {},
          });
        } catch {
          /* handlers that need a real DOM event */
        }
      }
    }
  }
  return emitted;
}

const FORBIDDEN = [
  "price_entity",
  "coil_dry_enabled",
  "coil_dry_minutes",
  "coil_dry_mode",
  "coil_dry_fan_mode",
  "coil_dry_min_cooling_minutes",
  "coil_dry_drain_minutes",
  "mold_f_rsi",
  "control_mode",
  "mold_prevention_intensity",
  "mold_prevention_reheat_enabled",
];

test("touching every settings panel saves no key the fork's backend rejects or drops", () => {
  const emitted = touchEveryPanel();
  const keys = new Set(emitted.map((e) => e.key));
  for (const bad of ["controlMode", "moldFRsi", "moldPreventionIntensity", "priceEntity"])
    assert.equal(keys.has(bad), false, bad);
  const s = new Settings();
  s.hass = hass;
  s._autoSave = () => {};
  for (const e of emitted) s._onSettingChanged({ detail: { key: e.key, value: e.value } });
  const payload = s._buildPayload();
  for (const bad of FORBIDDEN) assert.equal(bad in payload, false, bad);
});

test("the fork's own settings are reachable from their panels and land in the payload", () => {
  const emitted = touchEveryPanel();
  const s = new Settings();
  s.hass = hass;
  s._autoSave = () => {};
  for (const e of emitted) s._onSettingChanged({ detail: { key: e.key, value: e.value } });
  const keys = new Set(emitted.map((e) => e.key));
  for (const [field, payloadKey] of [
    ["temperatureRoundingMode", "temperature_rounding_mode"],
    ["acHeadOffsetEnabled", "ac_head_offset_enabled"],
    ["moldPreventionSustainedMinutes", "mold_prevention_sustained_minutes"],
    ["moldPreventionDehumidificationEnabled", "mold_prevention_dehumidification_enabled"],
    ["moldPreventionDryMinTemperature", "mold_prevention_dry_min_temperature"],
    ["windowOpenNotificationMinutes", "window_open_notification_minutes"],
    ["bypassChildLock", "hydraulic_bypass_child_lock"],
    ["budgetEnabled", "power_budget_enabled"],
  ]) {
    assert.ok(keys.has(field), `${field} emitted (got ${[...keys].join(",")})`);
    assert.ok(payloadKey in s._buildPayload(), payloadKey);
  }
});
