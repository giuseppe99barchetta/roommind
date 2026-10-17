import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createServer } from "vite";

let server, Section, RoomDetail, Sensors, Devices;
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true } });
  ({ RsDehumidifierSection: Section } = await server.ssrLoadModule("/src/components/rs-dehumidifier-section.ts"));
  ({ RsRoomDetail: RoomDetail } = await server.ssrLoadModule("/src/components/rs-room-detail.ts"));
  ({ RsSensorSection: Sensors } = await server.ssrLoadModule("/src/components/rs-sensor-section.ts"));
  ({ RsDeviceSection: Devices } = await server.ssrLoadModule("/src/components/rs-device-section.ts"));
});
after(async () => { await server?.close(); });

const config = {
  entity_id: "humidifier.bed", served_area_ids: ["bath", "office"], mode: "manual",
  min_run_minutes: 7, min_off_minutes: 9, power_watts: 230,
};

test("unrelated room saves preserve shared registration and humidity settings", async () => {
  const detail = new RoomDetail();
  const writes = [];
  detail.hass = { language: "en", callWS: async (payload) => { writes.push(payload); } };
  detail.area = { area_id: "bed" };
  detail.config = {
    area_id: "bed", devices: [], dehumidifier: config, humidity_comfort_enabled: false,
    humidity_target: 58, humidity_tolerance: 6, humidity_priority: "energy",
  };
  detail.dispatchEvent = () => true;
  detail._initFromConfig();
  detail._displayName = "Bedroom";
  await detail._doSave();
  assert.equal(writes.length, 1);
  assert.deepEqual(writes[0].dehumidifier, config);
  assert.equal(writes[0].humidity_comfort_enabled, false);
  assert.equal(writes[0].humidity_target, 58);
  assert.equal(writes[0].humidity_tolerance, 6);
  assert.equal(writes[0].humidity_priority, "energy");
});

test("selecting a physical device neither enables comfort nor changes served rooms", () => {
  const section = new Section();
  section.config = config;
  const events = [];
  section.dispatchEvent = (event) => { events.push(event); return true; };
  section._selectDevice({ detail: "switch.new", stopPropagation() {} });
  assert.equal(events.length, 1);
  assert.equal(events[0].type, "dehumidifier-changed");
  assert.deepEqual(events[0].detail, { ...config, entity_id: "switch.new" });
  section._selectDevice({ detail: "", stopPropagation() {} });
  assert.equal(events[1].detail, null);
});

test("new registrations default to automatic control with five minute protections", () => {
  const section = new Section();
  let change;
  section.dispatchEvent = (event) => { change = event.detail; return true; };
  section._selectDevice({ detail: "switch.new", stopPropagation() {} });
  assert.deepEqual(change, {
    entity_id: "switch.new", served_area_ids: [], mode: "auto", min_run_minutes: 5, min_off_minutes: 5, power_watts: 0,
  });
});

function renderedText(value) {
  if (value == null || typeof value === "symbol" || typeof value === "function") return "";
  if (Array.isArray(value)) return value.map(renderedText).join(" ");
  if (value.strings) return `${value.strings.join(" ")} ${value.values.map(renderedText).join(" ")}`;
  return String(value);
}

test("an unassigned device has a visible action that opens the humidity editor", () => {
  const section = new Section();
  section.hass = { language: "it", states: {}, areas: {} };
  section.humidity = { humidity_comfort_enabled: false, humidity_target: 55 };
  const detail = new RoomDetail();
  detail.hass = section.hass;
  detail.area = { area_id: "bed" };
  const events = [];
  section.dispatchEvent = (event) => {
    events.push(event);
    detail._openEdit("dehumidifier")();
    return true;
  };

  const view = section.render();
  assert.ok(renderedText(view).includes("Aggiungi deumidificatore"));
  const click = view.values.find((_, i) => view.strings[i].trimEnd().endsWith("@click="));
  assert.equal(typeof click, "function");
  click();
  assert.equal(events[0].type, "edit-click");
  assert.equal(events[0].bubbles, true);
  assert.equal(events[0].composed, true);
  assert.equal(detail._editing, "dehumidifier");
  assert.ok(renderedText(detail._renderEditDialog()).includes("rs-dehumidifier-section"));
  assert.equal(section.config, null);
  assert.equal(section.humidity.humidity_comfort_enabled, false);
});

test("local and shared devices offer configuration even with humidity comfort disabled", () => {
  const section = new Section();
  section.hass = { language: "en", states: {}, areas: {} };
  section.humidity = { humidity_comfort_enabled: false, humidity_target: 55 };
  section.config = config;
  assert.ok(renderedText(section.render()).includes("Configure dehumidifier"));
  section.config = null;
  section.live = { devices: [{
    entity_id: "switch.hall", owner_area_id: "hall", served_area_ids: ["bed"],
    state: "off", action: null, available: true, commanded: null, pending_rooms: [],
  }] };
  assert.ok(renderedText(section.render()).includes("Configure dehumidifier"));
  section.editing = true;
  const editor = renderedText(section.render());
  assert.ok(editor.includes("rs-entity-picker-field"));
  assert.ok(!editor.includes('class="configure"'));
});

test("observed switch on is distinct from drying and host constraints remain visible", () => {
  const section = new Section();
  section.hass = { language: "en", states: {}, areas: {} };
  section.humidity = { humidity_comfort_enabled: true, humidity_target: 55 };
  section.live = {
    request: "comfort", assigned_entity_id: null, devices: [{
      entity_id: "switch.bed", owner_area_id: "bed", served_area_ids: ["bed", "bath"],
      state: "on", action: null, available: true, reason: "humidity_floor", commanded: false,
      requesting_rooms: [], pending_rooms: ["bath"], target_humidity: 45, humidity_floor: 45,
    }],
  };
  const text = renderedText(section.render());
  assert.ok(text.includes("Host humidity limit reached"));
  assert.ok(text.includes("Turn-off command sent"));
  assert.ok(text.includes("Requests from"));
  assert.ok(text.includes("bath"));
  assert.ok(!text.includes("Dehumidifying"));
  section.live.devices[0].action = "drying";
  assert.ok(renderedText(section.render()).includes("Dehumidifying"));
});

test("editing presents indoor beneficiary choices and preserves an independent comfort opt-in", () => {
  const section = new Section();
  section.hass = { language: "en", states: {}, areas: {} };
  section.config = config;
  section.areaId = "bed";
  section.editing = true;
  section.humidity = { humidity_comfort_enabled: false, humidity_target: 55, humidity_tolerance: 5, humidity_priority: "balanced" };
  section.rooms = { bed: {}, bath: { display_name: "Bathroom" }, garden: { display_name: "Garden", is_outdoor: true } };
  const text = renderedText(section.render());
  assert.ok(text.includes("Bathroom"));
  assert.ok(!text.includes("Garden"));
  assert.ok(text.includes("Adding a device does not enable comfort automatically"));
});

function templates(value) {
  if (Array.isArray(value)) return value.flatMap(templates);
  if (!value?.strings) return [];
  return [value, ...value.values.flatMap(templates)];
}

function clickChoice(view, label) {
  const choice = templates(view).find(t =>
    t.strings.join("").includes('class="choice"') && t.values.includes(label));
  assert.ok(choice, `Missing choice: ${label}`);
  choice.values.find((_, i) => choice.strings[i].trimEnd().endsWith("@click="))();
}

test("automatic and manual choices preserve device protections and do not opt into comfort", () => {
  const section = new Section();
  section.hass = { language: "it", states: {}, areas: {} };
  section.areaId = "bed";
  section.config = config;
  section.editing = true;
  section.humidity = { humidity_comfort_enabled: false, humidity_target: 55, humidity_tolerance: 5, humidity_priority: "balanced" };
  const events = [];
  section.dispatchEvent = event => { events.push(event); return true; };
  clickChoice(section.render(), "Automatico");
  assert.equal(events[0].type, "dehumidifier-changed");
  assert.deepEqual(events[0].detail, { ...config, mode: "auto" });
  clickChoice(section.render(), "Manuale");
  assert.deepEqual(events[1].detail, config);
  clickChoice(section.render(), "Risparmio energetico");
  assert.equal(events[2].type, "humidity-changed");
  assert.deepEqual(events[2].detail, { humidity_priority: "energy" });
  assert.equal(section.humidity.humidity_comfort_enabled, false);
});

test("disabled automation explains both climate switches and identifies the host room", () => {
  const section = new Section();
  section.hass = { language: "it", states: {}, areas: {} };
  section.humidity = { humidity_comfort_enabled: true, humidity_target: 55 };
  section.currentHumidity = 61;
  section.rooms = { hall: { display_name: "Corridoio" } };
  section.live = { devices: [{
    entity_id: "humidifier.hall", owner_area_id: "hall", served_area_ids: ["hall", "bed"],
    state: "off", action: null, available: true, reason: "disabled", commanded: null,
    target_humidity: 45, humidity_floor: 45, pending_rooms: [],
  }] };
  const text = renderedText(section.render());
  assert.ok(text.includes("Comfort attivo"));
  assert.ok(text.includes("impostazioni generali e nella stanza ospitante, Corridoio"));
  assert.ok(text.includes("61") && text.includes("55") && text.includes("45"));
  assert.ok(text.includes("Può essere diverso dal target comfort"));

  section.editing = true;
  section.live = undefined;
  section.config = config;
  for (const [global, room] of [[false, true], [true, false], [true, true]]) {
    section.climateControlActive = global;
    section.roomControlEnabled = room;
    const view = renderedText(section.render());
    assert.equal(view.includes("Controllo automatico disabilitato"), !global || !room);
  }
});

test("shared-only rooms explain where to manage sharing without creating a local registration", () => {
  const section = new Section();
  section.hass = { language: "en", states: {}, areas: {} };
  section.areaId = "bed";
  section.editing = true;
  section.humidity = { humidity_comfort_enabled: false, humidity_target: 55 };
  section.rooms = { hall: { display_name: "Hall" } };
  section.live = { devices: [{ owner_area_id: "hall" }] };
  const text = renderedText(section.render());
  assert.ok(text.includes("A shared appliance already serves this room"));
  assert.ok(text.includes("Change sharing in the host room"));
  assert.ok(text.includes("Hall"));
  assert.equal(section.config, null);
});

test("a registered device waiting for live data is not shown as unassigned", () => {
  const section = new Section();
  section.hass = { language: "en", states: {}, areas: {} };
  section.config = config;
  section.humidity = { humidity_comfort_enabled: false, humidity_target: 55 };
  const text = renderedText(section.render());
  assert.ok(text.includes("Appliance registered"));
  assert.ok(!text.includes("No dedicated or shared device assigned"));
  assert.ok(text.includes("Mold prevention still follows its own settings"));
});

test("equipment cards remain actionable without any configured entities", () => {
  for (const Component of [Sensors, Devices]) {
    const section = new Component();
    section.hass = { language: "it", states: {}, areas: {} };
    const text = renderedText(section.render());
    assert.ok(text.includes("Gestisci"));
  }
  const sensors = new Sensors();
  sensors.hass = { language: "it", states: { "binary_sensor.window": { state: "unavailable", attributes: {} } } };
  const text = renderedText(sensors._renderWindowViewRow("binary_sensor.window"));
  assert.ok(text.includes("Non disponibile"));
  assert.ok(!text.includes("Chiusa"));
});
