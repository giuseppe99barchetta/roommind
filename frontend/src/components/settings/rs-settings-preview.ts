/** Read-only safety preview. Never sends commands to physical devices. */
import { html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize, type TranslationKey } from "../../utils/localize";
import { DECISION_KEYS } from "../rs-room-insights";
import { RsSettingsBase } from "./rs-settings-base";
import "../shared/rs-field";
import "../shared/rs-list-row";
import "../shared/rs-segmented";

/** Boiler states the backend reports (BoilerState). */
const BOILER_STATES = ["off", "preopening", "on", "poststop", "fault"];

interface PreviewRoom {
  watts: number;
  source: "learned" | "fallback" | "unknown";
  samples: number;
  already_running: boolean;
  would_allow: boolean;
  reason:
    | "eligible"
    | "control_disabled"
    | "room_safety"
    | "compressor_protection"
    | "power_budget";
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
export class RsSettingsPreview extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @state() private _mode: "heating" | "cooling" | "dry" = "cooling";
  @state() private _result?: ControlPreview;
  @state() private _loading = false;
  @state() private _error = false;

  static styles = [RsSettingsBase.settingsBaseStyles];

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
    const modes = ["heating", "cooling", "dry"] as const;
    return html`
      <div class="settings-section first stack">
        <rs-field .label=${localize("preview.mode", lang)} .hint=${localize("preview.scope", lang)}>
          <rs-segmented
            wrap
            .label=${localize("preview.mode", lang)}
            .options=${modes.map((mode) => ({
              value: mode,
              label: localize(`heat_source.budget_${mode}`, lang),
            }))}
            .value=${this._mode}
            @value-changed=${(e: CustomEvent<{ value: "heating" | "cooling" | "dry" }>) => {
              e.stopPropagation();
              this._mode = e.detail.value;
              this._result = undefined;
            }}
          ></rs-segmented>
        </rs-field>
        <div>
          <ha-button .disabled=${this._loading} @click=${() => this._refresh()}>
            <ha-icon icon="mdi:play-circle-outline" slot="icon"></ha-icon>
            ${localize("preview.run", lang)}
          </ha-button>
        </div>
        ${this._error
          ? html`<p class="note" role="alert">${localize("preview.error", lang)}</p>`
          : nothing}
      </div>
      ${r
        ? html`<div class="settings-section">
              <rs-list-row
                icon="mdi:flash"
                .heading=${localize("preview.headroom", lang)}
                .value=${r.house_available_watts === null
                  ? "—"
                  : `${Math.round(r.house_available_watts)} W`}
              ></rs-list-row>
              <rs-list-row
                icon="mdi:meter-electric-outline"
                .heading=${localize("preview.meter", lang)}
                .value=${`${
                  r.power_sensor_healthy
                    ? localize("preview.healthy", lang)
                    : localize("preview.unavailable", lang)
                }${r.power_sensor_age_seconds !== null ? ` (${Math.round(r.power_sensor_age_seconds)} s)` : ""}`}
              ></rs-list-row>
              <rs-list-row
                icon="mdi:water-boiler"
                .heading=${localize("preview.boiler", lang)}
                .value=${BOILER_STATES.includes(r.boiler_state)
                  ? localize(`preview.boiler_${r.boiler_state}` as TranslationKey, lang)
                  : r.boiler_state}
              ></rs-list-row>
              <rs-list-row
                wrap
                icon="mdi:valve"
                .heading=${localize("preview.bypass", lang)}
                .secondary=${r.bypass_acknowledged
                  ? localize("preview.acknowledged", lang)
                  : localize("preview.not_acknowledged", lang)}
              ></rs-list-row>
            </div>
            <div class="settings-section">
              ${Object.entries(r.rooms).map(
                ([areaId, room]) =>
                  html`<rs-list-row
                    wrap
                    icon="mdi:door"
                    .heading=${this.hass.areas?.[areaId]?.name ?? areaId.replaceAll("_", " ")}
                    .secondary=${[
                      // in the wrapping line, not the row's value: a narrow screen would cut it
                      `${room.watts} W · ${localize(`heat_source.budget_${room.source}`, lang)}`,
                      localize(`preview.reason_${room.reason}`, lang),
                      room.current_decision_reasons.length
                        ? `${localize("preview.current_reasons", lang)}: ${room.current_decision_reasons
                            .map((reason) =>
                              DECISION_KEYS[reason]
                                ? localize(DECISION_KEYS[reason], lang)
                                : reason,
                            )
                            .join(" ")}`
                        : "",
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  ></rs-list-row>`,
              )}
            </div>`
        : nothing}
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-preview": RsSettingsPreview;
  }
}
