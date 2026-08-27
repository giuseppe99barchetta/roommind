import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizeBypassEntities,
  normalizeHeatingSettingsForWebsocket,
  normalizePowerSensorMode,
  selectPowerSensorMode,
  serializeHeatingSettings,
  syncPowerSensorMode,
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
  const payload = normalizeHeatingSettingsForWebsocket("climate.valvola_bagno", "available");
  assert.deepEqual(payload.hydraulicBypassEntities, ["climate.valvola_bagno"]);
});

test("the final WebSocket payload preserves consumption mode", () => {
  const payload = normalizeHeatingSettingsForWebsocket([], "consumption");
  assert.equal(payload.powerSensorMode, "consumption");
});

test("the settings model keeps consumption received from the get-settings response", () => {
  const response = {
    settings: serializeHeatingSettings(["climate.valvola_bagno"], "consumption"),
  };
  const settingsModel = {
    bypassEntities: normalizeBypassEntities(response.settings.hydraulic_bypass_entities),
    powerMode: normalizePowerSensorMode(response.settings.power_sensor_mode),
  };
  assert.deepEqual(settingsModel.bypassEntities, ["climate.valvola_bagno"]);
  assert.equal(settingsModel.powerMode, "consumption");
});

test("consumption survives a controlled-select rerender before save", () => {
  let selectState = { value: "available", hasLocalChange: false };

  // render -> select consumption
  selectState = selectPowerSensorMode("consumption");
  assert.equal(selectState.value, "consumption");

  // requestUpdate/rerender while the parent still has its old value
  selectState = syncPowerSensorMode(selectState, "available");
  assert.equal(selectState.value, "consumption");
  assert.equal(selectState.hasLocalChange, true);

  // Parent receives the event and acknowledges the controlled value.
  selectState = syncPowerSensorMode(selectState, "consumption");
  assert.equal(selectState.value, "consumption");
  assert.equal(selectState.hasLocalChange, false);

  // The final save serialization uses the same selected value.
  const payload = normalizeHeatingSettingsForWebsocket([], selectState.value);
  assert.equal(payload.powerSensorMode, "consumption");
});
