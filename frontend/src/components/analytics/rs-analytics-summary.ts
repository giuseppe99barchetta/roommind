/**
 * rs-analytics-summary – What happened in the selected range, read from the history:
 * time on target, too cold, too warm, heating/cooling hours and runs (upstream analytics_stats).
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { AnalyticsStats } from "../../types";
import { localize } from "../../utils/localize";

@customElement("rs-analytics-summary")
export class RsAnalyticsSummary extends LitElement {
  @property({ attribute: false }) public stats: AnalyticsStats | null = null;
  @property({ type: Boolean }) public canHeat = true;
  @property({ type: Boolean }) public canCool = false;
  @property({ type: String }) public language = "en";

  render() {
    const s = this.stats;
    if (!s || s.hours <= 0) return nothing;
    const l = this.language;
    const c = s.comfort;
    const tiles: { label: string; value: string; sub?: string; tone?: string }[] = [];
    if (c) {
      tiles.push({
        label: localize("analytics.summary.on_target", l),
        value: pct(c.within_pct),
        tone: "ok",
      });
      if (this.canHeat) {
        tiles.push({
          label: localize("analytics.summary.too_cold", l),
          value: pct(c.below_pct),
          tone: "cold",
        });
      }
      if (this.canCool) {
        tiles.push({
          label: localize("analytics.summary.too_warm", l),
          value: pct(c.above_pct),
          tone: "warm",
        });
      }
    }
    if (this.canHeat || s.heating_hours > 0) {
      tiles.push({
        label: localize("analytics.summary.heating", l),
        value: hours(s.heating_hours),
        sub: localize("analytics.summary.runs", l, { n: s.heating_starts }),
      });
    }
    if (this.canCool || s.cooling_hours > 0) {
      tiles.push({
        label: localize("analytics.summary.cooling", l),
        value: hours(s.cooling_hours),
        sub: localize("analytics.summary.runs", l, { n: s.cooling_starts }),
      });
    }
    if (!tiles.length) return nothing;
    return html`<ha-card>
      <div class="head">${localize("analytics.summary.title", l)}</div>
      <div class="tiles">
        ${tiles.map(
          (t) =>
            html`<div class="tile ${t.tone ?? ""}">
              <span class="label">${t.label}</span>
              <span class="value">${t.value}</span>
              ${t.sub ? html`<span class="sub">${t.sub}</span>` : nothing}
            </div>`,
        )}
      </div>
    </ha-card>`;
  }

  static styles = css`
    ha-card {
      padding: 12px 16px 16px;
      margin-bottom: 16px;
    }
    .head {
      font-weight: 500;
      margin-bottom: 10px;
    }
    .tiles {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
      gap: 10px;
    }
    .tile {
      display: flex;
      flex-direction: column;
      gap: 2px;
      padding: 10px 12px;
      border-radius: 10px;
      background: var(--secondary-background-color, rgba(127, 127, 127, 0.08));
    }
    .label,
    .sub {
      font-size: 12px;
      color: var(--secondary-text-color);
    }
    .value {
      font-size: 20px;
      font-weight: 600;
      color: var(--primary-text-color);
    }
    .tile.ok .value {
      color: var(--success-color, #2e7d32);
    }
    .tile.cold .value {
      color: var(--info-color, #1565c0);
    }
    .tile.warm .value {
      color: var(--warning-color, #b26a00);
    }
  `;
}

function pct(value: number): string {
  return `${Math.round(value)} %`;
}

function hours(value: number): string {
  return value < 10 ? `${value.toFixed(1)} h` : `${Math.round(value)} h`;
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-analytics-summary": RsAnalyticsSummary;
  }
}
