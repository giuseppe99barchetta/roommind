/**
 * rs-settings-general – General settings: climate control, display options.
 */
import { html, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import "../shared/rs-radio-group";

@customElement("rs-settings-general")
export class RsSettingsGeneral extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public groupByFloor = false;
  @property({ type: Boolean }) public climateControlActive = true;
  @property({ type: String }) public temperatureRoundingMode: "nearest" | "down" | "up" = "nearest";

  render() {
    const l = this.hass.language;

    return html`
      ${this.hass.floors && Object.keys(this.hass.floors).length > 0
        ? html`<div class="settings-section first">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">${localize("settings.group_by_floor", l)}</span>
              </div>
              <ha-switch
                .checked=${this.groupByFloor}
                @change=${(e: Event) =>
                  this._fire("groupByFloor", (e.target as HTMLInputElement).checked)}
              ></ha-switch>
            </div>
          </div>`
        : nothing}

      <div
        class="settings-section ${this.hass.floors && Object.keys(this.hass.floors).length > 0
          ? ""
          : "first"}"
      >
        <div class="toggle-row">
          <div class="toggle-text">
            <span class="toggle-label">${localize("settings.climate_control_active", l)}</span>
            <span class="toggle-hint">${localize("settings.climate_control_hint", l)}</span>
          </div>
          <ha-switch
            .checked=${this.climateControlActive}
            @change=${(e: Event) =>
              this._fire("climateControlActive", (e.target as HTMLInputElement).checked)}
          ></ha-switch>
        </div>
      </div>

      <div class="settings-section">
        <div class="toggle-text">
          <span class="toggle-label">${localize("settings.temperature_rounding", l)}</span>
          <span class="toggle-hint">${localize("settings.temperature_rounding_hint", l)}</span>
        </div>
        <div style="margin-top: 12px">
          <rs-radio-group
            .options=${[
              { value: "nearest", label: localize("settings.temperature_rounding_nearest", l) },
              { value: "down", label: localize("settings.temperature_rounding_down", l) },
              { value: "up", label: localize("settings.temperature_rounding_up", l) },
            ]}
            .selected=${this.temperatureRoundingMode}
            @selected-changed=${(e: CustomEvent<string>) => this._fire("temperatureRoundingMode", e.detail)}
          ></rs-radio-group>
        </div>
      </div>
    `;
  }

  static styles = [RsSettingsBase.settingsBaseStyles];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-general": RsSettingsGeneral;
  }
}
