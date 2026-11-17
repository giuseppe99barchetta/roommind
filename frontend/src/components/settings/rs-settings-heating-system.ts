import { LitElement, html, css, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import {
  normalizeBypassEntities,
  selectPowerSensorMode,
  syncPowerSensorMode,
  type PowerSensorModeState,
} from "../../utils/heating-settings";
import { getSelectValue } from "../../utils/events";
import { localize } from "../../utils/localize";
import "../shared/rs-list-row";
import "../shared/rs-number-field";

// HA 2026.8's ha-entity-picker is single-value only. The entity selector
// routes `multiple` values to ha-entities-picker, whose value is string[].
const HYDRAULIC_BYPASS_SELECTOR = {
  entity: {
    multiple: true,
    filter: [{ domain: "climate" }],
  },
};

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
  @property({ type: Boolean }) public bypassChildLock = true;
  @property({ type: Number }) public minDemandRooms = 1;
  @property({ type: String }) public demandUnit: "valves" | "rooms" = "valves";
  @property({ type: Number }) public minRunMinutes = 5;
  @property({ type: Number }) public minOffMinutes = 3;
  @property({ type: Number }) public faultRetryMinutes = 5;
  @property({ type: Number }) public maxWaitMinutes = 120;
  @property({ type: Boolean }) public budgetEnabled = false;
  @property({ type: String }) public powerSensor = "";
  @property({ type: String }) public powerMode: "available" | "consumption" = "available";
  @property({ type: Number }) public maxPower = 3300;
  @property({ type: Number }) public reserve = 200;
  @property({ type: Number }) public energyPricePerKwh = 0;
  @state() private _powerModeState: PowerSensorModeState = {
    value: "available",
    hasLocalChange: false,
  };

  protected willUpdate(changedProperties: PropertyValues<this>) {
    if (changedProperties.has("powerMode")) {
      this._powerModeState = syncPowerSensorMode(this._powerModeState, this.powerMode);
    }
  }

  render() {
    const l = this.hass.language;
    const fire = (key: string, value: unknown) =>
      this.dispatchEvent(
        new CustomEvent("setting-changed", {
          detail: { key, value },
          bubbles: true,
          composed: true,
        }),
      );
    // Ranges from the backend schema; steps keep the precision the backend stores (floats)
    const number = (
      key: string,
      value: number,
      label: string,
      min: number,
      max: number,
      step: number,
      { hint = "", suffix = "" } = {},
    ) =>
      html`<rs-number-field
        .label=${label}
        .hint=${hint}
        .suffix=${suffix}
        .min=${min}
        .max=${max}
        .step=${step}
        .value=${value}
        @value-changed=${(e: CustomEvent<{ value: number }>) => fire(key, e.detail.value)}
      ></rs-number-field>`;
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
      this._powerModeState = selectPowerSensorMode(value);
      fire("powerMode", this._powerModeState.value);
    };
    return html`<div class="section">
        <b>${localize("settings.boiler.title", l)}</b>
        <ha-entity-picker
          .hass=${this.hass}
          .includeDomains=${["climate", "switch"]}
          .value=${this.boilerEntity}
          .label=${localize("settings.boiler.entity", l)}
          @value-changed=${(e: CustomEvent) => fire("boilerEntity", e.detail.value || "")}
        ></ha-entity-picker>
        ${this.boilerEntity
          ? html`<ha-select
                .value=${this.boilerControlType}
                .label=${localize("settings.boiler.control_type", l)}
                @selected=${(e: CustomEvent) => fire("boilerControlType", e.detail.value)}
                ><ha-list-item value="climate"
                  >${localize("settings.boiler.control_type_climate", l)}</ha-list-item
                ><ha-list-item value="switch"
                  >${localize("settings.boiler.control_type_switch", l)}</ha-list-item
                ></ha-select
              >
              <div class="grid">
                ${number(
                  "startupDelay",
                  this.startupDelay,
                  localize("settings.boiler.startup_delay", l),
                  0,
                  3600,
                  0.1,
                  { suffix: "s" },
                )}
                ${number(
                  "shutdownDelay",
                  this.shutdownDelay,
                  localize("settings.boiler.shutdown_hold", l),
                  0,
                  3600,
                  0.1,
                  { suffix: "s" },
                )}
              </div>
              <ha-selector
                .hass=${this.hass}
                .selector=${HYDRAULIC_BYPASS_SELECTOR}
                .value=${this.bypassEntities}
                .label=${localize("settings.boiler.bypass_entities", l)}
                @value-changed=${onBypassChanged}
              ></ha-selector>
              <small>${localize("settings.boiler.bypass_hint", l)}</small>
              ${number(
                "bypassTemperature",
                this.bypassTemperature,
                localize("settings.boiler.bypass_temperature", l),
                5,
                50,
                0.1,
                { suffix: "°C" },
              )}
              <rs-list-row
                switch
                wrap
                .heading=${localize("settings.boiler.child_lock", this.hass.language)}
                .secondary=${localize("settings.boiler.child_lock_hint", this.hass.language)}
                .checked=${this.bypassChildLock}
                @toggle-changed=${(e: CustomEvent<boolean>) => fire("bypassChildLock", e.detail)}
              ></rs-list-row>
              <ha-select
                .value=${this.demandUnit}
                .label=${localize("settings.boiler.demand_unit", this.hass.language)}
                @selected=${(e: Event) => {
                  const value = getSelectValue(e);
                  if (value === "valves" || value === "rooms") fire("demandUnit", value);
                }}
                ><ha-list-item value="valves"
                  >${localize(
                    "settings.boiler.demand_unit_valves",
                    this.hass.language,
                  )}</ha-list-item
                ><ha-list-item value="rooms"
                  >${localize(
                    "settings.boiler.demand_unit_rooms",
                    this.hass.language,
                  )}</ha-list-item
                ></ha-select
              >
              ${number(
                "minDemandRooms",
                this.minDemandRooms,
                localize("settings.boiler.min_demand_rooms", l),
                1,
                20,
                1,
                { hint: localize("settings.boiler.min_demand_hint", l) },
              )}
              ${number(
                "maxWaitMinutes",
                this.maxWaitMinutes,
                localize("settings.boiler.max_wait_minutes", l),
                0,
                1440,
                0.1,
                { hint: localize("settings.boiler.max_wait_hint", l) },
              )}
              <div class="grid">
                ${number(
                  "minRunMinutes",
                  this.minRunMinutes,
                  localize("settings.boiler.min_run_minutes", l),
                  0,
                  120,
                  0.1,
                )}
                ${number(
                  "minOffMinutes",
                  this.minOffMinutes,
                  localize("settings.boiler.min_off_minutes", l),
                  0,
                  120,
                  0.1,
                )}
              </div>
              ${number(
                "faultRetryMinutes",
                this.faultRetryMinutes,
                localize("settings.boiler.fault_retry_minutes", l),
                1,
                240,
                0.1,
              )}`
          : nothing}
      </div>
      <div class="section">
        <b>${localize("settings.energy_price", this.hass.language)}</b>
        ${number(
          "energyPricePerKwh",
          this.energyPricePerKwh,
          localize("settings.energy_price_hint", l),
          0,
          100,
          0.0001,
        )}
      </div>
      <div class="section">
        <rs-list-row
          switch
          wrap
          .heading=${localize("settings.power_budget.title", l)}
          .secondary=${localize("settings.power_budget.hint", l)}
          .checked=${this.budgetEnabled}
          @toggle-changed=${(e: CustomEvent<boolean>) => fire("budgetEnabled", e.detail)}
        ></rs-list-row>
        ${this.budgetEnabled
          ? html`<ha-entity-picker
                .hass=${this.hass}
                .includeDomains=${["sensor"]}
                .value=${this.powerSensor}
                .label=${localize("settings.power_budget.sensor", l)}
                @value-changed=${(e: CustomEvent) => fire("powerSensor", e.detail.value || "")}
              ></ha-entity-picker
              ><ha-select
                .value=${this._powerModeState.value}
                .options=${[
                  {
                    value: "available",
                    label: localize("settings.power_budget.mode_available", l),
                  },
                  {
                    value: "consumption",
                    label: localize("settings.power_budget.mode_consumption", l),
                  },
                ]}
                .label=${localize("settings.power_budget.mode", l)}
                @selected=${onPowerModeSelected}
              ></ha-select>
              <div class="grid">
                ${number(
                  "maxPower",
                  this.maxPower,
                  localize("settings.power_budget.max_power", l),
                  0,
                  100000,
                  1,
                )}
                ${number(
                  "reserve",
                  this.reserve,
                  localize("settings.power_budget.reserve", l),
                  0,
                  100000,
                  1,
                )}
              </div>`
          : nothing}
      </div>`;
  }
  static styles = css`
    :host {
      display: block;
      /* the narrow rule below follows the panel's width, as in the other settings panels */
      container-type: inline-size;
    }
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
    /* one column on a narrow card, like the shared threshold-grid */
    @container (max-width: 520px) {
      .grid {
        grid-template-columns: 1fr;
      }
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
