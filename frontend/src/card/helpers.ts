/** Pure helpers of the room card (no Lit, so node tests can import them). */
import type { HomeAssistant, OverrideType, RoomConfig } from "../types";

/** "1h 20m" / "20m" until *until* (server time, seconds); "" when past. */
export function remainingText(until: number, nowMs: number): string {
  const remaining = until - nowMs / 1000;
  if (remaining <= 0) return "";
  const h = Math.floor(remaining / 3600);
  const m = Math.floor((remaining % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export function roomName(
  room: RoomConfig | undefined,
  hass: Pick<HomeAssistant, "areas">,
  areaId: string,
): string {
  return room?.display_name || hass.areas?.[areaId]?.name || areaId;
}

/**
 * The `roommind/override/set` message, or null when a custom override in auto mode would
 * put the heat target above the room's cooling target (the backend rejects that band).
 * *customC*: the custom target in °C. Auto rooms keep their current cooling target.
 */
export function overrideMessage(
  areaId: string,
  room: RoomConfig | undefined,
  type: OverrideType,
  hours: number,
  customC: number,
): Record<string, unknown> | null {
  const msg: Record<string, unknown> = {
    type: "roommind/override/set",
    area_id: areaId,
    override_type: type,
    duration: hours,
  };
  if (type !== "custom") return msg;
  const mode = room?.climate_mode ?? "auto";
  if (mode === "cool_only") {
    msg.cool = customC;
    return msg;
  }
  msg.heat = customC;
  if (mode === "auto") {
    const cool = room?.live?.cool_target ?? room?.comfort_cool;
    if (cool != null && cool < customC) return null;
    if (cool != null) msg.cool = cool;
  }
  return msg;
}

export function errorText(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  const msg = (err as { message?: string } | null)?.message;
  return msg || fallback;
}
