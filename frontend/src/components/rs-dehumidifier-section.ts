/** Dedicated and shared humidity control, separate from thermal equipment. */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { DehumidifierConfig, DehumidifierStatus, HomeAssistant, RoomConfig } from "../types";
import { localize, type TranslationKey } from "../utils/localize";
import { getSelectValue, openEntityInfo } from "../utils/events";
import { inputStyles } from "../styles/input-styles";
import "./shared/rs-entity-picker-field";
import "./shared/rs-threshold-field";
import "./shared/rs-toggle-row";

export type HumiditySettings = Required<
  Pick<
    RoomConfig,
    "humidity_comfort_enabled" | "humidity_target" | "humidity_tolerance" | "humidity_priority"
  >
>;

@customElement("rs-dehumidifier-section")
export class RsDehumidifierSection extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: String }) public areaId = "";
  @property({ attribute: false }) public rooms: Record<string, RoomConfig> = {};
  @property({ attribute: false }) public config: DehumidifierConfig | null = null;
  @property({ attribute: false }) public live?: DehumidifierStatus;
  @property({ attribute: false }) public humidity!: HumiditySettings;
  @property({ type: Boolean }) public editing = false;

  static styles = [
    inputStyles,
    css`
      :host {
        display: block;
      }
      .fields {
        display: grid;
        gap: 16px;
      }
      .numbers {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 12px;
      }
      .hint {
        color: var(--secondary-text-color);
        font-size: 13px;
        line-height: 1.5;
        margin: 0;
      }
      .device {
        border-top: 1px solid var(--divider-color);
        padding-top: 12px;
        margin-top: 12px;
      }
      .device:first-child {
        border-top: 0;
        padding-top: 0;
        margin-top: 0;
      }
      .name {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
      }
      button {
        font: inherit;
        color: var(--primary-color);
        background: none;
        border: 0;
        cursor: pointer;
        padding: 4px 0;
        text-align: start;
      }
      button:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: 2px;
      }
      .configure {
        display: block;
        min-height: 44px;
        margin-top: 12px;
        padding: 10px 14px;
        border: 1px solid var(--primary-color);
        border-radius: 10px;
      }
      label {
        display: flex;
        align-items: center;
        gap: 8px;
      }
      fieldset {
        border: 0;
        margin: 0;
        padding: 0;
      }
      legend {
        margin-bottom: 8px;
      }
    `,
  ];

  private _label(key: TranslationKey) {
    return localize(key, this.hass.language);
  }

  private _roomName(id: string) {
    return this.rooms[id]?.display_name || this.hass.areas?.[id]?.name || id;
  }

  private _deviceChanged(config: DehumidifierConfig | null) {
    this.dispatchEvent(
      new CustomEvent("dehumidifier-changed", { detail: config, bubbles: true, composed: true }),
    );
  }

  private _humidityChanged(changes: Partial<HumiditySettings>) {
    this.dispatchEvent(
      new CustomEvent("humidity-changed", { detail: changes, bubbles: true, composed: true }),
    );
  }

  private _selectDevice(e: CustomEvent<string>) {
    e.stopPropagation();
    this._deviceChanged(
      e.detail
        ? {
            served_area_ids: [],
            mode: "auto",
            min_run_minutes: 5,
            min_off_minutes: 5,
            power_watts: 0,
            ...this.config,
            entity_id: e.detail,
          }
        : null,
    );
  }

  private _number(key: "min_run_minutes" | "min_off_minutes" | "power_watts", value: number) {
    if (this.config)
      this._deviceChanged({
        ...this.config,
        [key]: Math.max(0, Math.min(key === "power_watts" ? 100000 : 1440, value)),
      });
  }

  render() {
    if (!this.editing) return this._view();
    const config = this.config;
    return html`<div class="fields">
      <rs-entity-picker-field
        .hass=${this.hass}
        .label=${this._label("dehumidifier.device")}
        .value=${config?.entity_id ?? ""}
        .includeDomains=${["humidifier", "switch"]}
        @value-changed=${this._selectDevice}
      ></rs-entity-picker-field>
      <p class="hint">${this._label("dehumidifier.device_hint")}</p>
      ${config
        ? html`
            <ha-select
              .label=${this._label("dehumidifier.mode")}
              .value=${config.mode}
              @selected=${(e: Event) => {
                const mode = getSelectValue(e);
                if (mode === "auto" || mode === "manual") this._deviceChanged({ ...config, mode });
              }}
              @closed=${(e: Event) => e.stopPropagation()}
            >
              <ha-list-item value="auto">${this._label("dehumidifier.auto")}</ha-list-item>
              <ha-list-item value="manual">${this._label("dehumidifier.manual")}</ha-list-item>
            </ha-select>
            <p class="hint">${this._label("dehumidifier.manual_hint")}</p>
            <fieldset>
              <legend>${this._label("dehumidifier.served_rooms")}</legend>
              <p class="hint">${this._label("dehumidifier.host_included")}</p>
              ${Object.entries(this.rooms)
                .filter(([id, r]) => id !== this.areaId && !r.is_outdoor)
                .map(
                  ([id]) =>
                    html` <label
                      ><ha-checkbox
                        .checked=${config.served_area_ids.includes(id)}
                        @change=${(e: Event) => {
                          const selected = (e.target as HTMLInputElement).checked;
                          this._deviceChanged({
                            ...config,
                            served_area_ids: selected
                              ? [...new Set([...config.served_area_ids, id])]
                              : config.served_area_ids.filter((a) => a !== id),
                          });
                        }}
                      ></ha-checkbox
                      >${this._roomName(id)}</label
                    >`,
                )}
            </fieldset>
            ${config.served_area_ids.some((id) => id !== this.areaId)
              ? html`<p class="hint">${this._label("dehumidifier.shared_hint")}</p>`
              : nothing}
            <div class="numbers">
              ${(["min_run_minutes", "min_off_minutes", "power_watts"] as const).map(
                (key) =>
                  html` <rs-threshold-field
                    .label=${this._label(`dehumidifier.${key}`)}
                    .value=${config[key]}
                    .min=${0}
                    .max=${key === "power_watts" ? 100000 : 1440}
                    .step=${1}
                    .suffix=${key === "power_watts" ? "W" : "min"}
                    @value-changed=${(e: CustomEvent<number>) => this._number(key, e.detail)}
                  ></rs-threshold-field>`,
              )}
            </div>
            <p class="hint">${this._label("dehumidifier.power_hint")}</p>
          `
        : nothing}
      <rs-toggle-row
        .label=${this._label("dehumidifier.comfort")}
        .checked=${this.humidity.humidity_comfort_enabled}
        @toggle-changed=${(e: CustomEvent<boolean>) =>
          this._humidityChanged({ humidity_comfort_enabled: e.detail })}
      ></rs-toggle-row>
      <p class="hint">${this._label("dehumidifier.comfort_hint")}</p>
      <div class="numbers">
        <rs-threshold-field
          .label=${this._label("dehumidifier.target")}
          .value=${this.humidity.humidity_target}
          .min=${30}
          .max=${80}
          .step=${1}
          suffix="%"
          @value-changed=${(e: CustomEvent<number>) =>
            this._humidityChanged({ humidity_target: Math.max(30, Math.min(80, e.detail)) })}
        ></rs-threshold-field>
        <rs-threshold-field
          .label=${this._label("dehumidifier.tolerance")}
          .value=${this.humidity.humidity_tolerance}
          .min=${0}
          .max=${20}
          .step=${1}
          suffix="%"
          @value-changed=${(e: CustomEvent<number>) =>
            this._humidityChanged({ humidity_tolerance: Math.max(0, Math.min(20, e.detail)) })}
        ></rs-threshold-field>
      </div>
      <ha-select
        .label=${this._label("dehumidifier.priority")}
        .value=${this.humidity.humidity_priority}
        @selected=${(e: Event) => {
          const priority = getSelectValue(e);
          if (priority === "comfort" || priority === "balanced" || priority === "energy")
            this._humidityChanged({ humidity_priority: priority });
        }}
        @closed=${(e: Event) => e.stopPropagation()}
      >
        ${(["comfort", "balanced", "energy"] as const).map(
          (p) =>
            html`<ha-list-item .value=${p}
              >${this._label(`dehumidifier.priority_${p}`)}</ha-list-item
            >`,
        )}
      </ha-select>
    </div>`;
  }

  private _view() {
    const devices = this.live?.devices ?? [];
    return html`
      ${!devices.length ? html`<p class="hint">${this._label("dehumidifier.empty")}</p>` : nothing}
      ${devices.map(
        (device) =>
          html`<div class="device">
            <div class="name">
              <button @click=${() => openEntityInfo(this, device.entity_id)}>
                ${this.hass.states[device.entity_id]?.attributes.friendly_name ?? device.entity_id}
              </button>
              <span
                >${device.state === "on"
                  ? this._label(
                      device.action === "drying"
                        ? "dehumidifier.drying"
                        : device.action === "idle"
                          ? "dehumidifier.idle"
                          : "dehumidifier.on",
                    )
                  : this._label(
                      device.available ? "dehumidifier.off" : "dehumidifier.reason_unavailable",
                    )}</span
              >
            </div>
            <p class="hint">
              ${this._label("dehumidifier.host")}: ${this._roomName(device.owner_area_id)}
            </p>
            <p class="hint">
              ${this._label("dehumidifier.served_rooms")}:
              ${device.served_area_ids.map((id) => this._roomName(id)).join(", ")}
            </p>
            ${device.commanded !== null &&
            (device.commanded ? device.state !== "on" : device.state === "on")
              ? html`<p class="hint">
                  ${this._label(
                    device.commanded ? "dehumidifier.command_on" : "dehumidifier.command_off",
                  )}
                </p>`
              : nothing}
            ${this.live?.assigned_entity_id === device.entity_id
              ? html`<p class="hint">${this._label("dehumidifier.assigned")}</p>`
              : nothing}
            ${device.reason
              ? html`<p class="hint">${this._label(`dehumidifier.reason_${device.reason}`)}</p>`
              : nothing}
            ${device.pending_rooms.length
              ? html`<p class="hint">
                  ${this._label("dehumidifier.requests")}:
                  ${device.pending_rooms.map((id) => this._roomName(id)).join(", ")}
                </p>`
              : nothing}
            ${device.target_humidity != null
              ? html`<p class="hint">
                  ${this._label("dehumidifier.device_target")}: ${device.target_humidity}%
                </p>`
              : nothing}
            ${device.humidity_floor != null
              ? html`<p class="hint">
                  ${this._label("dehumidifier.floor")}: ${device.humidity_floor}%
                </p>`
              : nothing}
          </div>`,
      )}
      ${this.live?.request
        ? html`<p class="hint">
            ${this._label(
              this.live.request === "mold"
                ? "dehumidifier.request_mold"
                : "dehumidifier.request_comfort",
            )}
          </p>`
        : nothing}
      <p class="hint">
        ${this._label("dehumidifier.comfort")}:
        ${this._label(
          this.humidity.humidity_comfort_enabled ? "dehumidifier.on" : "dehumidifier.off",
        )},
        ${this.humidity.humidity_target}%
      </p>
      <button
        class="configure"
        type="button"
        @click=${() =>
          this.dispatchEvent(new CustomEvent("edit-click", { bubbles: true, composed: true }))}
      >
        ${this._label(
          this.config || devices.length ? "dehumidifier.configure" : "dehumidifier.add",
        )}
      </button>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-dehumidifier-section": RsDehumidifierSection;
  }
}
