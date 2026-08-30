/** Per-room comfort profiles and gradual night mode controls. */
import { LitElement, html, css } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../types";
import { localize } from "../utils/localize";
import "./shared/rs-toggle-row";

const PROFILES = ["", "work", "sleep", "guests", "away"] as const;

@customElement("rs-comfort-section")
export class RsComfortSection extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: String }) public activeProfile = "";
  @property({ type: Boolean }) public nightModeEnabled = false;
  @property({ type: String }) public nightStart = "22:00";
  @property({ type: String }) public nightEnd = "07:00";
  @property({ type: Number }) public nightHeatDelta = -0.5;
  @property({ type: Number }) public nightCoolDelta = 0.5;
  @property({ type: Number }) public nightRampMinutes = 60;

  static styles = css`
    :host { display: block; }
    .profile-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    button {
      border: 1px solid var(--divider-color, #444);
      border-radius: 8px;
      padding: 9px 10px;
      color: var(--primary-text-color);
      background: var(--secondary-background-color, rgba(127, 127, 127, 0.08));
      cursor: pointer;
      font: inherit;
      font-size: 13px;
    }
    button.active { border-color: var(--primary-color); color: var(--primary-color); background: color-mix(in srgb, var(--primary-color) 12%, transparent); }
    .profile-label { margin: 0 0 10px; color: var(--secondary-text-color); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
    .night { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--divider-color); }
    .night-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }
    label { display: grid; gap: 5px; color: var(--secondary-text-color); font-size: 12px; }
    input { min-width: 0; box-sizing: border-box; width: 100%; padding: 8px; border: 1px solid var(--divider-color); border-radius: 6px; color: var(--primary-text-color); background: var(--card-background-color, transparent); font: inherit; }
    .wide { grid-column: 1 / -1; }
  `;

  render() {
    const l = this.hass.language;
    return html`
      <p class="profile-label">${localize("comfort.profiles", l)}</p>
      <div class="profile-grid">
        ${PROFILES.map(
          (profile) => html`<button
            class=${this.activeProfile === profile ? "active" : ""}
            @click=${() => this._emit("active_profile", profile)}
          >${localize(`comfort.profile.${profile || "default"}`, l)}</button>`,
        )}
      </div>
      <div class="night">
        <rs-toggle-row
          .label=${localize("comfort.night_mode", l)}
          .hint=${localize("comfort.night_mode_hint", l)}
          .checked=${this.nightModeEnabled}
          @toggle-changed=${(event: CustomEvent<boolean>) =>
            this._emit("night_mode_enabled", event.detail)}
        ></rs-toggle-row>
        ${this.nightModeEnabled
          ? html`<div class="night-grid">
              ${this._timeField("comfort.night_start", this.nightStart, "night_start")}
              ${this._timeField("comfort.night_end", this.nightEnd, "night_end")}
              ${this._numberField("comfort.night_heat_delta", this.nightHeatDelta, "night_heat_delta", -5, 0, 0.1)}
              ${this._numberField("comfort.night_cool_delta", this.nightCoolDelta, "night_cool_delta", 0, 5, 0.1)}
              ${this._numberField("comfort.night_ramp", this.nightRampMinutes, "night_ramp_minutes", 0, 240, 5, true)}
            </div>`
          : ""}
      </div>
    `;
  }

  private _timeField(label: Parameters<typeof localize>[0], value: string, key: string) {
    return html`<label>${localize(label, this.hass.language)}<input type="time" .value=${value} @change=${(e: Event) => this._emit(key, (e.target as HTMLInputElement).value)} /></label>`;
  }

  private _numberField(label: Parameters<typeof localize>[0], value: number, key: string, min: number, max: number, step: number, wide = false) {
    return html`<label class=${wide ? "wide" : ""}>${localize(label, this.hass.language)}<input type="number" min=${min} max=${max} step=${step} .value=${String(value)} @change=${(e: Event) => { const value = Number((e.target as HTMLInputElement).value); if (!Number.isNaN(value)) this._emit(key, value); }} /></label>`;
  }

  private _emit(key: string, value: string | number | boolean) {
    this.dispatchEvent(new CustomEvent("setting-changed", { detail: { key, value }, bubbles: true, composed: true }));
  }
}

declare global { interface HTMLElementTagNameMap { "rs-comfort-section": RsComfortSection; } }
