import assert from "node:assert/strict";
import test from "node:test";

import { overrideMessage, remainingText, roomName } from "../dist/card/helpers.js";

test("remaining time in hours and minutes, empty once past", () => {
  const now = 1_000_000_000;
  assert.equal(remainingText(1_000_000 + 4800, now), "1h 20m");
  assert.equal(remainingText(1_000_000 + 1200, now), "20m");
  assert.equal(remainingText(1_000_000 - 1, now), "");
});

test("room name: display name, then area name, then id", () => {
  const hass = { areas: { a1: { area_id: "a1", name: "Sala" } } };
  assert.equal(roomName({ display_name: "Living" }, hass, "a1"), "Living");
  assert.equal(roomName({}, hass, "a1"), "Sala");
  assert.equal(roomName(undefined, hass, "zz"), "zz");
});

test("comfort and eco overrides send only type and duration", () => {
  assert.deepEqual(overrideMessage("a1", { climate_mode: "auto" }, "boost", 2, 30), {
    type: "roommind/override/set",
    area_id: "a1",
    override_type: "boost",
    duration: 2,
  });
});

test("custom override follows the climate mode", () => {
  const heatOnly = overrideMessage("a1", { climate_mode: "heat_only" }, "custom", 1, 22);
  assert.equal(heatOnly.heat, 22);
  assert.equal("cool" in heatOnly, false);
  const coolOnly = overrideMessage("a1", { climate_mode: "cool_only" }, "custom", 1, 25);
  assert.equal(coolOnly.cool, 25);
  assert.equal("heat" in coolOnly, false);
});

test("custom override in auto keeps the cooling target and rejects an inverted band", () => {
  const room = { climate_mode: "auto", comfort_cool: 24, live: { cool_target: 25 } };
  const msg = overrideMessage("a1", room, "custom", 4, 22);
  assert.equal(msg.heat, 22);
  assert.equal(msg.cool, 25);
  assert.equal(overrideMessage("a1", room, "custom", 4, 26), null);
});
