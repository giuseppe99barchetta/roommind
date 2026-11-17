/**
 * rs-settings-orphans – rooms whose Home Assistant area was deleted (#494).
 *
 * Such a room rests: its devices are switched off, its entities removed, its learned
 * model kept. It runs again when the area is back, or can be deleted here.
 */
import { html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { RsSettingsBase } from "./rs-settings-base";
import type { HomeAssistant, RoomWithoutArea } from "../../types";
import { localize } from "../../utils/localize";
import { alertStyles } from "../../styles/tokens";
import "../shared/rs-confirm-button";

@customElement("rs-settings-orphans")
export class RsSettingsOrphans extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public rooms: RoomWithoutArea[] = [];
  @state() private _deleted = new Set<string>();
  @state() private _busy = "";
  @state() private _error = "";

  private async _delete(room: RoomWithoutArea): Promise<void> {
    const l = this.hass.language;
    if (this._busy) return;
    this._busy = room.area_id;
    this._error = "";
    try {
      await this.hass.callWS({ type: "roommind/rooms/delete", area_id: room.area_id });
      this._deleted = new Set([...this._deleted, room.area_id]);
    } catch (err) {
      this._error =
        (err as { message?: string } | null)?.message || localize("room.error_delete_fallback", l);
    } finally {
      this._busy = "";
    }
  }

  render() {
    const l = this.hass.language;
    const rooms = this.rooms.filter((r) => !this._deleted.has(r.area_id));
    if (!rooms.length) return html`<p class="note">${localize("orphans.none", l)}</p>`;
    return html`
      ${this._error ? html`<p class="rs-alert" role="alert">${this._error}</p>` : nothing}
      ${rooms.map(
        (room, idx) => html`
          <div class="settings-section ${idx === 0 ? "first" : ""}">
            <rs-list-row
              wrap
              icon="mdi:home-remove-outline"
              .heading=${room.display_name || room.area_id}
              .secondary=${localize("orphans.hint", l)}
            >
              <rs-confirm-button
                slot="end"
                .label=${localize("orphans.delete", l)}
                .accessibleLabel=${`${localize("orphans.delete", l)}: ${room.display_name || room.area_id}`}
                .confirmMessage=${localize("orphans.confirm_delete", l, {
                  name: room.display_name || room.area_id,
                })}
                .disabled=${this._busy === room.area_id}
                destructive
                @confirmed=${() => this._delete(room)}
              ></rs-confirm-button>
            </rs-list-row>
          </div>
        `,
      )}
    `;
  }

  static styles = [RsSettingsBase.settingsBaseStyles, alertStyles];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-orphans": RsSettingsOrphans;
  }
}
