import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createServer } from "vite";

let server, Page, Summary, Model, builder;
before(async () => {
  globalThis.window ??= { addEventListener() {}, removeEventListener() {} };
  globalThis.matchMedia ??= () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
  });
  server = await createServer({ configFile: false, server: { middlewareMode: true } });
  ({ RsAnalytics: Page } = await server.ssrLoadModule("/src/components/rs-analytics.ts"));
  ({ RsAnalyticsSummary: Summary } = await server.ssrLoadModule(
    "/src/components/analytics/rs-analytics-summary.ts",
  ));
  ({ RsAnalyticsModel: Model } = await server.ssrLoadModule(
    "/src/components/analytics/rs-analytics-model.ts",
  ));
  builder = await server.ssrLoadModule("/src/utils/chart-builder.ts");
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
  config: { unit_system: { temperature: "°C" }, time_zone: "Europe/Rome" },
  callWS: async () => ({}),
};

const T0 = Date.UTC(2026, 10, 17, 6) / 1000;
/** Points as analytics_service.py (205-245) builds them in the fork. */
const points = Array.from({ length: 24 }, (_, i) => ({
  ts: T0 + i * 300,
  room_temp: 20 + i * 0.05,
  outdoor_temp: 6,
  target_temp: 21,
  heat_target: 21,
  cool_target: 24,
  mode: i % 6 < 3 ? "heating" : "idle",
  predicted_temp: 20.2,
  window_open: false,
  heating_power: i % 6 < 3 ? 100 : 0,
  solar_irradiance: 0,
  device_setpoint: 23,
  current_humidity: 55,
  energy_mode: "heating",
  ac_power_w: 400,
  predicted_power_w: 380,
}));

/** analytics/get as the fork answers (analytics_service.py 327-336, 407-422 + residual_heat). */
const response = {
  detail: points.slice(12),
  history: points.slice(0, 12),
  forecast: [],
  energy_cost: { price_eur_kwh: 0.3, today_eur: 0.4, last_7d_eur: 2.1, forecast_3h_eur: 0.1 },
  operation_summary: {},
  energy_insights: {},
  stats: {
    hours: 2,
    heating_hours: 1,
    cooling_hours: 0,
    window_hours: 0,
    heating_starts: 4,
    cooling_starts: 0,
    price: null,
    heat_overshoot: { runs: 4, mean: 0.3, max: 0.6 },
    cool_overshoot: null,
    comfort: {
      below_pct: 20,
      within_pct: 80,
      above_pct: 0,
      mean_deviation: 0.2,
      miss_deviation: 0.5,
    },
  },
  model: {
    confidence: 0.7,
    model: { C: 2000, U: 80, Q_heat: 1500, Q_cool: 0, Q_solar: 0, Q_occupancy: 50 },
    n_samples: 900,
    n_observations: 900,
    n_heating: 300,
    n_cooling: 0,
    applicable_modes: ["idle", "heating"],
    mpc_active: true,
    sigma_e: 0.1,
    prediction_std_idle: 0.2,
    prediction_std_heating: 0.3,
    has_occupancy_sensors: false,
    residual_scale: 1.4,
    residual_samples: 6,
    residual_decay_minutes: 45,
  },
};

const room = {
  area_id: "sala",
  climate_mode: "auto",
  devices: [
    { entity_id: "climate.trv", type: "trv", role: "auto", heating_system_type: "radiator" },
  ],
  temperature_sensor: "sensor.t",
  window_sensors: [],
  schedules: [],
};

function flat(value) {
  if (value == null) return "";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.map(flat).join("");
  if (value.strings) return value.strings.join("") + value.values.map(flat).join("");
  return "";
}

async function loadedPage(controlMode = "bangbang") {
  const page = new Page();
  page.hass = {
    ...hass,
    callWS: async (msg) =>
      msg.type === "roommind/analytics/compare"
        ? {
            rooms: [
              { area_id: "sala", name: "Sala" },
              { area_id: "b", name: "B" },
            ],
          }
        : structuredClone(response),
  };
  page.rooms = { sala: room };
  page.controlMode = controlMode;
  page._selectedRoom = "sala";
  page.dispatchEvent = () => true;
  await page._fetchData();
  return page;
}

test("the page renders a fork analytics answer: summary, chart, energy, comparison, model", async () => {
  const page = await loadedPage();
  const text = flat(page.render());
  for (const tag of [
    "<rs-analytics-summary",
    "<rs-analytics-chart",
    "<rs-energy-analytics-chart",
    "<rs-analytics-model",
  ])
    assert.ok(text.includes(tag), tag);
  assert.ok(text.includes("comparison"), "room comparison table");
  assert.equal(text.includes("rs-analytics-rhythm"), false, "no rhythm card");
  assert.equal(/NaN|undefined/.test(text), false);
});

test("humidity reaches the 2.0 chart from current_humidity; no co2, price or target-reason panel", async () => {
  const page = await loadedPage();
  const pts = page._points();
  assert.ok(pts.every((p) => p.humidity === 55 && p.current_humidity === 55));
  const series = builder.buildChartSeries(pts, {
    hass,
    language: "en",
    chartAnchor: (T0 + 24 * 300) * 1000,
    rangeStart: T0 * 1000,
    rangeEnd: (T0 + 24 * 300) * 1000,
    targetBand: "both",
    showPrice: false,
  });
  const panels = builder.visiblePanels(series, new Set());
  assert.deepEqual(panels, ["outdoor", "humidity"]);
  assert.equal(
    series.some((s) => String(s.id ?? "").includes("reason")),
    false,
    "no target-reason strip",
  );
});

test("summary and model render without NaN, the model shows the fork's afterglow and accuracy, never Simple mode", async () => {
  const page = await loadedPage("bangbang");
  const s = new Summary();
  Object.assign(s, {
    hass,
    stats: page._data.stats,
    points: page._points(),
    rangeStart: T0 * 1000,
    rangeEnd: (T0 + 24 * 300) * 1000,
    bandSides: "both",
    canHeat: true,
    canCool: false,
    hasWindowSensor: false,
    showPrice: false,
    language: "en",
  });
  const sText = flat(s.render());
  assert.equal(/NaN|undefined/.test(sText), false, sText.slice(0, 300));

  // The page hands the model "mpc" whatever rooms/list says (bangbang = still learning)
  const bound = [];
  (function walk(v) {
    if (Array.isArray(v)) return v.forEach(walk);
    if (!v || typeof v !== "object" || !v.strings) return;
    v.strings.forEach((str, i) => {
      if (
        v.strings.join("").includes("<rs-analytics-model") &&
        str.trimEnd().endsWith(".controlMode=")
      )
        bound.push(v.values[i]);
    });
    v.values.forEach(walk);
  })(page.render());
  assert.deepEqual(bound, ["mpc"]);
  const m = new Model();
  Object.assign(m, {
    hass,
    data: page._data,
    language: "en",
    controlMode: "mpc",
    managed: false,
    canHeat: true,
    canCool: false,
    boostHours: null,
  });
  const ids = m._tiles().map((t) => t.id);
  assert.ok(ids.includes("residual_afterglow"), ids.join());
  assert.ok(ids.includes("accuracy_idle") && ids.includes("accuracy_heating"), ids.join());
  const mText = flat(m.render());
  assert.equal(/NaN|undefined/.test(mText), false);
  assert.equal(mText.includes("Simple"), false);
});

test("fork-only shapes: legacy AC list cools, solar shows without a learned flag, no mislabeled backtest line", async () => {
  const page = await loadedPage();
  const legacy = { ...room, devices: undefined, acs: ["climate.ac"], thermostats: ["climate.trv"] };
  page.rooms = { sala: legacy };
  const bound = [];
  (function walk(v) {
    if (Array.isArray(v)) return v.forEach(walk);
    if (!v || typeof v !== "object" || !v.strings) return;
    v.strings.forEach((str, i) => {
      if (v.strings.join("").includes("<rs-analytics-model") && str.trimEnd().endsWith(".canCool="))
        bound.push(v.values[i]);
    });
    v.values.forEach(walk);
  })(page.render());
  assert.deepEqual(bound, [true]);

  // The chart gets no recorded prediction (no mislabeled backtest line); the export keeps it
  assert.ok(
    page._chartData().history.every((p) => p.predicted_temp === null),
    "chart",
  );
  assert.ok(
    page._data.history.every((p) => p.predicted_temp === 20.2),
    "export data",
  );
  const { buildCsvString } = await server.ssrLoadModule("/src/utils/analytics-export.ts");
  assert.ok(buildCsvString(page._data).includes("20.2"), "CSV keeps predicted_temp");
  const m = new Model();
  const data = structuredClone(page._data);
  data.model.model.Q_solar = 300;
  Object.assign(m, {
    hass,
    data,
    language: "en",
    controlMode: "mpc",
    canHeat: true,
    canCool: false,
  });
  assert.ok(m._tiles().some((t) => t.id === "solar_gain"));
});

test("the afterglow info names the per-room residual control switch, not 'learning only'", async () => {
  const { readFileSync } = await import("node:fs");
  const stale = {
    en: "does not change heating yet",
    de: "ändert sich noch nicht",
    fr: "ne change pas encore",
    it: "il riscaldamento non cambia.",
  };
  for (const lang of ["en", "de", "fr", "it"]) {
    const strings = JSON.parse(
      readFileSync(new URL(`../src/locales/${lang}.json`, import.meta.url), "utf8"),
    );
    const info = strings["analytics.info.residual_afterglow"];
    assert.ok(!info.includes(stale[lang]), `${lang}: ${info}`);
    assert.ok(info.includes(strings["schedule.residual_control_toggle"]), `${lang}: ${info}`);
    assert.ok(info.includes(strings["room.section.schedule"]), `${lang}: ${info}`);
  }
});

test("the rhythm card shows when the backend sends a rhythm; a picked day becomes the range", async () => {
  const day = (date) => ({
    date,
    heat: Array(24).fill(0.5),
    cool: Array(24).fill(null),
    window: Array(24).fill(0),
    deviation: Array(24).fill(0),
    below: Array(24).fill(0),
    above: Array(24).fill(0),
    temp: Array(24).fill(20.5),
    humidity: Array(24).fill(55),
    outdoor: Array(24).fill(4),
    within: 1,
  });
  const page = await loadedPage();
  page._data = { ...page._data, rhythm: { days: [day("2026-11-17"), day("2026-11-16")] } };
  assert.ok(flat(page.render()).includes("<rs-analytics-rhythm"), "card mounted");

  const { RsAnalyticsRhythm } = await server.ssrLoadModule(
    "/src/components/analytics/rs-analytics-rhythm.ts",
  );
  const card = new RsAnalyticsRhythm();
  Object.assign(card, {
    hass,
    rhythm: page._data.rhythm,
    rangeStart: Date.UTC(2026, 10, 16),
    rangeEnd: Date.UTC(2026, 10, 17),
    language: "en",
    canHeat: true,
    canCool: false,
    hasWindowSensor: true,
    bandSides: { heat: true, cool: false },
  });
  assert.equal(/NaN|undefined/.test(flat(card.render())), false);

  globalThis.matchMedia ??= () => ({ matches: true });
  void page._onDaySelected(new CustomEvent("day-selected", { detail: "2026-11-16" }));
  assert.equal(page._activeQuick, null);
  assert.ok(page._rangeEnd > page._rangeStart);
  assert.ok(page._rangeEnd - page._rangeStart < 25 * 3600_000, "one day");
});
