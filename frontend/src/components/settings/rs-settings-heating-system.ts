import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { normalizeBypassEntities, normalizePowerSensorMode } from "../../utils/heating-settings";
import { getSelectValue } from "../../utils/events";

/** Native central-boiler, hydraulic safety and electrical budget settings. */
@customElement("rs-settings-heating-system")
export class RsSettingsHeatingSystem extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: String }) public boilerEntity = "";
  @property({ type: String }) public boilerControlType: "climate" | "switch" = "climate";
  @property({ type: Array }) public bypassEntities: string[] = [];
  @property({ type: Number }) public startupDelay = 30;
  @property({ type: Number }) public shutdownDelay = 60;
  @property({ type: Number }) public bypassTemperature = 28;
  @property({ type: Boolean }) public budgetEnabled = false;
  @property({ type: String }) public powerSensor = "";
  @property({ type: String }) public powerMode: "available" | "consumption" = "available";
  @property({ type: Number }) public maxPower = 3300;
  @property({ type: Number }) public reserve = 200;

  render() {
    const fire = (key: string, value: unknown) =>
      this.dispatchEvent(
        new CustomEvent("setting-changed", {
          detail: { key, value },
          bubbles: true,
          composed: true,
        }),
      );
    const number = (key: string, value: number) =>
      html`<ha-textfield
        type="number"
        .value=${String(value)}
        @change=${(e: Event) => fire(key, Number((e.target as HTMLInputElement).value))}
      ></ha-textfield>`;
    const pickerValue = (e: CustomEvent): unknown => {
      const detail = e.detail as unknown;
      const target = e.target as { value?: unknown; values?: unknown; selected?: unknown } | null;
      const currentTarget = e.currentTarget as {
        value?: unknown;
        values?: unknown;
        selected?: unknown;
      } | null;
      if (typeof detail === "string" || Array.isArray(detail)) return detail;
      if (detail && typeof detail === "object") {
        const values = detail as { value?: unknown; values?: unknown; selected?: unknown };
        return values.value ?? values.values ?? values.selected;
      }
      return (
        target?.value ??
        target?.values ??
        target?.selected ??
        currentTarget?.value ??
        currentTarget?.values
      );
    };
    const onBypassChanged = (e: CustomEvent) => {
      const value = pickerValue(e);
      // Diagnostic logging is intentionally limited to explicit user changes.
      // eslint-disable-next-line no-console
      console.debug("RoomMind hydraulic bypass picker event", {
        type: e.type,
        detail: e.detail,
        targetValue: (e.target as { value?: unknown } | null)?.value,
        currentTargetValue: (e.currentTarget as { value?: unknown } | null)?.value,
        value,
      });
      fire("bypassEntities", normalizeBypassEntities(value));
    };
    const onPowerModeSelected = (e: Event) => {
      const value = getSelectValue(e);
      // HA 2026.8 puts the selected option in detail.value; target.value may
      // still be the previous selection while the event is being dispatched.
      // eslint-disable-next-line no-console
      console.debug("RoomMind power sensor mode selected", {
        type: e.type,
        detail: (e as CustomEvent).detail,
        targetValue: (e.target as { value?: unknown } | null)?.value,
        currentTargetValue: (e.currentTarget as { value?: unknown } | null)?.value,
        value,
      });
      fire("powerMode", normalizePowerSensorMode(value));
    };
    return html`<div class="section">
        <b>Central boiler</b>
        <ha-entity-picker
          .hass=${this.hass}
          .includeDomains=${["climate", "switch"]}
          .value=${this.boilerEntity}
          label="Boiler control entity"
          @value-changed=${(e: CustomEvent) => fire("boilerEntity", e.detail.value || "")}
        ></ha-entity-picker>
        ${this.boilerEntity
          ? html`<ha-select
                .value=${this.boilerControlType}
                label="Control type"
                @selected=${(e: CustomEvent) => fire("boilerControlType", e.detail.value)}
                ><ha-list-item value="climate">Climate</ha-list-item
                ><ha-list-item value="switch">Switch</ha-list-item></ha-select
              >
              <div class="grid">
                <label>Startup delay ${number("startupDelay", this.startupDelay)}</label
                ><label>Shutdown hold ${number("shutdownDelay", this.shutdownDelay)}</label>
              </div>
              <ha-entity-picker
                .hass=${this.hass}
                .includeDomains=${["climate"]}
                .multiple=${true}
                .value=${this.bypassEntities}
                label="Hydraulic bypass TRVs"
                @value-changed=${onBypassChanged}
              ></ha-entity-picker>
              <label
                >Forced bypass temperature
                ${number("bypassTemperature", this.bypassTemperature)}</label
              >`
          : nothing}
      </div>
      <div class="section">
        <div class="toggle">
          <span
            ><b>Electrical power budget</b
            ><small
              >Allocate heat-pump starts centrally; a missing sensor falls back to boiler.</small
            ></span
          ><ha-switch
            .checked=${this.budgetEnabled}
            @change=${(e: Event) => fire("budgetEnabled", (e.target as HTMLInputElement).checked)}
          ></ha-switch>
        </div>
        ${this.budgetEnabled
          ? html`<ha-entity-picker
                .hass=${this.hass}
                .includeDomains=${["sensor"]}
                .value=${this.powerSensor}
                label="Available power / consumption sensor"
                @value-changed=${(e: CustomEvent) => fire("powerSensor", e.detail.value || "")}
              ></ha-entity-picker
              ><ha-select
                .value=${this.powerMode}
                label="Sensor reports"
                @selected=${onPowerModeSelected}
                ><ha-list-item value="available">Available power</ha-list-item
                ><ha-list-item value="consumption">House consumption</ha-list-item></ha-select
              >
              <div class="grid">
                <label>Maximum house load (W) ${number("maxPower", this.maxPower)}</label
                ><label>Safety reserve (W) ${number("reserve", this.reserve)}</label>
              </div>`
          : nothing}
      </div>`;
  }
  static styles = css`
    .section {
      display: grid;
      gap: 12px;
    }
    .section + .section {
      border-top: 1px solid var(--divider-color);
      margin-top: 18px;
      padding-top: 18px;
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .grid label,
    label {
      display: grid;
      gap: 4px;
      font-size: 13px;
    }
    .toggle {
      display: flex;
      justify-content: space-between;
      gap: 16px;
    }
    .toggle small {
      display: block;
      color: var(--secondary-text-color);
      margin-top: 4px;
    }
  `;
}
declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-heating-system": RsSettingsHeatingSystem;
  }
}
