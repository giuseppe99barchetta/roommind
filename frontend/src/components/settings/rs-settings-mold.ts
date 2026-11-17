/**
 * rs-settings-mold – Mold risk detection & prevention settings. The fork's prevention: how long
 * the risk must last, dehumidifying and its minimum temperature; no intensity choice and no
 * global wall factor (the fork keeps the wall factor per room, in the room's sensors).
 */
import { html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { RsSettingsBase } from "./rs-settings-base";
import "../shared/rs-number-field";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";

@customElement("rs-settings-mold")
export class RsSettingsMold extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public moldDetectionEnabled = false;
  @property({ type: Number }) public moldHumidityThreshold = 70;
  @property({ type: Number }) public moldSustainedMinutes = 30;
  @property({ type: Boolean }) public moldPreventionEnabled = false;
  @property({ type: Number }) public moldPreventionSustainedMinutes = 15;
  @property({ type: Boolean }) public moldPreventionDehumidificationEnabled = true;
  @property({ type: Number }) public moldPreventionDryMinTemperature = 23;

  render() {
    const l = this.hass.language;

    return html`
      <div class="settings-section first">
        <rs-list-row
          switch
          wrap
          .heading=${localize("mold.detection", l)}
          .secondary=${localize("mold.detection_desc", l)}
          .checked=${this.moldDetectionEnabled}
          @toggle-changed=${(e: CustomEvent<boolean>) =>
            this._fire("moldDetectionEnabled", e.detail)}
        ></rs-list-row>
        ${this.moldDetectionEnabled
          ? html`
              <div class="threshold-grid sub">
                <rs-number-field
                  .label=${localize("mold.threshold", l)}
                  suffix="%"
                  .hint=${localize("mold.threshold_hint", l)}
                  .min=${50}
                  .max=${90}
                  .value=${this.moldHumidityThreshold}
                  @value-changed=${(e: CustomEvent<{ value: number }>) =>
                    this._fire("moldHumidityThreshold", e.detail.value)}
                ></rs-number-field>
                <rs-number-field
                  .label=${localize("mold.sustained", l)}
                  suffix="min"
                  .hint=${localize("mold.sustained_hint", l)}
                  .min=${5}
                  .max=${120}
                  .value=${this.moldSustainedMinutes}
                  @value-changed=${(e: CustomEvent<{ value: number }>) =>
                    this._fire("moldSustainedMinutes", e.detail.value)}
                ></rs-number-field>
              </div>
            `
          : nothing}
      </div>

      <div class="settings-section">
        <rs-list-row
          switch
          wrap
          .heading=${localize("mold.prevention", l)}
          .secondary=${localize("mold.prevention_desc", l)}
          .checked=${this.moldPreventionEnabled}
          @toggle-changed=${(e: CustomEvent<boolean>) =>
            this._fire("moldPreventionEnabled", e.detail)}
        ></rs-list-row>
        ${this.moldPreventionEnabled
          ? html`
              <div class="threshold-grid sub">
                <rs-number-field
                  .label=${localize("mold.prevention_sustained", l)}
                  suffix="min"
                  .hint=${localize("mold.prevention_sustained_hint", l)}
                  .min=${0}
                  .max=${120}
                  .value=${this.moldPreventionSustainedMinutes}
                  @value-changed=${(e: CustomEvent<{ value: number }>) =>
                    this._fire("moldPreventionSustainedMinutes", e.detail.value)}
                ></rs-number-field>
              </div>
              <rs-list-row
                switch
                wrap
                .heading=${localize("mold.dehumidification", l)}
                .secondary=${localize("mold.dehumidification_desc", l)}
                .checked=${this.moldPreventionDehumidificationEnabled}
                @toggle-changed=${(e: CustomEvent<boolean>) =>
                  this._fire("moldPreventionDehumidificationEnabled", e.detail)}
              ></rs-list-row>
              ${this.moldPreventionDehumidificationEnabled
                ? html`<div class="threshold-grid sub">
                    <rs-number-field
                      .hass=${this.hass}
                      kind="temperature"
                      .label=${localize("mold.dehumidification_min_temperature", l)}
                      .hint=${localize("mold.dehumidification_min_temperature_hint", l)}
                      .min=${15}
                      .max=${30}
                      .value=${this.moldPreventionDryMinTemperature}
                      @value-changed=${(e: CustomEvent<{ value: number }>) =>
                        this._fire("moldPreventionDryMinTemperature", e.detail.value)}
                    ></rs-number-field>
                  </div>`
                : nothing}
            `
          : nothing}
      </div>
    `;
  }

  static styles = [
    RsSettingsBase.settingsBaseStyles,
    css`
      .sub {
        margin-top: var(--rs-space-3);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-mold": RsSettingsMold;
  }
}
