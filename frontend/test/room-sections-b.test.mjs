import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createServer } from "vite";

let server, RoomDetail, SensorSection, ScheduleSettings, Comfort, NumberField, Insights;
before(async () => {
  globalThis.window ??= { addEventListener() {}, removeEventListener() {} };
  server = await createServer({ configFile: false, server: { middlewareMode: true } });
  ({ RsRoomDetail: RoomDetail } = await server.ssrLoadModule("/src/components/rs-room-detail.ts"));
  ({ RsSensorSection: SensorSection } = await server.ssrLoadModule(
    "/src/components/rs-sensor-section.ts",
  ));
  ({ RsScheduleSettings: ScheduleSettings } = await server.ssrLoadModule(
    "/src/components/rs-schedule-settings.ts",
  ));
  ({ RsComfortSection: Comfort } = await server.ssrLoadModule(
    "/src/components/rs-comfort-section.ts",
  ));
  ({ RsNumberField: NumberField } = await server.ssrLoadModule(
    "/src/components/shared/rs-number-field.ts",
  ));
  ({ RsRoomInsights: Insights } = await server.ssrLoadModule(
    "/src/components/rs-room-insights.ts",
  ));
});
after(async () => {
  await server?.close();
});

const hass = {
  language: "en",
  areas: { sala: { area_id: "sala", name: "Sala" } },
  states: {
    "sensor.voc_index": {
      entity_id: "sensor.voc_index",
      state: "120",
      attributes: { device_class: "pm25", unit_of_measurement: "idx" },
    },
    "sensor.air_quality_1": { entity_id: "sensor.air_quality_1", state: "3", attributes: {} },
    "sensor.hum": {
      entity_id: "sensor.hum",
      state: "55",
      attributes: { device_class: "humidity" },
    },
    "binary_sensor.win": {
      entity_id: "binary_sensor.win",
      state: "off",
      attributes: { device_class: "window" },
    },
    "fan.vent": { entity_id: "fan.vent", state: "on", attributes: {} },
    "sensor.co2": {
      entity_id: "sensor.co2",
      state: "900",
      attributes: { device_class: "carbon_dioxide" },
    },
  },
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

function roomDetail() {
  const detail = new RoomDetail();
  detail.hass = hass;
  detail.area = hass.areas.sala;
  detail.config = {
    area_id: "sala",
    climate_mode: "auto",
    devices: [{ entity_id: "climate.ac", type: "ac", role: "auto" }],
    schedules: [],
    live: {},
  };
  detail._initFromConfig();
  detail._autoSave = () => {};
  return detail;
}

const sensorChanged = (key, value) => ({ detail: { key, value } });

test("each air field edited through the room page lands in the save payload", () => {
  const detail = roomDetail();
  for (const [key, value] of [
    ["co2_sensor", "sensor.co2"],
    ["co2_threshold", 1200],
    ["voc_sensor", "sensor.voc_index"],
    ["voc_threshold", 0.005],
    ["ventilation_entity", "fan.vent"],
  ]) {
    detail._onSensorChanged(sensorChanged(key, value));
    assert.equal(detail._buildRoomPayload()[key], value, key);
  }
  detail._onSensorChanged(sensorChanged("voc_threshold", null));
  assert.equal(detail._buildRoomPayload().voc_threshold, null, "VOC threshold cleared");
  // The fork's own sensor keys still land too
  detail._onSensorChanged(sensorChanged("keep_fan_only_on_window_open", false));
  detail._onSensorChanged(sensorChanged("mold_f_rsi", 0.7));
  const payload = detail._buildRoomPayload();
  assert.equal(payload.keep_fan_only_on_window_open, false);
  assert.equal(payload.mold_f_rsi, 0.7);
  for (const key of ["occupancy_eco_enabled", "occupancy_eco_delay"])
    assert.equal(key in payload, false, key);
});

function sensors(extra = {}) {
  const s = new SensorSection();
  s.hass = hass;
  s.area = hass.areas.sala;
  s.editing = true;
  Object.assign(s, extra);
  const fired = [];
  s.dispatchEvent = (e) => (fired.push(e.detail), true);
  return { s, fired };
}

test("the VOC picker offers any sensor and its threshold keeps the fork's precision", () => {
  const { s, fired } = sensors({ vocSensor: "sensor.voc_index", vocThreshold: 0.5 });
  // Upstream's filter (VOC classes or "voc" in an unclassified id) would reject both
  assert.equal(s._accepts("voc", "sensor.voc_index"), true);
  assert.equal(s._accepts("voc", "sensor.air_quality_1"), true);
  const tpl = s._renderVocSettings("en");
  const onChange = handlers(tpl)[0];
  onChange({ target: { value: "0.005" } });
  onChange({ target: { value: "" } });
  assert.deepEqual(fired, [
    { key: "voc_threshold", value: 0.005 },
    { key: "voc_threshold", value: null },
  ]);
});

test("the sensor dialog emits the fork's keys: keep-fan-only and wall factor reachable, no occupancy eco", () => {
  const { s, fired } = sensors({
    humiditySensor: "sensor.hum",
    windowSensors: new Set(["binary_sensor.win"]),
    occupancySensors: new Set(["binary_sensor.win"]),
    co2Sensor: "sensor.co2",
    vocSensor: "sensor.voc_index",
    moldFRsi: 0.8,
  });
  const tpl = s.render();
  for (const fn of handlers(tpl))
    for (const detail of [true, { value: 0.75 }]) {
      try {
        fn({ detail, target: { value: "0.7" }, stopPropagation() {} });
      } catch {
        /* handlers needing a real DOM event */
      }
    }
  const keys = new Set(fired.map((d) => d?.key).filter(Boolean));
  for (const key of [
    "keep_fan_only_on_window_open",
    "mold_f_rsi",
    "window_open_delay",
    "co2_threshold",
  ])
    assert.ok(keys.has(key), `${key} (got ${[...keys]})`);
  for (const key of keys) assert.equal(key.startsWith("occupancy_eco"), false, key);
});

test("the ventilation row reads the fork's air_ventilation_active", () => {
  const { s } = sensors({
    editing: false,
    co2Sensor: "sensor.co2",
    ventilationEntity: "fan.vent",
    live: { air_ventilation_active: true },
  });
  const text = flat(s._renderAirRows());
  assert.ok(text.includes("running for the air quality"), text);
  const off = sensors({
    editing: false,
    co2Sensor: "sensor.co2",
    ventilationEntity: "fan.vent",
    live: { ventilation_active: true },
  }).s;
  assert.notEqual(flat(off._renderAirRows()), text, "upstream's field is not read");
});

test("the schedule card sends no pre-heat, follow-device, price or editor event; rows open their dialog", () => {
  const sch = new ScheduleSettings();
  sch.hass = hass;
  sch.schedules = [];
  const fired = [];
  sch.dispatchEvent = (e) => (fired.push(e), true);
  for (const editing of [false, true]) {
    sch.editing = editing;
    for (const fn of handlers(sch.render())) {
      try {
        fn({ detail: true, stopPropagation() {}, target: {} });
      } catch {
        /* handlers needing a real DOM event */
      }
    }
  }
  const names = new Set(fired.map((e) => e.type));
  for (const bad of ["preheat-changed", "follow-device-setpoint-changed", "open-schedule-editor"])
    assert.equal(names.has(bad), false, bad);
  const parts = fired.filter((e) => e.type === "edit-click").map((e) => e.detail.part);
  assert.ok(parts.includes("schedule") && parts.includes("temperatures"), parts.join());
  assert.equal(parts.includes("price"), false);
});

test("comfort/eco from the temperatures dialog and the schedule toggles land in the payload", () => {
  const detail = roomDetail();
  detail._onScheduleEditClick({ stopPropagation() {}, detail: { part: "temperatures" } });
  assert.equal(detail._editing, "temperatures");
  const dialog = detail._renderEditDialog();
  assert.ok(flat(dialog).includes("<rs-target-temps"), "temperatures dialog");
  detail._onComfortHeatChanged({ detail: { value: 22.5 } });
  detail._onEcoCoolChanged({ detail: { value: 28 } });
  detail._onPreconditioningToggle({ detail: true });
  const payload = detail._buildRoomPayload();
  assert.equal(payload.comfort_heat, 22.5);
  assert.equal(payload.eco_cool, 28);
  assert.equal(payload.preconditioning_enabled, true);
});

test("schedule status texts carry the unit once, no placeholder left", () => {
  const sch = new ScheduleSettings();
  sch.schedules = [{ entity_id: "schedule.sala" }];
  sch.activeScheduleIndex = 0;
  const texts = [
    { state: "on", attributes: { temperature: 21 } },
    { state: "on", attributes: {} },
    { state: "off", attributes: {} },
  ].map((st) => {
    sch.hass = { ...hass, states: { "schedule.sala": { entity_id: "schedule.sala", ...st } } };
    return sch._getStatusText(0, "active");
  });
  for (const t of texts) {
    assert.equal(t.includes("{"), false, t);
    assert.equal((t.match(/°C/g) ?? []).length, 1, t);
  }
});

test("the CO2 threshold keeps any whole ppm the backend accepts (825 stays 825)", () => {
  const { s } = sensors({ co2Sensor: "sensor.co2", co2Threshold: 1000 });
  const steps = bindings(s._renderCo2Settings("en"), "<rs-number-field", ".step");
  assert.deepEqual(steps, [1]);
});

// ── Comfort and profiles in the 2.0 controls: same setting-changed events ──

function comfort(props = {}) {
  const c = new Comfort();
  Object.assign(c, { hass, climateMode: "auto", profileTargets: {} }, props);
  const events = [];
  c.dispatchEvent = (e) => {
    events.push(e.detail);
    return true;
  };
  return { c, events };
}

const stop = (detail) => ({ detail, stopPropagation() {} });

test("comfort: a profile is picked and picking the active one again clears it", () => {
  const { c, events } = comfort();
  const [pick] = bindings(c.render(), "<rs-segmented", "@value-changed");
  pick(stop({ value: "work" }));
  const reselect = comfort({ activeProfile: "work" });
  bindings(reselect.c.render(), "<rs-segmented", "@value-changed")[0](stop({ value: "work" }));
  assert.deepEqual(events, [{ key: "active_profile", value: "work" }]);
  assert.deepEqual(reselect.events, [{ key: "active_profile", value: "" }]);
  assert.deepEqual(
    bindings(c.render(), "<rs-segmented", ".options")[0].map((o) => o.value),
    ["", "work", "sleep", "guests", "away"],
  );
});

test("comfort: the profile targets stay visible in the field's hint", () => {
  const { c } = comfort({ profileTargets: { work: { heat_target: 19.5, cool_target: 24 } } });
  const [hint] = bindings(c.render(), "<rs-field", ".hint");
  assert.match(hint, /Work 19[.,]5 – 24[.,]0°C/);
});

test("comfort: the night switch and fields send the same keys, ranges from the backend", () => {
  const { c, events } = comfort({ nightModeEnabled: true });
  const tree = c.render();
  bindings(tree, "<rs-list-row", "@toggle-changed")[0]({ detail: false });
  const times = bindings(tree, "<ha-textfield", "@change");
  times[0]({ target: { value: "23:15" } });
  times[1]({ target: { value: "06:30" } });
  const numbers = bindings(tree, "<rs-number-field", "@value-changed");
  numbers[0]({ detail: { value: -1.5 } });
  numbers[1]({ detail: { value: 0.8 } });
  numbers[2]({ detail: { value: 12 } });
  assert.deepEqual(events, [
    { key: "night_mode_enabled", value: false },
    { key: "night_start", value: "23:15" },
    { key: "night_end", value: "06:30" },
    { key: "night_heat_delta", value: -1.5 },
    { key: "night_cool_delta", value: 0.8 },
    { key: "night_ramp_minutes", value: 12 },
  ]);
  const range = (name) => bindings(tree, "<rs-number-field", name);
  assert.deepEqual(range(".min"), [-5, 0, 0]);
  assert.deepEqual(range(".max"), [0, 5, 240]);
  // ramp step 1: a 12-minute ramp stays 12 (the old input's step was 5)
  assert.deepEqual(range(".step"), [0.1, 0.1, 1]);
});

test("comfort: night fields round to their step (−0.27 → −0.3) and a ramp of 12 stays 12", () => {
  const commit = (props, typed) => {
    const f = new NumberField();
    Object.assign(f, { value: 0 }, props);
    const out = [];
    f.dispatchEvent = (e) => {
      out.push(e.detail.value);
      return true;
    };
    f._onChange({ stopPropagation() {}, target: { value: typed } });
    return out;
  };
  assert.deepEqual(commit({ min: -5, max: 0, step: 0.1 }, "-0.27"), [-0.3]);
  assert.deepEqual(commit({ min: -5, max: 0, step: 0.1 }, "-9"), [-5]);
  assert.deepEqual(commit({ min: 0, max: 240, step: 1 }, "12"), [12]);
});

// Values bound to `name` on the element `tag` itself (its open tag is the last one before)
function own(value, tag, name, out = []) {
  if (Array.isArray(value)) value.forEach((v) => own(v, tag, name, out));
  else if (value && typeof value === "object" && value.strings) {
    value.values.forEach((v, i) => {
      const before = value.strings.slice(0, i + 1).join(" ");
      if (
        before.trimEnd().endsWith(name + "=") &&
        before.lastIndexOf("<") === before.lastIndexOf(tag)
      )
        out.push(v);
      own(v, tag, name, out);
    });
  }
  return out;
}

// ── Room insights as 2.0 list cards: same texts, same conditions ──
test("room insights render as list cards with rows, not an ha-card", () => {
  const i = new Insights();
  i.hass = hass;
  i.decisionReasons = ["window_open"];
  i.comfortScore = {
    score: 82,
    label: "fair",
    factors: {},
    breakdown: { temperature: { penalty: 18, status: "off_target" } },
  };
  i.readiness = {
    level: "partial",
    ready_count: 1,
    total_count: 2,
    items: [
      { key: "temperature", status: "ready" },
      { key: "window", status: "missing" },
    ],
  };
  const tree = i.render();
  const text = flat(tree);
  assert.ok(!text.includes("<ha-card"), "no ha-card wrapper");
  assert.equal(own(tree, "<rs-list-card", ".heading").length, 3);
  const headings = own(tree, "<rs-list-row", ".heading");
  assert.ok(headings.includes("Comfort 82%"), headings.join("|"));
  assert.ok(
    headings.some((h) => /window/i.test(h)),
    headings.join("|"),
  );
  assert.deepEqual(own(tree, "<rs-list-row", ".value"), ["−18", "82/100"]);
  const empty = new Insights();
  empty.hass = hass;
  const bare = empty.render();
  assert.equal(own(bare, "<rs-list-card", ".heading").length, 1, "no readiness, no score");
  assert.ok(own(bare, "<rs-list-row", ".heading").length === 1, "idle reason only");
});
