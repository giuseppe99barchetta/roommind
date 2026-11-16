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

@customElement("rs-settings-orphans")
export class RsSettingsOrphans extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public rooms: RoomWithoutArea[] = [];
  @state() private _deleted = new Set<string>();
  @state() private _busy = "";
  @state() private _error = "";

  private async _delete(room: RoomWithoutArea): Promise<void> {
    const l = this.hass.language;
    if (!confirm(localize("orphans.confirm_delete", l, { name: room.display_name }))) return;
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
    if (!rooms.length) return html`<span class="field-hint">${localize("orphans.none", l)}</span>`;
    return html`
      ${rooms.map(
        (room) => html`
          <div class="toggle-row">
            <div class="toggle-text">
              <span class="toggle-label">${room.display_name}</span>
              <span class="toggle-hint">${localize("orphans.hint", l)}</span>
            </div>
            <ha-button ?disabled=${this._busy === room.area_id} @click=${() => this._delete(room)}
              >${localize("orphans.delete", l)}</ha-button
            >
          </div>
        `,
      )}
      ${this._error
        ? html`<span class="field-hint" style="color: var(--error-color)">${this._error}</span>`
        : nothing}
    `;
  }

  static styles = [RsSettingsBase.settingsBaseStyles];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-orphans": RsSettingsOrphans;
  }
}
