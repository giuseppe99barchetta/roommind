/**
 * rs-air-quality-section – CO2/VOC sensors, their thresholds and the ventilation unit RoomMind
 * runs while the air is bad (#267). Fires `air-quality-changed` with {key, value}.
 */
import { LitElement, html, css } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../types";
import { localize } from "../utils/localize";
import "./shared/rs-entity-picker-field";

/** Mirrors MIN/MAX/DEFAULT_CO2_THRESHOLD in const.py. */
const CO2_MIN = 800;
const CO2_MAX = 5000;
const CO2_DEFAULT = 1000;

export interface AirQualityConfig {
  co2_sensor: string;
  co2_threshold: number;
  voc_sensor: string;
  voc_threshold: number | null;
  ventilation_entity: string;
}

@customElement("rs-air-quality-section")
export class RsAirQualitySection extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public config: AirQualityConfig = {
    co2_sensor: "",
    co2_threshold: CO2_DEFAULT,
    voc_sensor: "",
    voc_threshold: null,
    ventilation_entity: "",
  };

  render() {
    const l = this.hass.language;
    const c = this.config;
    return html`
      <div class="section-subtitle">${localize("air_quality.title", l)}</div>
      <p class="hint">${localize("air_quality.hint", l)}</p>
      <rs-entity-picker-field
        .hass=${this.hass}
        .label=${localize("air_quality.co2_sensor", l)}
        .value=${c.co2_sensor}
        .includeDomains=${["sensor"]}
        .entityFilter=${(s: { attributes: Record<string, unknown> }) =>
          s.attributes.device_class === "carbon_dioxide"}
        @value-changed=${(e: CustomEvent<string>) => this._fire(e, "co2_sensor", e.detail ?? "")}
      ></rs-entity-picker-field>
      ${c.co2_sensor
        ? html`<ha-textfield
            type="number"
            .label=${localize("air_quality.co2_threshold", l)}
            suffix="ppm"
            min=${CO2_MIN}
            max=${CO2_MAX}
            step="50"
            .value=${String(c.co2_threshold ?? CO2_DEFAULT)}
            @change=${(e: Event) => {
              const v = Math.round(Number((e.target as HTMLInputElement).value));
              if (Number.isFinite(v)) {
                this._fire(e, "co2_threshold", Math.min(CO2_MAX, Math.max(CO2_MIN, v)));
              }
            }}
          ></ha-textfield>`
        : ""}
      <rs-entity-picker-field
        .hass=${this.hass}
        .label=${localize("air_quality.voc_sensor", l)}
        .value=${c.voc_sensor}
        .includeDomains=${["sensor"]}
        @value-changed=${(e: CustomEvent<string>) => this._fire(e, "voc_sensor", e.detail ?? "")}
      ></rs-entity-picker-field>
      ${c.voc_sensor
        ? html`<ha-textfield
              type="number"
              .label=${localize("air_quality.voc_threshold", l)}
              min="0.001"
              step="any"
              .value=${c.voc_threshold == null ? "" : String(c.voc_threshold)}
              @change=${(e: Event) => {
                const raw = (e.target as HTMLInputElement).value.trim();
                const v = Number(raw);
                this._fire(e, "voc_threshold", raw === "" || !(v > 0) ? null : v);
              }}
            ></ha-textfield>
            <p class="hint">${localize("air_quality.voc_threshold_hint", l)}</p>`
        : ""}
      <rs-entity-picker-field
        .hass=${this.hass}
        .label=${localize("air_quality.ventilation_entity", l)}
        .value=${c.ventilation_entity}
        .includeDomains=${["fan", "switch", "input_boolean"]}
        @value-changed=${(e: CustomEvent<string>) =>
          this._fire(e, "ventilation_entity", e.detail ?? "")}
      ></rs-entity-picker-field>
      <p class="hint">${localize("air_quality.ventilation_hint", l)}</p>
    `;
  }

  private _fire(e: Event, key: keyof AirQualityConfig, value: string | number | null) {
    e.stopPropagation();
    this.dispatchEvent(
      new CustomEvent("air-quality-changed", {
        detail: { key, value },
        bubbles: true,
        composed: true,
      }),
    );
  }

  static styles = css`
    :host {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-top: 20px;
    }
    .section-subtitle {
      font-weight: 500;
    }
    .hint {
      margin: 0;
      font-size: 12px;
      color: var(--secondary-text-color);
    }
    ha-textfield {
      width: 100%;
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-air-quality-section": RsAirQualitySection;
  }
}
