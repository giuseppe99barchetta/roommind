/** Dedicated and shared humidity control, separate from thermal equipment. */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type {
  DehumidifierConfig,
  DehumidifierDeviceStatus,
  DehumidifierStatus,
  HomeAssistant,
  RoomConfig,
} from "../types";
import { localize, type TranslationKey } from "../utils/localize";
import { openEntityInfo } from "../utils/events";
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
  @property({ type: Boolean }) public climateControlActive = true;
  @property({ type: Boolean }) public roomControlEnabled = true;
  @property({ type: Number }) public currentHumidity: number | null = null;

  static styles = [
    inputStyles,
    css`
      :host {
        display: block;
      }
      .fields,
      .overview {
        display: grid;
        gap: 16px;
      }
      * {
        box-sizing: border-box;
      }
      .panel,
      .device,
      .room-summary {
        border: 1px solid var(--divider-color, rgba(128, 128, 128, 0.18));
        border-radius: 14px;
        padding: 16px;
        min-width: 0;
      }
      .panel {
        display: grid;
        gap: 14px;
      }
      .panel-heading {
        display: flex;
        align-items: center;
        gap: 10px;
      }
      .step,
      .device-icon {
        display: grid;
        place-items: center;
        flex-shrink: 0;
        width: 30px;
        height: 30px;
        border-radius: 9px;
        color: var(--primary-color);
        background: color-mix(in srgb, var(--primary-color) 10%, transparent);
        font-size: 12px;
        font-weight: 700;
      }
      h4 {
        margin: 0;
        font-size: 14px;
        font-weight: 600;
        color: var(--primary-text-color);
      }
      .eyebrow {
        display: block;
        color: var(--secondary-text-color);
        font-size: 12px;
        margin-bottom: 6px;
      }
      .room-summary {
        background: var(--secondary-background-color);
        display: grid;
        gap: 14px;
      }
      .summary-heading,
      .name,
      .summary-values {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        flex-wrap: wrap;
      }
      .summary-values > div {
        flex: 1;
        min-width: 100px;
      }
      .metric {
        font-size: 28px;
        line-height: 1.2;
        font-weight: 600;
        letter-spacing: -0.04em;
        font-variant-numeric: tabular-nums;
      }
      .metric small {
        font-size: 16px;
        color: var(--secondary-text-color);
        margin-inline-start: 3px;
      }
      .badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 5px 9px;
        border-radius: 8px;
        font-size: 11px;
        line-height: 1.4;
        background: var(--secondary-background-color);
        color: var(--secondary-text-color);
      }
      .badge.active {
        color: var(--primary-color);
        background: color-mix(in srgb, var(--primary-color) 12%, transparent);
      }
      .badge.warning {
        color: var(--warning-color, #e99b22);
        background: color-mix(in srgb, var(--warning-color, #e99b22) 12%, transparent);
      }
      .device {
        display: grid;
        gap: 12px;
      }
      .device-identity {
        display: flex;
        align-items: center;
        gap: 10px;
        min-width: 0;
        flex: 1;
      }
      .device-icon {
        width: 38px;
        height: 38px;
        --mdc-icon-size: 22px;
      }
      .device-identity > div {
        min-width: 0;
      }
      .device-name {
        font-weight: 600;
        overflow-wrap: anywhere;
      }
      .chips {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
      }
      .chip {
        padding: 5px 9px;
        border: 1px solid var(--divider-color, rgba(128, 128, 128, 0.18));
        border-radius: 8px;
        font-size: 12px;
      }
      .chip.host {
        border-style: dashed;
        color: var(--primary-color);
      }
      .notice {
        display: flex;
        align-items: flex-start;
        gap: 10px;
        padding: 12px;
        border-radius: 10px;
        background: var(--secondary-background-color);
      }
      .notice ha-icon {
        --mdc-icon-size: 18px;
        flex-shrink: 0;
        color: var(--primary-color);
      }
      .notice.warning {
        border-inline-start: 3px solid var(--warning-color, #e99b22);
      }
      .notice strong {
        display: block;
        font-size: 12px;
        margin-bottom: 4px;
        color: var(--primary-text-color);
      }
      .choices {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 8px;
      }
      .choices.priority {
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }
      .choice {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        justify-content: flex-start;
        padding: 12px;
        border: 1px solid var(--divider-color, rgba(128, 128, 128, 0.2));
        border-radius: 10px;
        color: var(--primary-text-color);
        line-height: 1.5;
      }
      .choice[aria-pressed="true"] {
        border-color: var(--primary-color);
        background: color-mix(in srgb, var(--primary-color) 8%, transparent);
      }
      .choice strong {
        display: block;
        font-size: 13px;
        margin-bottom: 4px;
      }
      .choice .hint {
        font-size: 12px;
      }
      .room-options {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(min(100%, 190px), 1fr));
        gap: 8px;
      }
      .room-option {
        padding: 8px 10px;
        border: 1px solid var(--divider-color, rgba(128, 128, 128, 0.2));
        border-radius: 10px;
        cursor: pointer;
        font-size: 13px;
        min-width: 0;
        overflow-wrap: anywhere;
      }
      .room-option.selected {
        border-color: color-mix(in srgb, var(--primary-color) 45%, transparent);
        background: color-mix(in srgb, var(--primary-color) 6%, transparent);
      }
      details {
        border-top: 1px solid var(--divider-color, rgba(128, 128, 128, 0.16));
        padding-top: 12px;
      }
      summary {
        cursor: pointer;
        color: var(--secondary-text-color);
        font-size: 13px;
        line-height: 1.6;
      }
      summary:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: 4px;
      }
      .details-body {
        display: grid;
        gap: 12px;
        padding-top: 14px;
      }
      .facts {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 12px;
        margin: 0;
      }
      dt {
        font-size: 12px;
        color: var(--secondary-text-color);
        margin-bottom: 4px;
      }
      dd {
        margin: 0;
        font-size: 16px;
        font-weight: 600;
      }
      .guide {
        margin: 0;
        padding-inline-start: 20px;
        display: grid;
        gap: 10px;
      }
      .numbers {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(min(100%, 140px), 1fr));
        gap: 12px;
      }
      .hint {
        color: var(--secondary-text-color);
        font-size: 13px;
        line-height: 1.5;
        margin: 0;
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
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        justify-self: start;
        min-height: 44px;
        padding: 10px 14px;
        border: 1px solid var(--primary-color);
        border-radius: 10px;
      }
      .configure ha-icon {
        --mdc-icon-size: 18px;
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
      @media (max-width: 480px) {
        .choices.priority {
          grid-template-columns: 1fr;
        }
        .panel,
        .device,
        .room-summary {
          padding: 12px;
        }
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

  private _heading(step: string, title: TranslationKey) {
    return html`<div class="panel-heading">
      <span class="step">${step}</span>
      <h4>${this._label(title)}</h4>
    </div>`;
  }

  private _disabledNotice(room: string) {
    return html`<div class="notice warning" role="status">
      <ha-icon icon="mdi:pause-circle-outline"></ha-icon>
      <div>
        <strong>${this._label("dehumidifier.reason_disabled")}</strong>
        <p class="hint">${localize("dehumidifier.disabled_hint", this.hass.language, { room })}</p>
      </div>
    </div>`;
  }

  private _guide() {
    return html`<details>
      <summary>${this._label("dehumidifier.how_it_works")}</summary>
      <ol class="details-body guide hint">
        <li>${this._label("dehumidifier.guide_device")}</li>
        <li>${this._label("dehumidifier.guide_comfort")}</li>
        <li>${this._label("dehumidifier.guide_shared")}</li>
      </ol>
    </details>`;
  }

  render() {
    if (!this.editing) return this._view();
    const config = this.config;
    const sharedDevices = (this.live?.devices ?? []).filter((d) => d.owner_area_id !== this.areaId);
    return html`<div class="fields">
      <p class="hint">${this._label("dehumidifier.intro")}</p>
      ${this._guide()}
      ${!this.climateControlActive || (config && !this.roomControlEnabled)
        ? this._disabledNotice(this._roomName(this.areaId))
        : nothing}
      <section class="panel">
        ${this._heading("1", "dehumidifier.device")}
        <rs-entity-picker-field
          .hass=${this.hass}
          .label=${this._label("dehumidifier.device")}
          .value=${config?.entity_id ?? ""}
          .includeDomains=${["humidifier", "switch"]}
          @value-changed=${this._selectDevice}
        ></rs-entity-picker-field>
        <p class="hint">${this._label("dehumidifier.device_hint")}</p>
        ${!config && sharedDevices.length
          ? html`<div class="notice">
              <ha-icon icon="mdi:home-group"></ha-icon>
              <div>
                <strong>${this._label("dehumidifier.shared_available")}</strong>
                <p class="hint">
                  ${sharedDevices.map((d) => this._roomName(d.owner_area_id)).join(", ")}.
                  ${this._label("dehumidifier.shared_available_hint")}
                </p>
              </div>
            </div>`
          : nothing}
        ${config
          ? html`
              <h4>${this._label("dehumidifier.mode")}</h4>
              <div class="choices" role="group" aria-label=${this._label("dehumidifier.mode")}>
                ${(["auto", "manual"] as const).map(
                  (mode) =>
                    html` <button
                      type="button"
                      class="choice"
                      aria-pressed=${config.mode === mode}
                      @click=${() => this._deviceChanged({ ...config, mode })}
                    >
                      <strong>${this._label(`dehumidifier.${mode}`)}</strong>
                      <span class="hint"
                        >${this._label(
                          mode === "auto"
                            ? "dehumidifier.auto_hint"
                            : "dehumidifier.manual_option_hint",
                        )}</span
                      >
                    </button>`,
                )}
              </div>
            `
          : nothing}
      </section>
      ${config
        ? html`<section class="panel">
            ${this._heading("2", "dehumidifier.served_rooms")}
            <p class="hint">${this._label("dehumidifier.coverage_hint")}</p>
            <div class="chips">
              <span class="chip host"
                >${this._roomName(this.areaId)} · ${this._label("dehumidifier.host_room")}</span
              >
            </div>
            <fieldset>
              <legend class="eyebrow">${this._label("dehumidifier.additional_rooms")}</legend>
              <div class="room-options">
                ${Object.entries(this.rooms)
                  .filter(([id, r]) => id !== this.areaId && !r.is_outdoor)
                  .map(
                    ([id]) =>
                      html` <label
                        class="room-option ${config.served_area_ids.includes(id) ? "selected" : ""}"
                      >
                        <ha-checkbox
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
                        >${this._roomName(id)}
                      </label>`,
                  )}
              </div>
            </fieldset>
            ${config.served_area_ids.length
              ? html`<p class="hint">${this._label("dehumidifier.shared_hint")}</p>`
              : nothing}
          </section>`
        : nothing}
      <section class="panel">
        ${this._heading(config ? "3" : "2", "dehumidifier.room_comfort")}
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
        <p class="hint">${this._label("dehumidifier.tolerance_hint")}</p>
        <h4>${this._label("dehumidifier.priority")}</h4>
        <div
          class="choices priority"
          role="group"
          aria-label=${this._label("dehumidifier.priority")}
        >
          ${(["comfort", "balanced", "energy"] as const).map(
            (priority) =>
              html` <button
                type="button"
                class="choice"
                aria-pressed=${this.humidity.humidity_priority === priority}
                @click=${() => this._humidityChanged({ humidity_priority: priority })}
              >
                <strong>${this._label(`dehumidifier.priority_${priority}`)}</strong>
                <span class="hint">${this._label(`dehumidifier.priority_${priority}_hint`)}</span>
              </button>`,
          )}
        </div>
      </section>
      ${config
        ? html`<details>
            <summary>${this._label("dehumidifier.protections")}</summary>
            <div class="details-body">
              <p class="hint">${this._label("dehumidifier.timing_hint")}</p>
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
            </div>
          </details>`
        : nothing}
    </div>`;
  }

  private _deviceView(device: DehumidifierDeviceStatus) {
    const shared = device.served_area_ids.length > 1;
    const stateLabel = !device.available
      ? "dehumidifier.reason_unavailable"
      : device.state !== "on"
        ? "dehumidifier.off"
        : device.action === "drying"
          ? "dehumidifier.drying"
          : device.action === "idle"
            ? "dehumidifier.idle"
            : "dehumidifier.on";
    return html`<div class="device">
      <div class="name">
        <div class="device-identity">
          <ha-icon class="device-icon" icon="mdi:air-humidifier"></ha-icon>
          <div>
            <button
              type="button"
              class="device-name"
              @click=${() => openEntityInfo(this, device.entity_id)}
            >
              ${this.hass.states[device.entity_id]?.attributes.friendly_name ?? device.entity_id}
            </button>
            <p class="hint">
              ${this._label("dehumidifier.host")}: ${this._roomName(device.owner_area_id)}
            </p>
          </div>
        </div>
        <span class="badge ${device.available && device.state === "on" ? "active" : ""}"
          >${this._label(stateLabel)}</span
        >
      </div>
      <div>
        <span class="eyebrow"
          >${this._label(shared ? "dehumidifier.shared_device" : "dehumidifier.local_device")}</span
        >
        <div class="chips">
          ${device.served_area_ids.map(
            (id) =>
              html`<span class="chip ${id === device.owner_area_id ? "host" : ""}"
                >${this._roomName(id)}</span
              >`,
          )}
        </div>
      </div>
      ${device.reason === "disabled"
        ? this._disabledNotice(this._roomName(device.owner_area_id))
        : device.reason
          ? html`<div
              class="notice ${device.reason === "unavailable" || device.reason === "error"
                ? "warning"
                : ""}"
            >
              <ha-icon
                icon=${device.reason === "manual"
                  ? "mdi:hand-back-right-outline"
                  : "mdi:pause-circle-outline"}
              ></ha-icon>
              <div>
                <strong>${this._label(`dehumidifier.reason_${device.reason}`)}</strong>
                ${device.reason === "manual"
                  ? html`<p class="hint">${this._label("dehumidifier.manual_hint")}</p>`
                  : nothing}
              </div>
            </div>`
          : device.state === "off" && !device.requested
            ? html`<p class="hint">${this._label("dehumidifier.waiting_hint")}</p>`
            : nothing}
      ${device.commanded != null &&
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
      ${device.pending_rooms.length
        ? html`<p class="hint">
            ${this._label("dehumidifier.requests")}:
            ${device.pending_rooms.map((id) => this._roomName(id)).join(", ")}
          </p>`
        : nothing}
      ${device.target_humidity != null || device.humidity_floor != null
        ? html`<details>
            <summary>${this._label("dehumidifier.device_details")}</summary>
            <div class="details-body">
              <dl class="facts">
                ${device.target_humidity != null
                  ? html`<div>
                      <dt>${this._label("dehumidifier.device_target")}</dt>
                      <dd>${device.target_humidity}%</dd>
                    </div>`
                  : nothing}
                ${device.humidity_floor != null
                  ? html`<div>
                      <dt>${this._label("dehumidifier.floor")}</dt>
                      <dd>${device.humidity_floor}%</dd>
                    </div>`
                  : nothing}
              </dl>
              ${shared
                ? html`<p class="hint">${this._label("dehumidifier.device_target_hint")}</p>`
                : nothing}
            </div>
          </details>`
        : nothing}
    </div>`;
  }

  private _view() {
    const devices = this.live?.devices ?? [];
    return html`<div class="overview">
      <div class="room-summary">
        <div class="summary-heading">
          <h4>${this._label("dehumidifier.room_comfort")}</h4>
          <span class="badge ${this.humidity.humidity_comfort_enabled ? "active" : ""}"
            >${this._label(
              this.humidity.humidity_comfort_enabled
                ? "dehumidifier.comfort_enabled"
                : "dehumidifier.comfort_disabled",
            )}</span
          >
        </div>
        <div class="summary-values">
          ${this.currentHumidity != null
            ? html`<div>
                <span class="eyebrow">${this._label("dehumidifier.measured")}</span
                ><span class="metric">${Math.round(this.currentHumidity)}<small>%</small></span>
              </div>`
            : nothing}
          <div>
            <span class="eyebrow">${this._label("dehumidifier.target")}</span
            ><span class="metric">${this.humidity.humidity_target}<small>%</small></span>
          </div>
        </div>
        ${!this.humidity.humidity_comfort_enabled
          ? html`<p class="hint">${this._label("dehumidifier.comfort_off_hint")}</p>`
          : nothing}
      </div>
      ${!devices.length
        ? html`<div class="notice">
            <ha-icon icon="mdi:air-humidifier"></ha-icon>
            <p class="hint">
              ${this._label(this.config ? "dehumidifier.status_pending" : "dehumidifier.empty")}
            </p>
          </div>`
        : nothing}
      ${devices.map((device) => this._deviceView(device))}
      ${this.live?.request
        ? html`<p class="hint">
            ${this._label(
              this.live.request === "mold"
                ? "dehumidifier.request_mold"
                : "dehumidifier.request_comfort",
            )}
          </p>`
        : nothing}
      <button
        class="configure"
        type="button"
        @click=${() =>
          this.dispatchEvent(new CustomEvent("edit-click", { bubbles: true, composed: true }))}
      >
        <ha-icon icon=${this.config || devices.length ? "mdi:tune-variant" : "mdi:plus"}></ha-icon>
        ${this._label(
          this.config || devices.length ? "dehumidifier.configure" : "dehumidifier.add",
        )}
      </button>
    </div>`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-dehumidifier-section": RsDehumidifierSection;
  }
}
