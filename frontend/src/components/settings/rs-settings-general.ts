/**
 * rs-settings-general – General settings: climate control, display options.
 */
import { html, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { hasFloors } from "../../utils/dashboard";
import "../shared/rs-segmented";

@customElement("rs-settings-general")
export class RsSettingsGeneral extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public groupByFloor = false;
  @property({ type: Boolean }) public climateControlActive = true;
  @property({ type: String }) public temperatureRoundingMode: "nearest" | "down" | "up" = "nearest";

  render() {
    const l = this.hass.language;
    return html`
      <div class="settings-section first">
        <rs-list-row
          switch
          wrap
          .heading=${localize("settings.climate_control_active", l)}
          .secondary=${localize("settings.climate_control_hint", l)}
          .checked=${this.climateControlActive}
          @toggle-changed=${(e: CustomEvent<boolean>) =>
            this._fire("climateControlActive", e.detail)}
        ></rs-list-row>
      </div>
      ${hasFloors(this.hass)
        ? html`<div class="settings-section">
            <rs-list-row
              switch
              wrap
              .heading=${localize("settings.group_by_floor", l)}
              .checked=${this.groupByFloor}
              @toggle-changed=${(e: CustomEvent<boolean>) => this._fire("groupByFloor", e.detail)}
            ></rs-list-row>
          </div>`
        : nothing}
      <div class="settings-section">
        <span class="field-label">${localize("settings.temperature_rounding", l)}</span>
        <p class="note">${localize("settings.temperature_rounding_hint", l)}</p>
        <rs-segmented
          wrap
          .label=${localize("settings.temperature_rounding", l)}
          .options=${[
            { value: "nearest", label: localize("settings.temperature_rounding_nearest", l) },
            { value: "down", label: localize("settings.temperature_rounding_down", l) },
            { value: "up", label: localize("settings.temperature_rounding_up", l) },
          ]}
          .value=${this.temperatureRoundingMode}
          @value-changed=${(e: CustomEvent<{ value: string }>) =>
            this._fire("temperatureRoundingMode", e.detail.value)}
        ></rs-segmented>
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
