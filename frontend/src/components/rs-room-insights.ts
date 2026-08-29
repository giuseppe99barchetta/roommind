/** Room readiness checklist and plain-language explanation of current control. */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, RoomReadiness } from "../types";
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

  static styles = css`
    :host {
      display: block;
    }
    ha-card {
      padding: 18px;
    }
    h3 {
      margin: 0 0 10px;
      font-size: 16px;
    }
    .subheading {
      margin-top: 18px;
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
  `;

  render() {
    const language = this.hass.language;
    const reasons = this.decisionReasons.length ? this.decisionReasons : ["mode_idle"];
    return html`
      <ha-card>
        <h3>${localize("insights.decision.title", language)}</h3>
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
        ${this.readiness
          ? html`
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
            `
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
