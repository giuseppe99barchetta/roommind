import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizeBypassEntities,
  normalizePowerSensorMode,
  selectEventValue,
  serializeHeatingSettings,
} from "../dist/utils/heating-settings.js";

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
  const selectedConsumption = selectEventValue({ currentTarget: { value: "consumption" } });
  assert.equal(normalizePowerSensorMode(selectedConsumption), "consumption");
  assert.equal(normalizePowerSensorMode("available"), "available");
});

test("save payload keeps the selected consumption mode and list-form bypasses", () => {
  assert.deepEqual(serializeHeatingSettings("climate.valvola_bagno", "consumption"), {
    hydraulic_bypass_entities: ["climate.valvola_bagno"],
    power_sensor_mode: "consumption",
  });
});

test("persisted heating settings render with supported values after reload", () => {
  const persisted = serializeHeatingSettings(["climate.valvola_bagno"], "consumption");
  assert.deepEqual(normalizeBypassEntities(persisted.hydraulic_bypass_entities), [
    "climate.valvola_bagno",
  ]);
  assert.equal(normalizePowerSensorMode(persisted.power_sensor_mode), "consumption");
});
