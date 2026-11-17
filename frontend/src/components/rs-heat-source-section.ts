import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { ClimateMode, HomeAssistant, RoomLiveData } from "../types";
import { localize } from "../utils/localize";
import { tokens } from "../styles/tokens";
import { formStyles } from "../styles/form-styles";
import { formatNumber } from "../utils/format";
import { formatTempLocale, tempUnit, toDisplayDelta } from "../utils/temperature";
import "./shared/rs-number-field";
import "./shared/rs-info-icon";
import "./shared/rs-list-row";

/** Mirrors HEAT_SOURCE_HYSTERESIS / HEAT_SOURCE_LARGE_GAP_MULTIPLIER (const.py). */
const HYSTERESIS_K = 0.3;
const BOTH_MULTIPLIER = 2;

/**
 * Heat source orchestration (radiators + AC) in the 2.0 layout, with the fork's native mode
 * (boiler / heat pump thresholds, hybrid delta), the AC power estimate and the learned power
 * budget. No price awareness: the fork has no price source.
 */
@customElement("rs-heat-source-section")
export class RsHeatSourceSection extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public enabled = false;
  @property({ type: Boolean }) public native = false;
  @property({ type: Boolean }) public hasAc = false;
  @property({ type: Boolean }) public hasTrv = false;
  @property({ type: Number }) public heatPumpPower = 0;
  @property({ attribute: false })
  public powerBudgetEstimates?: RoomLiveData["power_budget_estimates"];
  @property({ type: Number }) public primaryDelta = 1.5;
  @property({ type: Number }) public outdoorThreshold = 5.0;
  @property({ type: Number }) public acMinOutdoor = -15.0;
  @property({ type: Number }) public boilerOutdoorThreshold = 2;
  @property({ type: Number }) public heatPumpOutdoorThreshold = 8;
  @property({ type: Number }) public hybridDelta = 1.5;
  @property({ type: Boolean }) public editing = false;
  /**
   * Current outdoor temperature; null = none, then the gap decides between the sources.
   * Undefined (not passed) reads as known.
   */
  @property({ attribute: false }) public outdoorTemp: number | null | undefined = undefined;
  @property({ type: String }) public climateMode: ClimateMode = "auto";

  static styles = [
    tokens,
    formStyles,
    css`
      :host {
        display: block;
        --rs-form-inline: var(--rs-space-4);
      }
      .power-learning {
        display: flex;
        flex-wrap: wrap;
        gap: 6px 14px;
        color: var(--secondary-text-color);
        font-size: var(--rs-font-sm, 12px);
        line-height: 1.6;
      }
    `,
  ];

  private _abs(c: number): string {
    return `${formatTempLocale(c, this.hass, 0, 1)} ${tempUnit(this.hass)}`;
  }

  private _delta(k: number): string {
    return `${formatNumber(toDisplayDelta(k, this.hass), this.hass, 0, 1)} ${tempUnit(this.hass)}`;
  }

  /** What decides the source now, in one line. */
  private _ruleText(): string {
    const l = this.hass.language;
    if (!this.hasTrv) return "";
    if (!this.enabled) {
      return localize(
        this.climateMode === "heat_only"
          ? "heat_source.summary_disabled_heat_only"
          : "heat_source.summary_disabled",
        l,
      );
    }
    if (this.native) {
      return [
        `${localize("heat_source.boiler_outdoor_threshold", l)}: ${this._abs(this.boilerOutdoorThreshold)}`,
        `${localize("heat_source.heat_pump_outdoor_threshold", l)}: ${this._abs(this.heatPumpOutdoorThreshold)}`,
        `${localize("heat_source.hybrid_delta", l)}: ${this._delta(this.hybridDelta)}`,
      ].join(" · ");
    }
    return this.outdoorTemp !== null
      ? localize("heat_source.rule_outdoor", l, { temp: this._abs(this.outdoorThreshold) })
      : localize("heat_source.rule_gap", l, { delta: this._delta(this.primaryDelta) });
  }

  render() {
    const l = this.hass.language;

    if (!this.editing) {
      const secondary = [
        this._ruleText(),
        this.hasAc ? `${localize("heat_source.power_estimate", l)}: ${this.heatPumpPower} W` : "",
      ].filter(Boolean);
      return html`<rs-list-row
          clickable
          chevron
          wrap
          icon="mdi:swap-horizontal"
          .heading=${localize("heat_source.toggle", l)}
          .secondary=${secondary.join(" · ")}
          .value=${this.hasTrv ? localize(this.enabled ? "detail.on" : "detail.off", l) : ""}
          @row-click=${this._fireEdit}
        ></rs-list-row>
        ${this._renderPowerLearning(l)}`;
    }

    return html`
      ${this.hasTrv
        ? html`<div class="group">
            <rs-list-row
              switch
              wrap
              .heading=${localize("heat_source.toggle", l)}
              .secondary=${this._ruleText()}
              .checked=${this.enabled}
              @toggle-changed=${(e: CustomEvent<boolean>) =>
                this._emit("heat_source_orchestration", e.detail)}
            >
              <rs-info-icon
                slot="end"
                .text=${localize("heat_source.toggle_hint", l)}
              ></rs-info-icon>
            </rs-list-row>
          </div>`
        : nothing}
      ${this.hasAc
        ? html`<div class="group">
            <rs-number-field
              .label=${localize("heat_source.power_estimate", l)}
              .info=${localize("heat_source.power_estimate_hint", l)}
              suffix="W"
              .value=${this.heatPumpPower}
              .min=${0}
              .max=${20000}
              .step=${50}
              @value-changed=${(e: CustomEvent<{ value: number }>) =>
                this._emit("heat_pump_power_watts", e.detail.value)}
            ></rs-number-field>
            ${this._renderPowerLearning(l)}
          </div>`
        : nothing}
      ${this.enabled && this.hasTrv
        ? html`<div class="group">
            <rs-list-row
              switch
              wrap
              .heading=${localize("heat_source.native_toggle", l)}
              .checked=${this.native}
              @toggle-changed=${(e: CustomEvent<boolean>) =>
                this._emit("native_heat_source", e.detail)}
            >
              <rs-info-icon
                slot="end"
                .text=${localize("heat_source.native_toggle_hint", l)}
              ></rs-info-icon>
            </rs-list-row>
            <h4 class="group-title">${localize("heat_source.group_rules", l)}</h4>
            ${this.native ? this._renderNativeRules(l) : this._renderRules(l)}
          </div>`
        : nothing}
    `;
  }

  private _renderRules(l: string) {
    const both = this.primaryDelta * BOTH_MULTIPLIER + HYSTERESIS_K;
    return html`<rs-number-field
        .hass=${this.hass}
        kind="temperature"
        .label=${localize("heat_source.outdoor_threshold", l)}
        .info=${localize("heat_source.outdoor_threshold_hint", l)}
        .value=${this.outdoorThreshold}
        .min=${-20}
        .max=${25}
        .step=${1}
        @value-changed=${(e: CustomEvent<{ value: number }>) =>
          this._emit("heat_source_outdoor_threshold", e.detail.value)}
      ></rs-number-field>
      <rs-number-field
        .hass=${this.hass}
        kind="temperature-delta"
        .label=${localize("heat_source.primary_delta", l)}
        .info=${localize("heat_source.primary_delta_hint", l)}
        .hint=${localize("heat_source.both_from", l, { delta: this._delta(both) })}
        .value=${this.primaryDelta}
        .min=${0.5}
        .max=${5.0}
        .step=${0.1}
        @value-changed=${(e: CustomEvent<{ value: number }>) =>
          this._emit("heat_source_primary_delta", e.detail.value)}
      ></rs-number-field>
      <rs-number-field
        .hass=${this.hass}
        kind="temperature"
        .label=${localize("heat_source.ac_min_outdoor", l)}
        .info=${localize("heat_source.ac_min_outdoor_hint", l)}
        .value=${this.acMinOutdoor}
        .min=${-30}
        .max=${5}
        .step=${1}
        @value-changed=${(e: CustomEvent<{ value: number }>) =>
          this._emit("heat_source_ac_min_outdoor", e.detail.value)}
      ></rs-number-field>`;
  }

  private _renderNativeRules(l: string) {
    return html`<rs-number-field
        .hass=${this.hass}
        kind="temperature"
        .label=${localize("heat_source.boiler_outdoor_threshold", l)}
        .info=${localize("heat_source.boiler_outdoor_threshold_hint", l)}
        .value=${this.boilerOutdoorThreshold}
        .min=${-30}
        .max=${20}
        .step=${0.5}
        @value-changed=${(e: CustomEvent<{ value: number }>) =>
          this._emit("heat_source_boiler_outdoor_threshold", e.detail.value)}
      ></rs-number-field>
      <rs-number-field
        .hass=${this.hass}
        kind="temperature"
        .label=${localize("heat_source.heat_pump_outdoor_threshold", l)}
        .info=${localize("heat_source.heat_pump_outdoor_threshold_hint", l)}
        .value=${this.heatPumpOutdoorThreshold}
        .min=${-20}
        .max=${35}
        .step=${0.5}
        @value-changed=${(e: CustomEvent<{ value: number }>) =>
          this._emit("heat_source_heat_pump_outdoor_threshold", e.detail.value)}
      ></rs-number-field>
      <rs-number-field
        .hass=${this.hass}
        kind="temperature-delta"
        .label=${localize("heat_source.hybrid_delta", l)}
        .info=${localize("heat_source.hybrid_delta_hint", l)}
        .value=${this.hybridDelta}
        .min=${0}
        .max=${10}
        .step=${0.1}
        @value-changed=${(e: CustomEvent<{ value: number }>) =>
          this._emit("heat_source_hybrid_delta", e.detail.value)}
      ></rs-number-field>`;
  }

  private _renderPowerLearning(lang: string) {
    if (!this.hasAc || !this.powerBudgetEstimates) return nothing;
    const modes = ["heating", "cooling", "dry"] as const;
    return html`<div class="power-learning">
      ${modes.map((mode) => {
        const estimate = this.powerBudgetEstimates?.[mode];
        if (!estimate) return nothing;
        const title = localize(`heat_source.budget_${mode}`, lang);
        const source = localize(`heat_source.budget_${estimate.source}`, lang);
        return html`<span
          >${title}: ${estimate.watts > 0 ? `${estimate.watts} W` : "—"} (${source})</span
        >`;
      })}
    </div>`;
  }

  private _emit(key: string, value: unknown) {
    this.dispatchEvent(
      new CustomEvent("setting-changed", {
        detail: { key, value },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _fireEdit(e: Event) {
    e.stopPropagation();
    this.dispatchEvent(new CustomEvent("edit-click", { bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-heat-source-section": RsHeatSourceSection;
  }
}
