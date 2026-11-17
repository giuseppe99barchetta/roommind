import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createServer } from "vite";

let server, RoomDetail, OverrideSection, Hero;
before(async () => {
  globalThis.window ??= { addEventListener() {}, removeEventListener() {} };
  server = await createServer({ configFile: false, server: { middlewareMode: true } });
  ({ RsRoomDetail: RoomDetail } = await server.ssrLoadModule("/src/components/rs-room-detail.ts"));
  ({ RsOverrideSection: OverrideSection } = await server.ssrLoadModule(
    "/src/components/rs-override-section.ts",
  ));
  ({ RsRoomHero: Hero } = await server.ssrLoadModule(
    "/src/components/room-detail/rs-room-hero.ts",
  ));
});
after(async () => {
  await server?.close();
});

const hass = {
  language: "en",
  areas: { sala: { area_id: "sala", name: "Sala" } },
  states: {},
  entities: {},
  devices: {},
  config: { unit_system: { temperature: "°C" } },
  callWS: async () => ({}),
};

// Keys upstream's 2.0 room page saves that the fork's rooms/save rejects (one would fail the whole save)
const UPSTREAM_ONLY = [
  "occupancy_eco_enabled",
  "occupancy_eco_delay",
  "preheat_enabled",
  "follow_device_setpoint",
  "price_shift",
  "covers_window_hold",
  "heat_source_price_aware",
];
const UPSTREAM_ONLY_DEVICE = [
  "coil_dry",
  "coil_dry_mode",
  "coil_dry_minutes",
  "coil_dry_fan_mode",
  "setpoint_offset",
  "setback_auto_off",
];

test("the room page's save payload carries no key the fork's backend rejects", () => {
  const detail = new RoomDetail();
  detail.hass = hass;
  detail.area = hass.areas.sala;
  detail.config = {
    area_id: "sala",
    devices: [{ entity_id: "climate.trv", type: "trv", role: "auto" }],
    covers: ["cover.sala"],
    covers_auto_enabled: true,
    climate_mode: "auto",
  };
  detail._initFromConfig();
  const payload = detail._buildRoomPayload();
  for (const key of UPSTREAM_ONLY) assert.equal(key in payload, false, key);
  for (const dev of payload.devices)
    for (const key of UPSTREAM_ONLY_DEVICE) assert.equal(key in dev, false, key);
});

test("overrides go out with a duration or permanent, never until_schedule_change", async () => {
  const sent = [];
  for (const hours of [1, 2, 4, 0]) {
    const section = new OverrideSection();
    section.hass = { ...hass, callWS: async (msg) => sent.push(msg) };
    section.config = { area_id: "sala", climate_mode: "auto", live: {} };
    section.climateMode = "auto";
    section._overridePending = "boost";
    section.dispatchEvent = () => true;
    await section._onOverrideActivate(hours);
  }
  assert.deepEqual(
    sent.map((m) => m.duration),
    [1, 2, 4, 0],
  );
  for (const msg of sent) {
    assert.equal(msg.type, "roommind/override/set");
    assert.equal("until_schedule_change" in msg, false);
  }
});

function flat(value) {
  if (value == null) return "";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.map(flat).join("");
  if (value.strings) return value.strings.join("") + value.values.map(flat).join("");
  return "";
}

test("the hero names mold prevention without a delta the fork does not send", () => {
  const hero = new Hero();
  hero.hass = hass;
  hero.area = hass.areas.sala;
  hero.climateControlActive = true;
  const live = {
    mode: "heating",
    current_temp: 20,
    target_temp: 21,
    heat_target: 21,
    cool_target: 24,
    mold_prevention_active: true,
    mold_prevention_strategy: "raise",
    mold_risk_level: "warning",
    override_active: false,
  };
  hero.config = { area_id: "sala", climate_mode: "auto", schedules: [], live };
  const text = flat(hero._renderTarget(live));
  assert.ok(text.includes("Mold prevention"), text);
  assert.equal(/NaN|undefined/.test(text), false, text);
});

test("no 'until the next schedule change' choice is offered (the fork's override/set has no such field)", () => {
  const section = new OverrideSection();
  section.hass = hass;
  section.language = "en";
  section.config = {
    area_id: "sala",
    climate_mode: "auto",
    schedules: [{ entity_id: "schedule.sala" }],
    live: { active_schedule_index: 0 },
  };
  section.hass = {
    ...hass,
    states: { "schedule.sala": { state: "on", attributes: { next_event: "2099-01-01T06:00:00" } } },
  };
  const template = section._renderPending("boost");
  const options = template.values.find(
    (v) => Array.isArray(v) && v.every((o) => o && "value" in o),
  );
  assert.ok(options, "duration choices rendered");
  assert.equal(
    options.some((o) => o.value === "next"),
    false,
  );
});

// Value bound to `.name=` (or `@name=`) on the first template whose markup holds `tag`.
function binding(value, tag, name) {
  if (value == null || typeof value !== "object") return undefined;
  if (Array.isArray(value)) {
    for (const v of value) {
      const found = binding(v, tag, name);
      if (found !== undefined) return found;
    }
    return undefined;
  }
  if (!value.strings) return undefined;
  if (value.strings.join("").includes(tag)) {
    const i = value.strings.findIndex((s) => s.trimEnd().endsWith(name + "="));
    if (i >= 0) return value.values[i];
  }
  return binding(value.values, tag, name);
}

function roomDetail(extra = {}) {
  const detail = new RoomDetail();
  detail.hass = hass;
  detail.area = hass.areas.sala;
  detail.config = {
    area_id: "sala",
    devices: [{ entity_id: "climate.trv", type: "trv", role: "auto" }],
    climate_mode: "auto",
    schedules: [],
    live: { mode: "idle", current_temp: 20, target_temp: 21 },
  };
  Object.assign(detail, extra);
  detail._initFromConfig();
  return detail;
}

test("the room page hands the panel's vacation and control mode to the hero", () => {
  const detail = roomDetail({
    controlMode: "bangbang",
    vacationActive: true,
    vacationUntil: 4102444800,
    outdoorTemp: 3,
  });
  const tpl = detail.render();
  assert.equal(binding(tpl, "<rs-room-hero", ".controlMode"), "bangbang");
  assert.equal(binding(tpl, "<rs-room-hero", ".vacationActive"), true);
  assert.equal(binding(tpl, "<rs-room-hero", ".vacationUntil"), 4102444800);
  assert.equal(binding(tpl, "<rs-room-hero", ".outdoorTemp"), 3);
});

test("the presence edit dialog's settings link navigates", () => {
  const detail = roomDetail();
  detail._editing = "presence";
  const handler = binding(detail._renderEditDialog(), "<rs-presence-section", "@open-settings");
  assert.equal(typeof handler, "function");
});

test("the hero keeps the fork's diagnostics: budget, preconditioning, AC efficiency, sensor, window", () => {
  const hero = new Hero();
  hero.hass = hass;
  hero.area = hass.areas.sala;
  hero.config = { area_id: "sala", climate_mode: "auto", temperature_sensor: "sensor.t", live: {} };
  const texts = (live) => {
    hero.config = { ...hero.config, live };
    return hero._chips(live).map((c) => c.text);
  };
  const all = texts({
    mode: "idle",
    current_temp: null,
    power_budget_blocked: true,
    preconditioning_active: true,
    ac_efficiency_status: "possible_issue",
    window_open: true,
    window_open_minutes: 12,
    window_impact_c: -0.8,
    window_recovery_minutes: 25,
  }).join(" | ");
  for (const s of [
    "power budget",
    "Pre-conditioning active",
    "responding slowly",
    "Temperature sensor unavailable",
    "25 min",
    "-0.8",
  ])
    assert.ok(all.includes(s), `${s} in ${all}`);
  const planned = texts({ mode: "idle", current_temp: 20, preconditioning_planned_at: 4102444800 });
  assert.ok(
    planned.some((t) => t.length > 0 && /pre-?condition/i.test(t)),
    planned.join(" | "),
  );
});
