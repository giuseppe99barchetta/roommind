import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createServer } from "vite";

let server, Settings, Panel, cats;
before(async () => {
  globalThis.window ??= { addEventListener() {}, removeEventListener() {} };
  server = await createServer({ configFile: false, server: { middlewareMode: true } });
  ({ RsSettings: Settings } = await server.ssrLoadModule("/src/components/rs-settings.ts"));
  ({ RoomMindPanel: Panel } = await server.ssrLoadModule("/src/roommind-panel.ts"));
  cats = await server.ssrLoadModule("/src/components/settings/settings-categories.ts");
});
after(async () => {
  await server?.close();
});

const hass = {
  language: "en",
  areas: {},
  states: {},
  entities: {},
  devices: {},
  config: { unit_system: { temperature: "°C" } },
  callWS: async () => ({}),
};

const PANELS = [
  "rs-settings-heating-system",
  "rs-settings-preview",
  "rs-settings-general",
  "rs-settings-sensors",
  "rs-settings-control",
  "rs-settings-presence",
  "rs-settings-vacation",
  "rs-settings-valve",
  "rs-settings-compressor",
  "rs-settings-orphans",
  "rs-settings-head-offset",
  "rs-settings-mold",
  "rs-settings-notifications",
  "rs-settings-learning",
  "rs-settings-reset",
];

function flat(value) {
  if (value == null) return "";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.map(flat).join("");
  if (value.strings) return value.strings.join("") + value.values.map(flat).join("");
  return "";
}

/** Values bound to `?hidden=` right before each `<tag`, in template order. */
function hiddenOf(template) {
  const out = {};
  (function walk(v) {
    if (Array.isArray(v)) return v.forEach(walk);
    if (!v || typeof v !== "object" || !v.strings) return;
    v.strings.forEach((s, i) => {
      const next = v.strings[i + 1] ?? "";
      if (s.trimEnd().endsWith("?hidden=")) {
        const tag = PANELS.find((t) => next.includes(`<${t}`));
        if (tag) out[tag] = v.values[i];
      }
    });
    v.values.forEach(walk);
  })(template);
  return out;
}

function settings(extra = {}) {
  const s = new Settings();
  s.hass = hass;
  s._loaded = true;
  Object.assign(s, extra);
  return s;
}

test("the categories are the fork's: no price or coil dry, heating system / preview / head offset in", () => {
  const ids = cats.SETTINGS_GROUPS.flatMap((g) => g.categories.map((c) => c.id));
  assert.deepEqual(ids.sort(), [
    "compressor",
    "control",
    "general",
    "head_offset",
    "heating_system",
    "learning",
    "mold",
    "notifications",
    "orphans",
    "presence",
    "preview",
    "reset",
    "sensors",
    "vacation",
    "valve",
  ]);
});

test("routing resolves known, unknown and orphan categories", () => {
  const r = cats.resolveSettingsCategory;
  assert.equal(r("presence", false, true), "presence");
  assert.equal(r("presence", false, false), "presence");
  assert.equal(r("price", false, true), "general");
  assert.equal(r("coil_dry", false, false), "");
  assert.equal(r("orphans", false, true), "general");
  assert.equal(r("orphans", true, false), "orphans");
});

test("resting rooms appear in the list only when there are any", () => {
  const without = flat(settings()._renderNav("general"));
  assert.equal(without.includes('data-id="orphans"') || without.includes("orphans"), false);
  const s = settings({ roomsWithoutArea: [{ area_id: "x", display_name: "X" }] });
  assert.ok(flat(s._renderNav("general")).includes("home-remove-outline"));
});

test("a list row selects its category through the panel event", () => {
  const s = settings();
  const fired = [];
  s.dispatchEvent = (e) => (fired.push(e), true);
  s._onNavClick({ preventDefault() {}, button: 0 }, "mold");
  assert.equal(fired[0].type, "settings-category-changed");
  assert.equal(fired[0].detail.category, "mold");
  // A modified click keeps the browser's own link handling
  s._onNavClick({ ctrlKey: true, preventDefault() {}, button: 0 }, "valve");
  assert.equal(fired.length, 1);
});

test("every panel stays mounted across categories, only the selected one shown", () => {
  for (const [category, wide] of [
    ["preview", true],
    ["vacation", false],
    ["orphans", true],
    ["general", true],
  ]) {
    const s = settings({
      category,
      wide,
      roomsWithoutArea: [{ area_id: "x", display_name: "X" }],
    });
    const hidden = hiddenOf(s.render());
    assert.deepEqual(Object.keys(hidden).sort(), [...PANELS].sort(), category);
    const shown = Object.entries(hidden)
      .filter(([, h]) => !h)
      .map(([t]) => t);
    assert.deepEqual(shown, [`rs-settings-${category}`], category);
  }
  // Narrow list: no category selected, every panel still in the tree (hidden)
  const list = hiddenOf(settings({ category: "", wide: false }).render());
  assert.equal(Object.keys(list).length, PANELS.length);
  assert.ok(Object.values(list).every(Boolean));
});

test("the room page's presence link and the URL open the presence category", () => {
  const panel = new Panel();
  panel.route = { path: "/settings/presence" };
  panel._applyRoute();
  assert.equal(panel._activeTab, "settings");
  assert.equal(panel._settingsCategory, "presence");
  for (const wide of [true, false]) {
    const s = settings({ category: panel._settingsCategory, wide });
    const shown = Object.entries(hiddenOf(s.render())).filter(([, h]) => !h);
    assert.deepEqual(
      shown.map(([t]) => t),
      ["rs-settings-presence"],
      `wide=${wide}`,
    );
  }
  panel.route = { path: "/settings/price" };
  panel._applyRoute();
  assert.equal(panel._settingsCategory, "", "unknown id falls back");
});

test("summaries: control names MPC whatever rooms/list says, the outdoor reading is in the user's unit", () => {
  const f = {
    ...hass,
    config: { unit_system: { temperature: "°F" } },
    states: {
      "sensor.out": {
        entity_id: "sensor.out",
        state: "20",
        attributes: { unit_of_measurement: "°C" },
      },
    },
  };
  const s = settings({ hass: f, _outdoorTempSensor: "sensor.out" });
  const outdoor = s._summary("sensors").text;
  assert.ok(outdoor.includes("68"), outdoor);
  assert.equal(outdoor.includes("20"), false, outdoor);
  const control = s._summary("control").text;
  assert.ok(control.includes("MPC"), control);
});

test("a narrow deep link that arrives before the settings load focuses the page once they did", () => {
  const s = settings({ category: "presence", wide: false });
  let focused = 0;
  globalThis.window.scrollTo ??= () => {};
  s.renderRoot = {
    querySelector: (sel) => (sel === "#page-title" ? { focus: () => focused++ } : null),
  };
  s.updated(new Map([["_loaded", false]]));
  assert.equal(focused, 1);
});
