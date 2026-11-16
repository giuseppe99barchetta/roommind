/**
 * RoomMind – dashboard card entry point.
 *
 * Bundled on its own into roommind-card.js, which the integration loads on every
 * dashboard. It must not import panel components: both bundles would define the
 * same custom elements and the second one would fail to load.
 */
import { RoomMindRoomCard } from "./card/roommind-room-card";
import { localize } from "./utils/localize";

interface CustomCardEntry {
  type: string;
  name: string;
  description: string;
  preview?: boolean;
}

function uiLanguage(): string {
  const ha = document.querySelector("home-assistant") as { hass?: { language?: string } } | null;
  return ha?.hass?.language ?? navigator.language ?? "en";
}

// Referenced so the bundler keeps the module that defines the element (c9088d29)
void RoomMindRoomCard;

const w = window as unknown as { customCards?: CustomCardEntry[] };
w.customCards = w.customCards ?? [];
// Getters: HA is not connected yet when this runs, the card picker reads them later.
if (!w.customCards.some((c) => c.type === "roommind-room-card")) {
  w.customCards.push({
    type: "roommind-room-card",
    get name() {
      return localize("roomcard.name", uiLanguage());
    },
    get description() {
      return localize("roomcard.description", uiLanguage());
    },
    preview: true,
  });
}
