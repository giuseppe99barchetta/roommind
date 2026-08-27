export type PowerSensorMode = "available" | "consumption";

/** Local state for a controlled ha-select while a parent update is in flight. */
export interface PowerSensorModeState {
  value: PowerSensorMode;
  hasLocalChange: boolean;
}

/** Normalize Home Assistant entity-picker values to the persisted list format. */
export function normalizeBypassEntities(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.filter(
      (entityId): entityId is string => typeof entityId === "string" && entityId.length > 0,
    );
  }
  return typeof value === "string" && value.length > 0 ? [value] : [];
}

/** Keep an invalid or stale stored mode fail-safe and compatible with the schema. */
export function normalizePowerSensorMode(value: unknown): PowerSensorMode {
  return value === "consumption" ? "consumption" : "available";
}

/** Apply a user selection immediately, before the parent component rerenders. */
export function selectPowerSensorMode(value: unknown): PowerSensorModeState {
  return { value: normalizePowerSensorMode(value), hasLocalChange: true };
}

/**
 * Keep a local user selection until the parent acknowledges the same value.
 * This prevents HA's controlled ha-select from snapping back during a render.
 */
export function syncPowerSensorMode(
  state: PowerSensorModeState,
  parentValue: unknown,
): PowerSensorModeState {
  const incoming = normalizePowerSensorMode(parentValue);
  if (state.hasLocalChange && incoming !== state.value) {
    return state;
  }
  return { value: incoming, hasLocalChange: false };
}

export function serializeHeatingSettings(
  bypassEntities: unknown,
  powerMode: unknown,
): { hydraulic_bypass_entities: string[]; power_sensor_mode: PowerSensorMode } {
  return {
    hydraulic_bypass_entities: normalizeBypassEntities(bypassEntities),
    power_sensor_mode: normalizePowerSensorMode(powerMode),
  };
}

/** Normalize raw UI state for the final global-settings WebSocket payload. */
export function normalizeHeatingSettingsForWebsocket(
  rawBypass: unknown,
  rawPowerSensorMode: unknown,
): { hydraulicBypassEntities: string[]; powerSensorMode: PowerSensorMode } {
  const hydraulicBypassEntities = Array.isArray(rawBypass)
    ? rawBypass.filter((value): value is string => typeof value === "string" && value.length > 0)
    : typeof rawBypass === "string" && rawBypass.length > 0
      ? [rawBypass]
      : [];
  const powerSensorMode = rawPowerSensorMode === "consumption" ? "consumption" : "available";

  return {
    hydraulicBypassEntities,
    powerSensorMode,
  };
}
