/** Room readiness checklist and plain-language explanation of current control. */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, RoomLiveData, RoomReadiness } from "../types";
import { localize, type TranslationKey } from "../utils/localize";

const DECISION_KEYS: Record<string, TranslationKey> = {
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

@customElement("rs-room-insights")
export class RsRoomInsights extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public readiness?: RoomReadiness;
  @property({ type: Array }) public decisionReasons: string[] = [];
  @property({ attribute: false }) public comfortScore?: RoomLiveData["comfort_score"];

  static styles = css`
    :host {
      display: block;
    }
    ha-card {
      padding: 18px;
    }
    .insights-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 24px;
    }
    h3 {
      margin: 0 0 10px;
      font-size: 16px;
    }
    .subheading {
      margin-top: 0;
    }
    .decision,
    .check {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 8px 0;
      font-size: 14px;
    }
    .decision ha-icon {
      color: var(--primary-color);
    }
    .ready ha-icon {
      color: var(--success-color, #4caf50);
    }
    .recommended ha-icon {
      color: var(--warning-color, #ff9800);
    }
    .missing ha-icon {
      color: var(--error-color, #db4437);
    }
    .summary {
      color: var(--secondary-text-color);
      font-size: 13px;
    }
    .comfort-score {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 8px 0 2px;
      color: var(--primary-text-color);
      font-size: 14px;
      font-weight: 500;
    }
    .comfort-score ha-icon {
      color: var(--success-color, #4caf50);
    }
    .comfort-score.fair ha-icon {
      color: var(--warning-color, #ff9800);
    }
    .comfort-score.poor ha-icon {
      color: var(--error-color, #db4437);
    }
    .score-breakdown {
      margin-top: 16px;
      padding-top: 16px;
      border-top: 1px solid var(--divider-color);
    }
    .score-breakdown h3 {
      margin-bottom: 4px;
    }
    .score-base,
    .score-factor {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-top: 8px;
      font-size: 14px;
    }
    .score-base {
      font-weight: 500;
    }
    .score-factor .penalty {
      color: var(--error-color, #db4437);
      white-space: nowrap;
    }
    .score-factor .neutral {
      color: var(--secondary-text-color);
      white-space: nowrap;
    }
    @media (max-width: 680px) {
      .insights-grid {
        grid-template-columns: 1fr;
        gap: 16px;
      }
    }
  `;

  render() {
    const language = this.hass.language;
    const reasons = this.decisionReasons.length ? this.decisionReasons : ["mode_idle"];
    return html`
      <ha-card>
        <div class="insights-grid">
          <section>
            <h3>${localize("insights.decision.title", language)}</h3>
            ${this.comfortScore
              ? html`
                  <div class="comfort-score ${this.comfortScore.label}">
                    <ha-icon icon="mdi:heart"></ha-icon>
                    ${localize("card.comfort_score", language, { score: this.comfortScore.score })}
                  </div>
                `
              : nothing}
            ${reasons
              .slice(0, 3)
              .map(
                (reason) => html`
                  <div class="decision">
                    <ha-icon icon="mdi:information-outline"></ha-icon>${localize(
                      DECISION_KEYS[reason] ?? "insights.decision.mode_idle",
                      language,
                    )}
                  </div>
                `,
              )}
          </section>
          ${this.readiness
            ? html`<section>
                <h3 class="subheading">${localize("insights.readiness.title", language)}</h3>
                <div class="summary">
                  ${localize(
                    `insights.readiness.${this.readiness.level}` as TranslationKey,
                    language,
                    { ready: this.readiness.ready_count, total: this.readiness.total_count },
                  )}
                </div>
                ${this.readiness.items.map(
                  (item) => html`
                    <div class="check ${item.status}">
                      <ha-icon
                        icon=${item.status === "ready"
                          ? "mdi:check-circle"
                          : item.status === "missing"
                            ? "mdi:alert-circle"
                            : "mdi:information-outline"}
                      ></ha-icon>
                      ${localize(
                        `insights.readiness.item.${item.key}.${item.status}` as TranslationKey,
                        language,
                      )}
                    </div>
                  `,
                )}
              </section>`
            : nothing}
        </div>
        ${this.comfortScore?.breakdown
          ? html`<section class="score-breakdown">
              <h3>${localize("insights.comfort.title", language)}</h3>
              <div class="summary">${localize("insights.comfort.summary", language)}</div>
              <div class="score-base">
                <span>${localize("insights.comfort.base", language)}</span>
                <span>100</span>
              </div>
              ${Object.entries(this.comfortScore.breakdown).map(
                ([factor, detail]) => html`
                  <div class="score-factor">
                    <span
                      >${localize(
                        `insights.comfort.factor.${factor}.${detail.status}` as TranslationKey,
                        language,
                      )}</span
                    >
                    <span class=${detail.penalty ? "penalty" : "neutral"}>
                      ${detail.penalty
                        ? `−${detail.penalty}`
                        : localize("insights.comfort.no_penalty", language)}
                    </span>
                  </div>
                `,
              )}
              <div class="score-base">
                <span>${localize("insights.comfort.total", language)}</span>
                <span>${this.comfortScore.score}/100</span>
              </div>
            </section>`
          : nothing}
      </ha-card>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-room-insights": RsRoomInsights;
  }
}
