export type PowerSensorMode = "available" | "consumption";

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

export function serializeHeatingSettings(
  bypassEntities: unknown,
  powerMode: unknown,
): { hydraulic_bypass_entities: string[]; power_sensor_mode: PowerSensorMode } {
  return {
    hydraulic_bypass_entities: normalizeBypassEntities(bypassEntities),
    power_sensor_mode: normalizePowerSensorMode(powerMode),
  };
}

/**
 * Apply the strict heating-settings contract at the final WebSocket boundary.
 * This intentionally accepts the picker values emitted by multiple HA releases
 * while guaranteeing a schema-compatible payload.
 */
export function finalizeHeatingSettingsPayload<
  T extends { hydraulic_bypass_entities: unknown; power_sensor_mode: unknown },
>(
  payload: T,
): Omit<T, "hydraulic_bypass_entities" | "power_sensor_mode"> & {
  hydraulic_bypass_entities: string[];
  power_sensor_mode: PowerSensorMode;
} {
  return {
    ...payload,
    ...serializeHeatingSettings(payload.hydraulic_bypass_entities, payload.power_sensor_mode),
  };
}
