import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createServer } from "vite";

let server, Panel;
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true } });
  ({ RoomMindPanel: Panel } = await server.ssrLoadModule("/src/roommind-panel.ts"));
});
after(async () => {
  await server?.close();
});

function panelWith(callWS) {
  const panel = new Panel();
  panel.hass = { language: "en", areas: {}, states: {}, entities: {}, devices: {}, callWS };
  panel._roomsLoaded = true;
  panel._activeTab = "areas";
  let reloads = 0;
  panel._loadRooms = async () => {
    reloads += 1;
  };
  return { panel, reloads: () => reloads };
}

test("the rooms dashboard offers a way into edit mode", () => {
  const { panel } = panelWith(async () => ({}));
  globalThis.window ??= { addEventListener() {}, removeEventListener() {} };
  const template = panel._renderAreas();
  const flat = JSON.stringify(template.strings);
  assert.ok(flat.includes("rs-icon-button"), "edit button rendered next to the dashboard");
  assert.ok(template.values.includes(panel._startEditing), "the button starts edit mode");
  panel._startEditing();
  assert.equal(panel._isEditing(), true);
  panel._stopEditing();
});

test("an older failed layout save does not undo a newer one that went through", async () => {
  const pending = [];
  const { panel, reloads } = panelWith(
    (msg) =>
      new Promise((resolve, reject) => {
        pending.push({ msg, resolve, reject });
      }),
  );
  panel._hiddenRooms = [];
  panel._onRoomHiddenChanged(new CustomEvent("x", { detail: { areaId: "a", hidden: true } }));
  panel._onRoomHiddenChanged(new CustomEvent("x", { detail: { areaId: "b", hidden: true } }));
  pending[1].resolve({});
  pending[0].reject(new Error("timeout"));
  await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(panel._hiddenRooms, ["a", "b"]);
  assert.equal(reloads(), 1, "the server's state is reloaded after the failure");
});

test("a rooms/list answer sent before a layout edit does not bring the old layout back", async () => {
  let answer;
  const { panel } = panelWith(async (msg) => {
    if (msg.type === "roommind/rooms/list") return new Promise((r) => (answer = r));
    return {};
  });
  panel._loadRooms = Object.getPrototypeOf(panel)._loadRooms.bind(panel);
  panel._hiddenRooms = [];
  const load = panel._loadRooms(); // poll in flight
  panel._onRoomHiddenChanged(new CustomEvent("x", { detail: { areaId: "a", hidden: true } }));
  answer({ rooms: {}, hidden_rooms: [], room_order: [], group_by_floor: false });
  await load;
  assert.deepEqual(panel._hiddenRooms, ["a"]);
});
