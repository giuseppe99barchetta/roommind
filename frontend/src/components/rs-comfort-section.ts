/** Per-room comfort profiles and gradual night mode controls. */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { ClimateMode, ComfortProfileTargets, HomeAssistant, RoomConfig } from "../types";
import { localize } from "../utils/localize";
import { formatTemp, tempUnit } from "../utils/temperature";
import { inputStyles } from "../styles/input-styles";
import "./shared/rs-field";
import "./shared/rs-list-row";
import "./shared/rs-number-field";
import "./shared/rs-segmented";

const PROFILES = ["", "work", "sleep", "guests", "away"] as const;
const NAMED = ["work", "sleep", "guests", "away"] as const;

@customElement("rs-comfort-section")
export class RsComfortSection extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: String }) public activeProfile = "";
  @property({ attribute: false }) public profileTargets: RoomConfig["profile_targets"] = {};
  @property({ type: String }) public climateMode: ClimateMode = "auto";
  @property({ type: Boolean }) public nightModeEnabled = false;
  @property({ type: String }) public nightStart = "22:00";
  @property({ type: String }) public nightEnd = "07:00";
  @property({ type: Number }) public nightHeatDelta = -0.5;
  @property({ type: Number }) public nightCoolDelta = 0.5;
  @property({ type: Number }) public nightRampMinutes = 60;

  static styles = [
    inputStyles,
    css`
      :host {
        display: block;
      }
      .night {
        margin-top: var(--rs-space-4, 16px);
        /* the switch row reaches the card edge (past .fork-section's padding) like the other
           room rows */
        margin-inline: calc(-1 * var(--rs-space-4, 16px));
      }
      .grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: var(--rs-space-4, 16px);
        margin-top: var(--rs-space-3, 12px);
      }
      .wide {
        grid-column: 1 / -1;
      }
      @container (max-width: 520px) {
        .grid {
          grid-template-columns: 1fr;
        }
      }
    `,
  ];

  /** "19.5 – 23 °C" for a profile, or "" when it has no target for this climate mode. */
  private _targetText(targets: ComfortProfileTargets | undefined): string {
    if (!targets) return "";
    const heat = this.climateMode === "cool_only" ? undefined : targets.heat_target;
    const cool = this.climateMode === "heat_only" ? undefined : targets.cool_target;
    const parts = [heat, cool].filter((t): t is number => t != null);
    if (!parts.length) return "";
    return `${parts.map((t) => formatTemp(t, this.hass)).join(" – ")}${tempUnit(this.hass)}`;
  }

  private _targetsHint(): string {
    const l = this.hass.language;
    return NAMED.map((profile) => {
      const text = this._targetText(this.profileTargets?.[profile]);
      return text ? `${localize(`comfort.profile.${profile}`, l)} ${text}` : "";
    })
      .filter(Boolean)
      .join(" · ");
  }

  render() {
    const l = this.hass.language;
    const hints = [
      this.activeProfile ? localize("comfort.profile_clear_hint", l) : "",
      this._targetsHint(),
    ].filter(Boolean);
    return html`
      <rs-field .label=${localize("comfort.profiles", l)} .hint=${hints.join(" ")}>
        <rs-segmented
          wrap
          reselect
          .label=${localize("comfort.profiles", l)}
          .options=${PROFILES.map((profile) => ({
            value: profile,
            label: localize(`comfort.profile.${profile || "default"}`, l),
          }))}
          .value=${this.activeProfile}
          @value-changed=${(e: CustomEvent<{ value: string }>) => {
            e.stopPropagation();
            const profile = e.detail.value;
            // Picking the active profile again clears it (back to the schedule).
            this._emit("active_profile", this.activeProfile === profile ? "" : profile);
          }}
        ></rs-segmented>
      </rs-field>
      <div class="night">
        <rs-list-row
          switch
          wrap
          icon="mdi:weather-night"
          .heading=${localize("comfort.night_mode", l)}
          .secondary=${localize("comfort.night_mode_hint", l)}
          .checked=${this.nightModeEnabled}
          @toggle-changed=${(event: CustomEvent<boolean>) =>
            this._emit("night_mode_enabled", event.detail)}
        ></rs-list-row>
      </div>
      ${this.nightModeEnabled
        ? html`<div class="grid">
            ${this._timeField("comfort.night_start", this.nightStart, "night_start")}
            ${this._timeField("comfort.night_end", this.nightEnd, "night_end")}
            ${this._numberField(
              "comfort.night_heat_delta",
              this.nightHeatDelta,
              "night_heat_delta",
              -5,
              0,
              0.1,
            )}
            ${this._numberField(
              "comfort.night_cool_delta",
              this.nightCoolDelta,
              "night_cool_delta",
              0,
              5,
              0.1,
            )}
            ${this._numberField(
              "comfort.night_ramp",
              this.nightRampMinutes,
              "night_ramp_minutes",
              0,
              240,
              1,
              true,
            )}
          </div>`
        : nothing}
    `;
  }

  private _timeField(label: Parameters<typeof localize>[0], value: string, key: string) {
    return html`<ha-textfield
      type="time"
      .label=${localize(label, this.hass.language)}
      .value=${value}
      @change=${(e: Event) => this._emit(key, (e.target as HTMLInputElement).value)}
    ></ha-textfield>`;
  }

  private _numberField(
    label: Parameters<typeof localize>[0],
    value: number,
    key: string,
    min: number,
    max: number,
    step: number,
    wide = false,
  ) {
    return html`<rs-number-field
      class=${wide ? "wide" : ""}
      .label=${localize(label, this.hass.language)}
      .min=${min}
      .max=${max}
      .step=${step}
      .value=${value}
      @value-changed=${(e: CustomEvent<{ value: number }>) => this._emit(key, e.detail.value)}
    ></rs-number-field>`;
  }

  private _emit(key: string, value: string | number | boolean) {
    this.dispatchEvent(
      new CustomEvent("setting-changed", { detail: { key, value }, bubbles: true, composed: true }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-comfort-section": RsComfortSection;
  }
}
