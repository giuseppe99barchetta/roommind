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

/** Read HA select events reliably across component implementations. */
export function selectEventValue(event: Event): unknown {
  const select = event.currentTarget as { value?: unknown } | null;
  if (select?.value !== undefined) {
    return select.value;
  }
  return (event as CustomEvent<{ value?: unknown }>).detail?.value;
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
