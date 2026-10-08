/** Read-only safety preview. Never sends commands to physical devices. */
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";

interface PreviewRoom {
  watts: number;
  source: "learned" | "fallback" | "unknown";
  samples: number;
  already_running: boolean;
  would_allow: boolean;
  reason: "eligible" | "control_disabled" | "room_safety" | "compressor_protection" | "power_budget";
  current_decision_reasons: string[];
}
interface ControlPreview {
  read_only: true;
  mode: string;
  house_available_watts: number | null;
  power_sensor_healthy: boolean;
  power_sensor_age_seconds: number | null;
  boiler_state: string;
  bypass_acknowledged: boolean;
  boiler_demand_rooms: string[];
  rooms: Record<string, PreviewRoom>;
}

@customElement("rs-settings-preview")
export class RsSettingsPreview extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @state() private _mode: "heating" | "cooling" | "dry" = "cooling";
  @state() private _result?: ControlPreview;
  @state() private _loading = false;
  @state() private _error = false;

  static styles = css`
    :host { display: block; font-size: 13px; }
    .controls { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
    select, button { padding: 8px 12px; border-radius: 9px; background: var(--card-background-color); color: var(--primary-text-color); border: 1px solid var(--divider-color); }
    button { cursor: pointer; }
    button:disabled { opacity: .6; cursor: default; }
    .summary { margin: 12px 0; color: var(--secondary-text-color); line-height: 1.6; }
    .room { padding: 10px 0; border-top: 1px solid var(--divider-color); display: grid; gap: 3px; }
    .room strong { color: var(--primary-text-color); }
    .reason { color: var(--secondary-text-color); }
  `;

  private async _refresh() {
    this._loading = true;
    this._error = false;
    try {
      this._result = await this.hass.callWS<ControlPreview>({
        type: "roommind/control/preview",
        mode: this._mode,
      });
    } catch {
      this._error = true;
    } finally {
      this._loading = false;
    }
  }

  render() {
    const lang = this.hass.language;
    const r = this._result;
    return html`
      <div class="controls">
        <select
          aria-label=${localize("preview.mode", lang)}
          .value=${this._mode}
          @change=${(e: Event) => {
            this._mode = (e.target as HTMLSelectElement).value as typeof this._mode;
            this._result = undefined;
          }}
        >
          <option value="heating">${localize("heat_source.budget_heating", lang)}</option>
          <option value="cooling">${localize("heat_source.budget_cooling", lang)}</option>
          <option value="dry">${localize("heat_source.budget_dry", lang)}</option>
        </select>
        <button ?disabled=${this._loading} @click=${() => this._refresh()}>
          ${localize("preview.run", lang)}
        </button>
      </div>
      <div class="summary">${localize("preview.scope", lang)}</div>
      ${this._error ? html`<div>${localize("preview.error", lang)}</div>` : nothing}
      ${r
        ? html`
            <div class="summary">
              ${localize("preview.headroom", lang)}:
              ${r.house_available_watts === null ? "—" : `${Math.round(r.house_available_watts)} W`}
              · ${localize("preview.meter", lang)}:
              ${r.power_sensor_healthy ? localize("preview.healthy", lang) : localize("preview.unavailable", lang)}
              ${r.power_sensor_age_seconds !== null ? `(${Math.round(r.power_sensor_age_seconds)} s)` : nothing}
              · ${localize("preview.boiler", lang)}: ${r.boiler_state}
              · ${localize("preview.bypass", lang)}:
              ${r.bypass_acknowledged ? localize("preview.acknowledged", lang) : localize("preview.not_acknowledged", lang)}
            </div>
            ${Object.entries(r.rooms).map(
              ([areaId, room]) => html`
                <div class="room">
                  <strong>${areaId.replaceAll("_", " ")}</strong>
                  <span>${room.watts} W · ${localize(`heat_source.budget_${room.source}`, lang)}</span>
                  <span class="reason">${localize(`preview.reason_${room.reason}`, lang)}</span>
                  ${room.current_decision_reasons.length
                    ? html`<span class="reason">${localize("preview.current_reasons", lang)}: ${room.current_decision_reasons.join(", ")}</span>`
                    : nothing}
                </div>
              `,
            )}
          `
        : nothing}
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-preview": RsSettingsPreview;
  }
}
