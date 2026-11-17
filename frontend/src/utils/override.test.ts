import { describe, expect, test } from "vitest";
import type { RoomConfig } from "../types";
import { QUICK_OVERRIDE_FALLBACK_H, quickMessage, quickOptions } from "./override";

const room = (schedules: { entity_id: string }[] = []) =>
  ({ area_id: "sala", climate_mode: "auto", schedules }) as unknown as RoomConfig;

describe("dashboard quick override on the fork's override contract", () => {
  test("comfort and eco go out with a duration, never until_schedule_change", () => {
    for (const r of [room(), room([{ entity_id: "schedule.sala" }])]) {
      const comfort = quickMessage(r, "comfort");
      expect(comfort).toEqual({
        type: "roommind/override/set",
        area_id: "sala",
        override_type: "boost",
        duration: QUICK_OVERRIDE_FALLBACK_H,
      });
      expect(quickMessage(r, "eco").override_type).toBe("eco");
      expect("until_schedule_change" in quickMessage(r, "eco")).toBe(false);
    }
  });

  test("clear ends the override", () => {
    expect(quickMessage(room(), "schedule")).toEqual({
      type: "roommind/override/clear",
      area_id: "sala",
    });
  });

  test("labels show the duration", () => {
    const labels = quickOptions(room(), "en").map((o) => o.label);
    expect(labels[1]).toContain(`${QUICK_OVERRIDE_FALLBACK_H} h`);
    expect(labels[2]).toContain(`${QUICK_OVERRIDE_FALLBACK_H} h`);
  });
});
