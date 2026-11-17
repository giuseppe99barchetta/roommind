import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createServer } from "vite";

let server, RoomDetail, DeviceSection, HeatSource;
before(async () => {
  globalThis.window ??= { addEventListener() {}, removeEventListener() {} };
  server = await createServer({ configFile: false, server: { middlewareMode: true } });
  ({ RsRoomDetail: RoomDetail } = await server.ssrLoadModule("/src/components/rs-room-detail.ts"));
  ({ RsDeviceSection: DeviceSection } = await server.ssrLoadModule(
    "/src/components/rs-device-section.ts",
  ));
  ({ RsHeatSourceSection: HeatSource } = await server.ssrLoadModule(
    "/src/components/rs-heat-source-section.ts",
  ));
});
after(async () => {
  await server?.close();
});

const hass = {
  language: "en",
  areas: { sala: { area_id: "sala", name: "Sala" } },
  states: {
    "climate.ac": {
      entity_id: "climate.ac",
      state: "cool",
      attributes: { hvac_modes: ["off", "cool", "heat", "fan_only"], fan_modes: ["low", "high"] },
    },
    "climate.trv": {
      entity_id: "climate.trv",
      state: "heat",
      attributes: { hvac_modes: ["heat"] },
    },
  },
  entities: {},
  devices: {},
  config: { unit_system: { temperature: "°C" } },
  callWS: async () => ({}),
};

const UPSTREAM_ONLY_DEVICE = [
  "coil_dry",
  "coil_dry_mode",
  "coil_dry_minutes",
  "coil_dry_fan_mode",
  "setpoint_offset",
  "setback_auto_off",
];

/** Every function bound in a template tree (event handlers). */
function handlers(value, out = []) {
  if (typeof value === "function") out.push(value);
  else if (Array.isArray(value)) value.forEach((v) => handlers(v, out));
  else if (value && typeof value === "object" && value.strings) handlers(value.values, out);
  return out;
}

/** Values bound to `.name=` on the templates whose markup holds `tag`. */
function bindings(value, tag, name, out = []) {
  if (Array.isArray(value)) value.forEach((v) => bindings(v, tag, name, out));
  else if (value && typeof value === "object" && value.strings) {
    if (value.strings.join("").includes(tag))
      value.strings.forEach((s, i) => {
        if (s.trimEnd().endsWith(name + "=")) out.push(value.values[i]);
      });
    bindings(value.values, tag, name, out);
  }
  return out;
}

function flat(value) {
  if (value == null) return "";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.map(flat).join("");
  if (value.strings) return value.strings.join("") + value.values.map(flat).join("");
  return "";
}

function section(devices, extra = {}) {
  const s = new DeviceSection();
  s.hass = hass;
  s.area = hass.areas.sala;
  s.devices = devices;
  s.selectedTempSensor = "sensor.t";
  s.editing = true;
  Object.assign(s, extra);
  const fired = [];
  s.dispatchEvent = (e) => (fired.push(e), true);
  return { s, fired };
}

test("idle actions per type are the fork's: TRV off/low, AC off/fan-only (when supported)/setback", () => {
  const { s } = section([
    { entity_id: "climate.trv", type: "trv", role: "auto", idle_action: "low" },
    { entity_id: "climate.ac", type: "ac", role: "auto" },
  ]);
  const opts = (d) =>
    bindings(s._renderIdleGroup(d), "<rs-segmented", ".options")[0].map((o) => o.value);
  assert.deepEqual(opts(s.devices[0]), ["off", "low"]);
  assert.deepEqual(opts(s.devices[1]), ["off", "fan_only", "setback"]);
  const noFan = { ...hass.states["climate.ac"], attributes: { hvac_modes: ["off", "cool"] } };
  s.hass = { ...hass, states: { ...hass.states, "climate.ac": noFan } };
  assert.deepEqual(opts(s.devices[1]), ["off", "setback"]);
  s.hass = hass;
  // An existing TRV "low" stays selected and its hint shows
  const trv = s._renderIdleGroup(s.devices[0]);
  assert.equal(bindings(trv, "<rs-segmented", ".value")[0], "low");
  assert.ok(flat(trv).includes('class="note"'), "low hint rendered");
});

test("an AC's detail reaches the fork's power sensor, fan-only conditions and seasons", () => {
  const ac = {
    entity_id: "climate.ac",
    type: "ac",
    role: "auto",
    idle_action: "fan_only",
    idle_fan_mode: "low",
    fan_only_seasons: ["summer"],
  };
  const { s, fired } = section([ac]);
  const tpl = s._renderDeviceDetail(ac);
  // Every control in the detail, fired: only fork keys change, never an upstream-only one
  for (const fn of handlers(tpl)) {
    for (const detail of [true, false, { value: "sensor.ac_power" }]) {
      try {
        fn({ detail, target: { value: "" }, stopPropagation() {}, preventDefault() {} });
      } catch {
        /* handlers that need a real DOM event */
      }
    }
  }
  const changed = new Set();
  for (const e of fired.filter((e) => e.type === "device-changed"))
    for (const d of e.detail.devices) {
      for (const key of UPSTREAM_ONLY_DEVICE) assert.equal(key in d, false, key);
      for (const [k, v] of Object.entries(d))
        if (JSON.stringify(v) !== JSON.stringify(ac[k])) changed.add(k);
    }
  for (const key of [
    "power_sensor_entity_id",
    "fan_only_only_after_cooling",
    "fan_only_require_presence",
    "fan_only_require_schedule",
    "fan_only_seasons",
  ])
    assert.ok(changed.has(key), `${key} editable (changed: ${[...changed]})`);
});

test("a TRV set to low survives a device edit and the room save", () => {
  const detail = new RoomDetail();
  detail.hass = hass;
  detail.area = hass.areas.sala;
  detail.config = {
    area_id: "sala",
    climate_mode: "auto",
    devices: [
      { entity_id: "climate.trv", type: "trv", role: "auto", idle_action: "low" },
      { entity_id: "climate.ac", type: "ac", role: "auto", idle_action: "fan_only" },
    ],
  };
  detail._initFromConfig();
  const { s, fired } = section(detail._devices);
  s._onPowerSensorChange("climate.ac", "sensor.ac_power");
  detail._onDeviceChanged(fired[0]);
  const payload = detail._buildRoomPayload();
  const trv = payload.devices.find((d) => d.entity_id === "climate.trv");
  const ac = payload.devices.find((d) => d.entity_id === "climate.ac");
  assert.equal(trv.idle_action, "low");
  assert.equal(ac.power_sensor_entity_id, "sensor.ac_power");
  for (const d of payload.devices)
    for (const key of UPSTREAM_ONLY_DEVICE) assert.equal(key in d, false, key);
});

test("a device row on the room page opens the devices dialog on that device", () => {
  const detail = new RoomDetail();
  detail.hass = hass;
  detail.area = hass.areas.sala;
  detail.config = {
    area_id: "sala",
    climate_mode: "auto",
    devices: [{ entity_id: "climate.ac", type: "ac", role: "auto" }],
  };
  detail._initFromConfig();
  detail._onDevicesEditClick({ stopPropagation() {}, detail: { entityId: "climate.ac" } });
  assert.equal(detail._editing, "devices");
  assert.equal(
    bindings(detail._renderEditDialog(), "<rs-device-section", ".focusEntity")[0],
    "climate.ac",
  );
});

const FORK_HEAT_KEYS = [
  "heat_source_orchestration",
  "heat_pump_power_watts",
  "native_heat_source",
  "heat_source_outdoor_threshold",
  "heat_source_primary_delta",
  "heat_source_ac_min_outdoor",
  "heat_source_boiler_outdoor_threshold",
  "heat_source_heat_pump_outdoor_threshold",
  "heat_source_hybrid_delta",
];

test("the heat source section emits the fork's keys only, native and legacy rules both reachable", () => {
  const keys = new Set();
  for (const native of [false, true]) {
    const hs = new HeatSource();
    hs.hass = hass;
    hs.editing = true;
    hs.enabled = true;
    hs.hasAc = true;
    hs.hasTrv = true;
    hs.native = native;
    hs.dispatchEvent = (e) => (keys.add(e.detail.key), true);
    for (const fn of handlers(hs.render())) fn({ detail: { value: 3 }, stopPropagation() {} });
  }
  assert.deepEqual([...keys].sort(), [...FORK_HEAT_KEYS].sort());
});
