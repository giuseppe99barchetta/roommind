/** Room readiness checklist and plain-language explanation of current control. */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, RoomLiveData, RoomReadiness } from "../types";
import { localize, type TranslationKey } from "../utils/localize";
import "./shared/rs-list-card";
import "./shared/rs-list-row";

export const DECISION_KEYS: Record<string, TranslationKey> = {
  window_open: "insights.decision.window_open",
  power_budget: "insights.decision.power_budget",
  compressor_min_off: "insights.decision.compressor_min_off",
  compressor_min_run: "insights.decision.compressor_min_run",
  override_boost: "insights.decision.override_boost",
  override_eco: "insights.decision.override_eco",
  override_custom: "insights.decision.override_custom",
  override_active: "insights.decision.override_active",
  presence_away: "insights.decision.presence_away",
  mold_prevention: "insights.decision.mold_prevention",
  humidity_comfort: "insights.decision.humidity_comfort",
  smart_ventilation: "insights.decision.smart_ventilation",
  preconditioning: "insights.decision.preconditioning",
  heat_source: "insights.decision.heat_source",
  mode_heating: "insights.decision.mode_heating",
  mode_cooling: "insights.decision.mode_cooling",
  mode_idle: "insights.decision.mode_idle",
};

/** Icon of each comfort factor the backend scores. */
const FACTOR_ICONS: Record<string, string> = {
  temperature: "mdi:thermometer",
  humidity: "mdi:water-percent",
  window: "mdi:window-closed-variant",
  air_quality: "mdi:air-filter",
  anomalies: "mdi:alert-circle-outline",
};

@customElement("rs-room-insights")
export class RsRoomInsights extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public readiness?: RoomReadiness;
  @property({ type: Array }) public decisionReasons: string[] = [];
  @property({ attribute: false }) public comfortScore?: RoomLiveData["comfort_score"];

  static styles = css`
    :host {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
  `;

  private _scoreColor(label: string): string {
    if (label === "fair") return "var(--warning-color, #ff9800)";
    if (label === "poor") return "var(--error-color, #db4437)";
    return "var(--success-color, #4caf50)";
  }

  render() {
    const language = this.hass.language;
    const reasons = this.decisionReasons.length ? this.decisionReasons : ["mode_idle"];
    const score = this.comfortScore;
    const readiness = this.readiness;
    return html`
      <rs-list-card .heading=${localize("insights.decision.title", language)}>
        ${score
          ? html`<rs-list-row
              icon="mdi:heart"
              .iconColor=${this._scoreColor(score.label)}
              .heading=${localize("card.comfort_score", language, { score: score.score })}
            ></rs-list-row>`
          : nothing}
        ${reasons
          .slice(0, 3)
          .map(
            (reason) =>
              html`<rs-list-row
                wrap
                icon="mdi:information-outline"
                icon-color="var(--primary-color)"
                .heading=${localize(
                  DECISION_KEYS[reason] ?? "insights.decision.mode_idle",
                  language,
                )}
              ></rs-list-row>`,
          )}
      </rs-list-card>
      ${readiness
        ? html`<rs-list-card .heading=${localize("insights.readiness.title", language)}>
            <rs-list-row
              wrap
              icon="mdi:clipboard-check-outline"
              .heading=${localize(
                `insights.readiness.${readiness.level}` as TranslationKey,
                language,
                { ready: readiness.ready_count, total: readiness.total_count },
              )}
            ></rs-list-row>
            ${readiness.items.map(
              (item) =>
                html`<rs-list-row
                  wrap
                  .icon=${item.status === "ready"
                    ? "mdi:check-circle"
                    : item.status === "missing"
                      ? "mdi:alert-circle"
                      : "mdi:information-outline"}
                  .iconColor=${item.status === "ready"
                    ? "var(--success-color, #4caf50)"
                    : item.status === "missing"
                      ? "var(--error-color, #db4437)"
                      : "var(--warning-color, #ff9800)"}
                  .heading=${localize(
                    `insights.readiness.item.${item.key}.${item.status}` as TranslationKey,
                    language,
                  )}
                ></rs-list-row>`,
            )}
          </rs-list-card>`
        : nothing}
      ${score?.breakdown
        ? html`<rs-list-card .heading=${localize("insights.comfort.title", language)}>
            <rs-list-row
              wrap
              icon="mdi:numeric"
              .heading=${localize("insights.comfort.base", language)}
              .secondary=${localize("insights.comfort.summary", language)}
              value="100"
            ></rs-list-row>
            ${Object.entries(score.breakdown).map(
              ([factor, detail]) =>
                html`<rs-list-row
                  wrap
                  .icon=${factor === "window" && detail.status === "open"
                    ? "mdi:window-open-variant"
                    : (FACTOR_ICONS[factor] ?? "mdi:information-outline")}
                  .iconColor=${detail.penalty ? "var(--warning-color, #ff9800)" : ""}
                  .heading=${localize(
                    `insights.comfort.factor.${factor}.${detail.status}` as TranslationKey,
                    language,
                  )}
                  .value=${detail.penalty
                    ? `−${detail.penalty}`
                    : localize("insights.comfort.no_penalty", language)}
                ></rs-list-row>`,
            )}
            <rs-list-row
              icon="mdi:heart"
              .iconColor=${this._scoreColor(score.label)}
              .heading=${localize("insights.comfort.total", language)}
              .value=${`${score.score}/100`}
            ></rs-list-row>
          </rs-list-card>`
        : nothing}
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-room-insights": RsRoomInsights;
  }
}
