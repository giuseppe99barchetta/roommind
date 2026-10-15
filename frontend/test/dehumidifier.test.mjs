import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createServer } from "vite";

let server, Section, RoomDetail;
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true } });
  ({ RsDehumidifierSection: Section } = await server.ssrLoadModule("/src/components/rs-dehumidifier-section.ts"));
  ({ RsRoomDetail: RoomDetail } = await server.ssrLoadModule("/src/components/rs-room-detail.ts"));
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
