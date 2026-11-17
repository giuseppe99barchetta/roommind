/**
 * rs-settings-head-offset – AC sensor offset (#461): switch and the offsets learned per AC.
 */
import { html } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";

/** {entity_id: {"heat"|"cool"|"idle": [offset_k, samples]}} as stored by the backend. */
export type HeadOffsets = Record<string, Record<string, [number, number]>>;

const STATES = ["heat", "cool", "idle"] as const;

@customElement("rs-settings-head-offset")
export class RsSettingsHeadOffset extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public acHeadOffsetEnabled = false;
  @property({ attribute: false }) public acHeadOffsets: HeadOffsets = {};

  private _value(entry: [number, number] | undefined): string {
    if (!entry) return "–";
    const [k, n] = entry;
    return `${k >= 0 ? "+" : ""}${k.toFixed(1)} K (${n})`;
  }

  render() {
    const l = this.hass.language;
    const acs = Object.keys(this.acHeadOffsets ?? {});
    return html`
      <div class="settings-section first">
        <rs-list-row
          switch
          wrap
          .heading=${localize("head_offset.title", l)}
          .secondary=${localize("head_offset.hint", l)}
          .checked=${this.acHeadOffsetEnabled}
          @toggle-changed=${(e: CustomEvent<boolean>) =>
            this._fire("acHeadOffsetEnabled", e.detail)}
        ></rs-list-row>
      </div>
      <div class="field-hint" style="margin-top: 12px">
        ${acs.length
          ? html`<strong>${localize("head_offset.learned", l)}</strong>
              <table style="width: 100%; margin-top: 4px">
                <tr>
                  <th></th>
                  ${STATES.map((s) => html`<th>${localize(`head_offset.${s}`, l)}</th>`)}
                </tr>
                ${acs.map(
                  (eid) =>
                    html`<tr>
                      <td>${this.hass.states[eid]?.attributes?.friendly_name ?? eid}</td>
                      ${STATES.map(
                        (s) => html`<td>${this._value(this.acHeadOffsets[eid]?.[s])}</td>`,
                      )}
                    </tr>`,
                )}
              </table>`
          : localize("head_offset.none", l)}
      </div>
    `;
  }

  static styles = [RsSettingsBase.settingsBaseStyles];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-head-offset": RsSettingsHeadOffset;
  }
}
