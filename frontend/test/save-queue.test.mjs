import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createServer } from "vite";

let server, RoomDetail, Settings;
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true } });
  ({ RsRoomDetail: RoomDetail } = await server.ssrLoadModule("/src/components/rs-room-detail.ts"));
  ({ RsSettings: Settings } = await server.ssrLoadModule("/src/components/rs-settings.ts"));
});
after(async () => {
  await server?.close();
});

/** callWS whose first save waits until released; later calls answer at once. */
function deferredFirst(writes) {
  let release;
  const callWS = (p) => {
    writes.push(p);
    if (writes.length === 1) return new Promise((r) => (release = r));
    return Promise.resolve({});
  };
  return { callWS, release: () => release({}) };
}

test("room page: reverting a value while its save is in flight still reaches the backend", async () => {
  const writes = [];
  const ws = deferredFirst(writes);
  const detail = new RoomDetail();
  detail.hass = { language: "en", callWS: ws.callWS };
  detail.area = { area_id: "bed" };
  detail.config = { area_id: "bed", devices: [], display_name: "A" };
  detail.dispatchEvent = () => true;
  detail._initFromConfig();

  detail._displayName = "B";
  const first = detail._doSave(); // in flight
  detail._displayName = "A";
  const second = detail._doSave(); // queued behind it
  assert.equal(writes.length, 1);
  ws.release();
  await Promise.all([first, second]);
  assert.deepEqual(
    writes.map((w) => w.display_name),
    ["B", "A"],
  );
});

test("settings page: reverting a value while its save is in flight still reaches the backend", async () => {
  const writes = [];
  const ws = deferredFirst(writes);
  const settings = new Settings();
  settings.hass = { language: "en", callWS: ws.callWS };
  settings.dispatchEvent = () => true;
  settings._comfortWeight = 70;
  settings._savedPayload = Object.fromEntries(
    Object.entries(settings._buildPayload()).map(([k, v]) => [k, JSON.stringify(v)]),
  );

  settings._comfortWeight = 40;
  const first = settings._doSave();
  settings._comfortWeight = 70;
  const second = settings._doSave();
  ws.release();
  await Promise.all([first, second]);
  assert.deepEqual(
    writes.map((w) => w.comfort_weight),
    [40, 70],
  );
});

test("settings page: nothing is saved after a failed load", async () => {
  const writes = [];
  const settings = new Settings();
  settings.hass = {
    language: "en",
    callWS: async (p) => {
      writes.push(p);
      throw new Error("down");
    },
  };
  settings.dispatchEvent = () => true;
  await settings._loadSettings();
  assert.equal(settings._loadFailed, true);
  settings._comfortWeight = 10;
  await settings._doSave();
  assert.deepEqual(
    writes.map((w) => w.type),
    ["roommind/settings/get"],
  );
});
