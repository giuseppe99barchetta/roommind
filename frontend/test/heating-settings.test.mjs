import assert from "node:assert/strict";
import test from "node:test";

import {
  finalizeHeatingSettingsPayload,
  normalizeBypassEntities,
  normalizePowerSensorMode,
  serializeHeatingSettings,
} from "../dist/utils/heating-settings.js";
import { getSelectValue } from "../dist/utils/events.js";

test("one bypass selection serializes as a one-item list", () => {
  assert.deepEqual(normalizeBypassEntities("climate.valvola_bagno"), ["climate.valvola_bagno"]);
});

test("multiple bypass selections serialize as a list", () => {
  assert.deepEqual(normalizeBypassEntities(["climate.valvola_bagno", "climate.valvola_sala"]), [
    "climate.valvola_bagno",
    "climate.valvola_sala",
  ]);
});

test("existing bypass list loads without changing its selections", () => {
  const stored = ["climate.valvola_bagno", "climate.valvola_sala"];
  assert.deepEqual(normalizeBypassEntities(stored), stored);
});

test("power sensor mode changes in both directions", () => {
  const selectedConsumption = getSelectValue({
    detail: { value: "consumption" },
    target: { value: "available" },
  });
  assert.equal(normalizePowerSensorMode(selectedConsumption), "consumption");
  assert.equal(normalizePowerSensorMode("available"), "available");
});

test("save payload keeps the selected consumption mode and list-form bypasses", () => {
  assert.deepEqual(serializeHeatingSettings("climate.valvola_bagno", "consumption"), {
    hydraulic_bypass_entities: ["climate.valvola_bagno"],
    power_sensor_mode: "consumption",
  });
});

test("the final WebSocket payload converts a single bypass string to a list", () => {
  const payload = finalizeHeatingSettingsPayload({
    type: "roommind/settings/save",
    hydraulic_bypass_entities: "climate.valvola_bagno",
    power_sensor_mode: "available",
  });
  assert.deepEqual(payload.hydraulic_bypass_entities, ["climate.valvola_bagno"]);
});

test("the final WebSocket payload preserves consumption mode", () => {
  const payload = finalizeHeatingSettingsPayload({
    type: "roommind/settings/save",
    hydraulic_bypass_entities: [],
    power_sensor_mode: "consumption",
  });
  assert.equal(payload.power_sensor_mode, "consumption");
});

test("persisted heating settings render with supported values after reload", () => {
  const persisted = serializeHeatingSettings(["climate.valvola_bagno"], "consumption");
  assert.deepEqual(normalizeBypassEntities(persisted.hydraulic_bypass_entities), [
    "climate.valvola_bagno",
  ]);
  assert.equal(normalizePowerSensorMode(persisted.power_sensor_mode), "consumption");
});
