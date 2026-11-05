import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createServer } from "vite";

let server, Panel, RoomDetail;
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true } });
  ({ RoomMindPanel: Panel } = await server.ssrLoadModule("/src/roommind-panel.ts"));
  ({ RsRoomDetail: RoomDetail } = await server.ssrLoadModule("/src/components/rs-room-detail.ts"));
});
after(async () => { await server?.close(); });

function setup() {
  const writes = [];
  const hass = { language: "en", areas: { bed: { area_id: "bed", name: "Bed" } }, callWS: async (p) => { writes.push(p.type); return {}; } };
  const detail = new RoomDetail();
  detail.hass = hass;
  detail.area = { area_id: "bed" };
  detail.config = { area_id: "bed", devices: [] };
  detail.dispatchEvent = () => true;
  detail._initFromConfig();
  const panel = new Panel();
  panel.hass = hass;
  panel._selectedAreaId = "bed";
  panel._navigate = () => {};
  panel._loadRooms = () => {};
  Object.defineProperty(panel, "renderRoot", { value: { querySelector: () => detail } });
  return { writes, detail, panel };
}

test("deleting a room with a pending edit does not recreate it on unmount", async () => {
  const { writes, detail, panel } = setup();
  globalThis.confirm = () => true;
  detail._displayName = "Edited";
  detail._autoSave(); // pending 500 ms debounce
  await panel._onDeleteRoom();
  detail.disconnectedCallback(); // detail view removed after deletion
  await new Promise((r) => setTimeout(r, 600));
  assert.deepEqual(writes, ["roommind/rooms/delete"]);
});

test("leaving the room normally still flushes the pending edit", async () => {
  const { writes, detail } = setup();
  detail._autoSave();
  detail.disconnectedCallback();
  assert.deepEqual(writes, ["roommind/rooms/save"]);
});

function deferredDelete(writes, hass) {
  let settle;
  hass.callWS = (p) => {
    writes.push(p.type);
    if (p.type !== "roommind/rooms/delete") return Promise.resolve({});
    return new Promise((resolve, reject) => { settle = { resolve, reject }; });
  };
  return () => settle;
}

test("an edit made while the delete is pending is not saved after success", async () => {
  const { writes, detail, panel } = setup();
  const settle = deferredDelete(writes, detail.hass);
  globalThis.confirm = () => true;
  const pending = panel._onDeleteRoom();
  detail._displayName = "Edited during delete";
  detail._autoSave();
  settle().resolve({});
  await pending;
  detail.disconnectedCallback();
  await new Promise((r) => setTimeout(r, 600));
  assert.deepEqual(writes, ["roommind/rooms/delete"]);
});

test("a rejected delete saves the pending edit and shows the error", async () => {
  const { writes, detail, panel } = setup();
  const settle = deferredDelete(writes, detail.hass);
  globalThis.confirm = () => true;
  detail._displayName = "Edited";
  detail._autoSave();
  const pending = panel._onDeleteRoom();
  settle().reject({ code: "unknown_error", message: "boom" });
  await pending;
  await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(writes, ["roommind/rooms/delete", "roommind/rooms/save"]);
  assert.equal(detail._error, "boom");
});

test("a second delete while the first is pending is ignored", async () => {
  const { writes, detail, panel } = setup();
  const settles = [];
  detail.hass.callWS = (p) => {
    writes.push(p.type);
    if (p.type !== "roommind/rooms/delete") return Promise.resolve({});
    return new Promise((resolve, reject) => settles.push({ resolve, reject }));
  };
  globalThis.confirm = () => true;
  detail._autoSave();
  const first = panel._onDeleteRoom();
  const second = panel._onDeleteRoom();
  settles[0].resolve({});
  settles[1]?.reject({ code: "not_found", message: "not found" });
  await Promise.all([first, second]);
  detail._autoSave();
  detail.disconnectedCallback();
  await new Promise((r) => setTimeout(r, 600));
  assert.deepEqual(writes, ["roommind/rooms/delete"]);
});

test("an earlier save finishing during a failed delete keeps the newer edit dirty", async () => {
  const { writes, detail, panel } = setup();
  let finishSave;
  detail.hass.callWS = (p) => {
    writes.push(p.type);
    if (p.type === "roommind/rooms/save" && !finishSave) return new Promise((r) => { finishSave = r; });
    if (p.type === "roommind/rooms/delete") return Promise.reject({ message: "boom" });
    return Promise.resolve({});
  };
  globalThis.confirm = () => true;
  detail._autoSave();
  const firstSave = detail._doSave(); // save of the first edit is in flight
  detail._displayName = "Newer edit";
  detail._autoSave();
  detail.beginDelete();
  finishSave({});
  await firstSave;
  assert.equal(detail._dirty, true);
  await panel._onDeleteRoom();
  await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(writes, ["roommind/rooms/save", "roommind/rooms/delete", "roommind/rooms/save"]);
});
