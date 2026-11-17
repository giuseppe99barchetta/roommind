import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createServer } from "vite";

let server, Panel, Editor, RoomDetail, ScheduleSettings, api;
before(async () => {
  globalThis.window ??= { addEventListener() {}, removeEventListener() {} };
  server = await createServer({ configFile: false, server: { middlewareMode: true } });
  ({ RoomMindPanel: Panel } = await server.ssrLoadModule("/src/roommind-panel.ts"));
  ({ RsScheduleEditor: Editor } = await server.ssrLoadModule(
    "/src/components/schedule/rs-schedule-editor.ts",
  ));
  ({ RsRoomDetail: RoomDetail } = await server.ssrLoadModule("/src/components/rs-room-detail.ts"));
  ({ RsScheduleSettings: ScheduleSettings } = await server.ssrLoadModule(
    "/src/components/rs-schedule-settings.ts",
  ));
  api = {
    ...(await server.ssrLoadModule("/src/utils/schedule-api.ts")),
    ...(await server.ssrLoadModule("/src/utils/schedule-week.ts")),
  };
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
  user: { is_admin: true },
  callWS: async () => ({}),
};

test("routes: /schedules opens the overview, /schedule/<id>?room=&kind= the editor", () => {
  const panel = new Panel();
  panel.route = { path: "/schedules" };
  panel._applyRoute();
  assert.equal(panel._activeTab, "schedules");
  assert.equal(panel._scheduleEntity, null);
  globalThis.window.location = { search: "?room=sala&kind=cover" };
  panel.route = { path: "/schedule/schedule.heating" };
  panel._applyRoute();
  assert.equal(panel._scheduleEntity, "schedule.heating");
  assert.equal(panel._scheduleRoom, "sala");
  assert.equal(panel._scheduleKind, "cover");
  assert.equal(panel._activeTab, "areas");
  delete globalThis.window.location;
});

test("the editor offers no helper deletion and never calls schedule/delete", () => {
  for (const name of ["_delete", "_renderDeleteRow", "_renderDeleteDialog", "_deleteEffects"])
    assert.equal(name in Editor.prototype, false, name);
  assert.equal("deleteSchedule" in api ? typeof Editor.prototype._delete : "none", "undefined");
});

function editorWithConflict(remote) {
  const ed = new Editor();
  const calls = [];
  ed.hass = {
    ...hass,
    callWS: async (msg) => {
      calls.push(msg.type);
      if (msg.type === "schedule/list") return [remote];
      return remote;
    },
  };
  ed.entityId = "schedule.heating";
  const week = { monday: [{ from: "06:00:00", to: "08:00:00" }] };
  ed._loaded = { itemId: "heating", name: "Heating", icon: "", snapshot: "" };
  ed._week = api.parseWeek(week);
  ed._name = "Heating";
  ed._remoteSnapshot = api.itemSnapshot({ name: "Heating", ...week });
  ed._savedJson = "";
  ed.dispatchEvent = () => true;
  return { ed, calls };
}

test("a helper changed elsewhere keeps the local draft and offers keep mine / load theirs", async () => {
  const remote = {
    id: "heating",
    name: "Heating",
    tuesday: [{ from: "10:00:00", to: "11:00:00" }],
  };
  const { ed, calls } = editorWithConflict(remote);
  const draft = JSON.stringify(ed._week);
  const message = await ed._flush();
  assert.ok(message, "flush reports the conflict");
  assert.equal(ed._conflict, true);
  assert.equal(JSON.stringify(ed._week), draft, "local edit kept");
  assert.equal(calls.includes("schedule/update"), false);
  // Load theirs: the remote week replaces the draft
  ed._loadTheirs();
  assert.equal(ed._conflict, false);
  assert.notEqual(JSON.stringify(ed._week), draft);

  const second = editorWithConflict(remote);
  await second.ed._flush();
  second.ed._keepMine();
  await second.ed._saving;
  assert.ok(second.calls.includes("schedule/update"), "keep mine saves over it");
  assert.equal(second.ed._conflict, false);
});

test("leaving the editor with a failed save keeps it open (back and tabs); a good save leaves", async () => {
  const panel = new Panel();
  panel.hass = hass;
  panel._rooms = {};
  panel._loadRooms = async () => {};
  panel._navigate = () => {};
  panel._navigateBack = () => {};
  panel._scheduleEntity = "schedule.heating";
  panel._scheduleRoom = "sala";
  let result = "Could not save";
  panel.dispatchEvent = () => true;
  Object.defineProperty(panel, "renderRoot", {
    value: { querySelector: () => ({ flush: async () => result }) },
  });
  await panel._onBackFromSchedule();
  assert.equal(panel._scheduleEntity, "schedule.heating", "back kept the editor");
  await panel._onTabClicked("settings");
  assert.equal(panel._scheduleEntity, "schedule.heating", "tab kept the editor");
  result = "";
  await panel._onBackFromSchedule();
  assert.equal(panel._scheduleEntity, null);
  assert.equal(panel._selectedAreaId, "sala", "back to the room it came from");
});

test("the room's schedule dialog opens the editor for this room through the panel", async () => {
  const sch = new ScheduleSettings();
  sch.hass = {
    ...hass,
    states: { "schedule.a": { entity_id: "schedule.a", state: "on", attributes: {} } },
  };
  sch.schedules = [{ entity_id: "schedule.a" }];
  sch.editing = true;
  const fired = [];
  sch.dispatchEvent = (e) => (fired.push(e), true);
  sch._openEditor("schedule.a");
  assert.equal(fired[0].type, "open-schedule-editor");
  assert.equal(fired[0].detail.entityId, "schedule.a");

  const detail = new RoomDetail();
  detail.hass = hass;
  detail.area = hass.areas.sala;
  const out = [];
  detail.dispatchEvent = (e) => (out.push(e), true);
  await detail._onOpenScheduleEditor({
    ...fired[0],
    stopPropagation() {},
    detail: fired[0].detail,
  });
  assert.deepEqual(out[0].detail, { entityId: "schedule.a", areaId: "sala", kind: "climate" });
});

test("a non-admin views an editable helper without the admin-only schedule/list", async () => {
  const calls = [];
  const h = {
    ...hass,
    user: { is_admin: false },
    states: {
      "schedule.a": { entity_id: "schedule.a", state: "on", attributes: { editable: true } },
    },
    callWS: async (msg) => {
      calls.push(msg.type);
      if (msg.type === "schedule/list") throw new Error("Unauthorized");
      if (msg.type === "execute_script" || msg.type === "call_service")
        return { response: { "schedule.a": {} } };
      return [];
    },
  };
  const loaded = await api.loadSchedule(h, "schedule.a");
  assert.equal(loaded.itemId, null, "view only");
  assert.equal(calls.includes("schedule/list"), false);
});

test("opening the editor saves the room first: a failed save stays, the next click retries", async () => {
  const detail = new RoomDetail();
  detail.hass = hass;
  detail.area = hass.areas.sala;
  const out = [];
  detail.dispatchEvent = (e) => (out.push(e), true);
  let fail = true;
  let saves = 0;
  detail._doSave = () => {
    saves++;
    detail._saveQueue = Promise.resolve().then(() => {
      if (!fail) detail._dirty = false;
    });
    return detail._saveQueue;
  };
  detail._dirty = true;
  detail._saveDebounce = setTimeout(() => {}, 10000);
  const ev = { stopPropagation() {}, detail: { entityId: "schedule.a" } };
  await detail._onOpenScheduleEditor(ev);
  assert.equal(out.length, 0, "stays on the room page");
  // No new edit, no debounce: the click itself retries the save
  fail = false;
  await detail._onOpenScheduleEditor(ev);
  assert.ok(saves >= 3, `retried (${saves} saves)`);
  assert.equal(out[0].type, "open-schedule-editor");
});
