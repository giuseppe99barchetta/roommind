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

function overrideSection(live = {}) {
  const sent = [];
  const section = new OverrideSection();
  section.hass = { ...hass, callWS: async (msg) => sent.push(msg) };
  section.config = { area_id: "sala", climate_mode: "auto", live };
  section.climateMode = "auto";
  section.dispatchEvent = () => true;
  return { section, sent };
}

test("a poll still carrying the old override of the same type does not undo a changed one", async () => {
  const now = Date.now() / 1000;
  const old = {
    override_active: true,
    override_type: "custom",
    override_heat: 21,
    override_cool: 25,
    override_until: now + 3600,
  };
  const { section } = overrideSection(old);
  section._overridePending = "custom";
  section._overrideCustomHeat = 23;
  section._overrideCustomCool = 26;
  await section._onOverrideActivate(4);
  section.config = { ...section.config, live: { ...old } };
  section.updated(new Map([["config", null]]));
  const ov = section.getEffectiveOverride();
  assert.equal(ov.heat, 23);
  assert.ok(ov.until > now + 3 * 3600, "the new 4 h end is kept");

  // Same type, same band, a different duration: still the old one
  const boost = { override_active: true, override_type: "boost", override_until: now + 3600 };
  const b = overrideSection(boost).section;
  b._overridePending = "boost";
  await b._onOverrideActivate(0);
  b.config = { ...b.config, live: { ...boost } };
  b.updated(new Map([["config", null]]));
  assert.equal(b.getEffectiveOverride().until, null);
  // The server answers with the permanent override: confirmed
  b.config = { ...b.config, live: { ...boost, override_until: null } };
  b.updated(new Map([["config", null]]));
  assert.equal(b._optimisticOverride, null);
});

test("turning control off while a choice is open drops it and sends nothing", async () => {
  const { section, sent } = overrideSection();
  section._overridePending = "boost";
  section.disabled = true;
  section.willUpdate(new Map([["disabled", false]]));
  assert.equal(section._overridePending, null);
  section._overridePending = "boost";
  await section._onOverrideActivate(2);
  assert.equal(sent.length, 0);
});

test("a late failure of an older override request does not undo a newer one", async () => {
  let rejectFirst;
  const calls = [];
  const section = new OverrideSection();
  section.hass = {
    ...hass,
    callWS: (msg) => {
      calls.push(msg);
      return calls.length === 1
        ? new Promise((_, reject) => (rejectFirst = reject))
        : Promise.resolve({});
    },
  };
  section.config = { area_id: "sala", climate_mode: "auto", live: {} };
  section.climateMode = "auto";
  section.dispatchEvent = () => true;
  section._overridePending = "boost";
  const first = section._onOverrideActivate(2);
  section._overridePending = "eco";
  await section._onOverrideActivate(2);
  rejectFirst(new Error("boom"));
  await first;
  assert.equal(section.getEffectiveOverride().type, "eco");
  assert.equal(section._overrideError, "");

  // Same for a clear overtaken by a newer set
  calls.length = 0;
  const clear = section._onClearOverride();
  section._overridePending = "boost";
  await section._onOverrideActivate(1);
  rejectFirst(new Error("boom"));
  await clear;
  assert.equal(section.getEffectiveOverride().type, "boost");
});

test("a stored target off the stepper grid shows as stored (21.2 °C, not 21)", async () => {
  const { tempRow } = await server.ssrLoadModule("/src/components/shared/temp-row.ts");
  const row = tempRow({ hass, side: "heat", label: "Comfort", celsius: 21.2, onChange() {} });
  const text = flat(row);
  assert.ok(text.includes("21.2"), text);
});

test("the fork's own sections sit in a padded body inside their cards; percent shown once", () => {
  const detail = new RoomDetail();
  detail.hass = hass;
  detail.area = hass.areas.sala;
  detail.config = { area_id: "sala", climate_mode: "auto", devices: [], schedules: [], live: {} };
  detail._initFromConfig();
  // Each fork section sits in a <div class="fork-section"> of the same template part
  const wrapped = [];
  (function walk(v) {
    if (Array.isArray(v)) return v.forEach(walk);
    if (!v || typeof v !== "object" || !v.strings) return;
    v.strings.forEach((str, i) => {
      if (!str.includes('class="fork-section"')) return;
      const inner = str.slice(str.lastIndexOf('class="fork-section"')) + flat(v.values[i]);
      for (const tag of ["<rs-comfort-section", "<rs-dehumidifier-section"])
        if (inner.includes(tag)) wrapped.push(tag);
    });
    v.values.forEach(walk);
  })(detail._renderSectionCards());
  assert.deepEqual(wrapped.sort(), ["<rs-comfort-section", "<rs-dehumidifier-section"]);
  const hero = new Hero();
  hero.hass = hass;
  hero.area = hass.areas.sala;
  const live = { mode: "idle", current_temp: 20, target_temp: 21, mold_surface_rh: 66 };
  hero.config = { area_id: "sala", climate_mode: "auto", schedules: [], live };
  const all = flat(hero.render());
  assert.equal(all.includes("%%"), false);
});
