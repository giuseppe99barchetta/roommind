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

test("the pre-heat line: up to the horizon from the default weight, a limit below it", async () => {
  const { preheatLeadHours } = await server.ssrLoadModule("/src/utils/constants.ts");
  assert.equal(preheatLeadHours(70), null);
  assert.equal(preheatLeadHours(100), null);
  assert.equal(preheatLeadHours(35), 6);
  assert.equal(preheatLeadHours(0), 0);
});

test("learn faster stays available while a learned room waits (outdoor sensor gone) or is paused", () => {
  const room = {
    area_id: "sala",
    devices: [{}],
    temperature_sensor: "sensor.t",
    live: { n_observations: 400, learning_paused_reason: "outdoor_unavailable", confidence: 0.5 },
  };
  for (const disabled of [[], ["sala"]]) {
    const p = new panels.learning();
    p.hass = hass;
    p.rooms = { sala: room };
    p.learningDisabledRooms = disabled;
    const disabledBindings = [];
    (function walk(v) {
      if (Array.isArray(v)) return v.forEach(walk);
      if (!v || typeof v !== "object" || !v.strings) return;
      v.strings.forEach((s, i) => {
        if (v.strings.join("").includes("<rs-icon-button") && s.trimEnd().endsWith(".disabled="))
          disabledBindings.push(v.values[i]);
      });
      v.values.forEach(walk);
    })(p._renderRoom("sala", "Sala", room));
    assert.deepEqual(disabledBindings, [false], `paused=${disabled.length > 0}`);
  }
});

test("learn faster is not offered before the room has a model", () => {
  const room = { area_id: "sala", devices: [{}], temperature_sensor: "sensor.t", live: {} };
  const p = new panels.learning();
  p.hass = hass;
  p.rooms = { sala: room };
  const tpl = p._renderRoom("sala", "Sala", room);
  const found = [];
  (function walk(v) {
    if (Array.isArray(v)) return v.forEach(walk);
    if (!v || typeof v !== "object" || !v.strings) return;
    v.strings.forEach((s, i) => {
      if (v.strings.join("").includes("<rs-icon-button") && s.trimEnd().endsWith(".disabled="))
        found.push(v.values[i]);
    });
    v.values.forEach(walk);
  })(tpl);
  assert.deepEqual(found, [true]);
});

// ── Safety preview in the 2.0 controls: same request, mode change clears the result ──
test("safety preview: segmented mode, a button that runs the same read-only request, rows", async () => {
  const mod = await server.ssrLoadModule("/src/components/settings/rs-settings-preview.ts");
  const p = new mod.RsSettingsPreview();
  const calls = [];
  p.hass = {
    ...hass,
    callWS: async (msg) => {
      calls.push(msg);
      return {
        read_only: true,
        mode: msg.mode,
        house_available_watts: 1234.4,
        power_sensor_healthy: true,
        power_sensor_age_seconds: 12,
        boiler_state: "idle",
        bypass_acknowledged: false,
        boiler_demand_rooms: [],
        rooms: {
          living_room: {
            watts: 800,
            source: "learned",
            samples: 3,
            already_running: false,
            would_allow: true,
            reason: "eligible",
            current_decision_reasons: ["window_open"],
          },
        },
      };
    },
  };
  const view = p.render();
  const text = JSON.stringify(view.strings);
  assert.ok(!text.includes("<select") && !text.includes("<button"), "no native select/button");
  const [pick] = handlers(view).filter((fn) => String(fn).includes("_mode"));
  pick({ detail: { value: "heating" }, stopPropagation() {} });
  assert.equal(p._mode, "heating");
  await p._refresh();
  assert.deepEqual(calls, [{ type: "roommind/control/preview", mode: "heating" }]);
  const rows = JSON.stringify(p.render(), (k, v) => (typeof v === "function" ? undefined : v));
  assert.ok(rows.includes("1234 W"), rows);
  assert.ok(rows.includes("living room"), rows);
  assert.ok(rows.includes("800 W"), rows);
  // a new mode drops the old result, as the select did
  handlers(p.render()).filter((fn) => String(fn).includes("_mode"))[0]({
    detail: { value: "dry" },
    stopPropagation() {},
  });
  assert.equal(p._result, undefined);
});
