/**
 * rs-settings-vacation – Vacation mode settings.
 */
import { css, html, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { toDisplay, toCelsius, tempUnit, tempStep, tempRange } from "../../utils/temperature";

@customElement("rs-settings-vacation")
export class RsSettingsVacation extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public vacationActive = false;
  @property({ type: Number }) public vacationTemp = 15;
  @property({ type: String }) public vacationUntil = "";
  /** Time picked before a date; used once the date is set. */
  @state() private _time = "00:00";

  render() {
    const l = this.hass.language;

    return html`
      <div class="toggle-row">
        <div class="toggle-text">
          <span class="toggle-label">${localize("vacation.title", l)}</span>
          <span class="toggle-hint">${localize("vacation.hint", l)}</span>
        </div>
        <ha-switch
          .checked=${this.vacationActive}
          @change=${(e: Event) => {
            const active = (e.target as HTMLInputElement).checked;
            this._fire("vacationActive", active);
            if (!active) this._fire("vacationUntil", "");
          }}
        ></ha-switch>
      </div>

      ${this.vacationActive
        ? html`
            <div class="threshold-grid" style="margin-top: 12px; align-items: end">
              <div class="threshold-field">${this._renderEndDate()}</div>
              <div class="threshold-field">
                <ha-textfield
                  .value=${String(toDisplay(this.vacationTemp, this.hass))}
                  .label=${localize("vacation.setback_temp", l)}
                  .suffix=${tempUnit(this.hass)}
                  type="number"
                  step=${tempStep(this.hass)}
                  min=${tempRange(5, 25, this.hass).min}
                  max=${tempRange(5, 25, this.hass).max}
                  @change=${(e: Event) => {
                    const v = parseFloat((e.target as HTMLInputElement).value);
                    if (!isNaN(v)) this._fire("vacationTemp", toCelsius(v, this.hass));
                  }}
                ></ha-textfield>
              </div>
            </div>
          `
        : nothing}
    `;
  }

  /**
   * Home Assistant's own date and time fields show the date in HA's language and format; a plain
   * datetime-local field follows the browser instead. The field stays as fallback for releases
   * that do not define ha-selector in the panel.
   */
  private _renderEndDate() {
    const l = this.hass.language;
    if (customElements.get("ha-selector")) {
      const [date, time] = this.vacationUntil ? this.vacationUntil.split("T") : ["", ""];
      return html`<div class="end-date">
        <ha-selector
          class="date"
          .hass=${this.hass}
          .selector=${{ date: {} }}
          .label=${localize("vacation.end_day", l)}
          .required=${false}
          .value=${date}
          @value-changed=${(e: CustomEvent<{ value?: string }>) => {
            e.stopPropagation();
            this._setEnd(e.detail.value ?? "", time || this._time);
          }}
        ></ha-selector>
        <ha-selector
          class="time"
          .hass=${this.hass}
          .selector=${{ time: { no_second: true } }}
          .label=${localize("vacation.end_time", l)}
          .required=${false}
          .value=${time || this._time}
          @value-changed=${(e: CustomEvent<{ value?: string }>) => {
            e.stopPropagation();
            this._time = (e.detail.value ?? "").slice(0, 5) || "00:00";
            if (date) this._setEnd(date, this._time);
          }}
        ></ha-selector>
      </div>`;
    }
    // Label outside the field: inside, it overlapped the empty datetime placeholder (#367)
    return html`<label class="field-label" for="vacation-until"
        >${localize("vacation.end_date", l)}</label
      >
      <ha-textfield
        id="vacation-until"
        .value=${this.vacationUntil}
        aria-label=${localize("vacation.end_date", l)}
        type="datetime-local"
        @change=${(e: Event) => this._fire("vacationUntil", (e.target as HTMLInputElement).value)}
      ></ha-textfield>`;
  }

  private _setEnd(date: string, time: string) {
    const until = date ? `${date}T${time.slice(0, 5) || "00:00"}` : "";
    if (until !== this.vacationUntil) this._fire("vacationUntil", until);
  }

  static styles = [
    RsSettingsBase.settingsBaseStyles,
    css`
      .field-label {
        display: block;
        font-size: 12px;
        color: var(--secondary-text-color);
        margin-bottom: 4px;
      }
      /* the time field carries its label above, the date field inside: align their bottoms */
      .end-date {
        display: flex;
        flex-wrap: wrap;
        align-items: flex-end;
        gap: 8px;
      }
      .end-date .date {
        flex: 1 1 150px;
        min-width: 0;
        /* ha-input keeps 8 px for a hint it does not show */
        margin-bottom: -8px;
      }
      .end-date .time {
        flex: none;
        width: auto;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-vacation": RsSettingsVacation;
  }
}
