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
