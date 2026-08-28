/** Energy analytics card: measured room/device consumption + learned forecast. */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { AnalyticsData, AnalyticsDataPoint, HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { infoIconStyles } from "../../styles/info-icon-styles";

const PALETTE = ["#03a9f4", "#ff9800", "#8bc34a", "#9c27b0", "#009688", "#f44336"];
const FORECAST_MS = 3 * 3600_000;
type PowerPoint = [number, number];

@customElement("rs-energy-analytics-chart")
export class RsEnergyAnalyticsChart extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public data: AnalyticsData | null = null;
  @property({ type: Number }) public rangeStart = 0;
  @property({ type: Number }) public rangeEnd = 0;
  @property({ type: Number }) public chartAnchor = 0;
  @property({ type: String }) public language = "en";

  @state() private _hiddenSeries = new Set<string>();
  @state() private _chartInfoExpanded = false;

  private _points(): AnalyticsDataPoint[] {
    return this.data ? [...this.data.history, ...this.data.detail] : [];
  }

  private _deviceIds(points: AnalyticsDataPoint[], forecast: AnalyticsDataPoint[]): string[] {
    const ids = new Set<string>();
    for (const p of [...points, ...forecast]) {
      for (const key of Object.keys(p.ac_device_power_w ?? {})) ids.add(key);
      for (const key of Object.keys(p.predicted_device_power_w ?? {})) ids.add(key);
    }
    return [...ids].sort();
  }

  private _friendlyName(entityId: string): string {
    const state = this.hass.states[entityId];
    const friendly = state?.attributes?.friendly_name;
    return typeof friendly === "string" && friendly
      ? friendly
      : entityId.split(".").pop()!.replaceAll("_", " ");
  }

  private _integrate(points: Array<{ ts: number; value: number | null | undefined }>): number {
    const usable = points.filter((p) => p.value != null).sort((a, b) => a.ts - b.ts);
    let wh = 0;
    for (let i = 1; i < usable.length; i++) {
      const dtH = Math.min(Math.max(usable[i].ts - usable[i - 1].ts, 0), 900) / 3600;
      wh += ((usable[i - 1].value! + usable[i].value!) / 2) * dtH;
    }
    return wh / 1000;
  }

  private _connectForecast(measured: PowerPoint[], forecast: PowerPoint[]): PowerPoint[] {
    if (measured.length === 0 || forecast.length === 0) return forecast;
    const lastMeasured = measured.reduce((latest, point) => (point[0] > latest[0] ? point : latest));
    return lastMeasured[0] < forecast[0][0] ? [lastMeasured, ...forecast] : forecast;
  }

  private _toggleSeries(id: string) {
    const next = new Set(this._hiddenSeries);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    this._hiddenSeries = next;
  }

  render() {
    const points = this._points();
    const forecast = this.data?.forecast ?? [];
    const hasEnergy =
      points.some((p) => p.ac_power_w != null) || forecast.some((p) => p.predicted_power_w != null);
    if (!hasEnergy) return nothing;

    const deviceIds = this._deviceIds(points, forecast);
    const measured: PowerPoint[] = points
      .filter((p) => p.ac_power_w != null)
      .map((p) => [p.ts * 1000, p.ac_power_w!] as PowerPoint);
    const predicted: PowerPoint[] = forecast
      .filter((p) => p.predicted_power_w != null)
      .map((p) => [p.ts * 1000, p.predicted_power_w!] as PowerPoint);
    // ECharts draws on canvas and cannot resolve CSS custom properties. Passing
    // `var(--primary-color)` made the measured line black and unstable on hover.
    const primaryColor =
      getComputedStyle(this).getPropertyValue("--primary-color").trim() || "#03a9f4";
    const series: Array<Record<string, unknown>> = [
      {
        id: "room_power",
        name: localize("analytics.energy_room_power", this.language),
        type: "line",
        showSymbol: false,
        data: measured,
        color: primaryColor,
        lineStyle: { width: 2.5 },
        emphasis: { disabled: true },
      },
    ];
    if (predicted.length > 0) {
      series.push({
        id: "room_power_forecast",
        name: localize("analytics.energy_forecast", this.language),
        type: "line",
        showSymbol: false,
        data: this._connectForecast(measured, predicted),
        color: primaryColor,
        lineStyle: { width: 2, type: "dashed" },
        emphasis: { disabled: true },
      });
    }
    deviceIds.forEach((id, index) => {
      const color = PALETTE[index % PALETTE.length];
      const actual: PowerPoint[] = points
        .filter((p) => p.ac_device_power_w?.[id] != null)
        .map((p) => [p.ts * 1000, p.ac_device_power_w![id]] as PowerPoint);
      const future: PowerPoint[] = forecast
        .filter((p) => p.predicted_device_power_w?.[id] != null)
        .map((p) => [p.ts * 1000, p.predicted_device_power_w![id]] as PowerPoint);
      series.push({
        id: `device_${id}`,
        name: this._friendlyName(id),
        type: "line",
        showSymbol: false,
        data: actual,
        color,
        lineStyle: { width: 1.5, opacity: 0.75 },
        emphasis: { disabled: true },
      });
      if (future.length) {
        series.push({
          id: `device_forecast_${id}`,
          name: `${this._friendlyName(id)} · ${localize("analytics.energy_forecast_short", this.language)}`,
          type: "line",
          showSymbol: false,
          data: this._connectForecast(actual, future),
          color,
          lineStyle: { width: 1.5, type: "dashed", opacity: 0.75 },
          emphasis: { disabled: true },
        });
      }
    });

    const latest = [...points].reverse().find((p) => p.ac_power_w != null);
    const actualEnergy = this._integrate(points.map((p) => ({ ts: p.ts, value: p.ac_power_w })));
    const forecastEnergy = this._integrate(
      forecast.map((p) => ({ ts: p.ts, value: p.predicted_power_w })),
    );
    const latestSamples =
      [...points].reverse().find((p) => p.energy_learning_samples != null)
        ?.energy_learning_samples ?? 0;
    const latestConfidence =
      [...forecast, ...points].reverse().find((p) => p.energy_prediction_confidence != null)
        ?.energy_prediction_confidence;
    const cost = this.data?.energy_cost;

    const visiblePower: number[] = [];
    const displaySeries = series.map((s) => {
      const id = s.id as string;
      if (this._hiddenSeries.has(id)) {
        return { ...s, lineStyle: { ...(s.lineStyle as object), width: 0, opacity: 0 } };
      }
      for (const point of s.data as PowerPoint[]) visiblePower.push(point[1]);
      return s;
    });
    const maxPower = visiblePower.length > 0 ? Math.max(...visiblePower) : 0;
    const isLive = Math.abs(this.rangeEnd - Date.now()) < 3600_000;
    displaySeries.push({
      id: "now_marker",
      name: "",
      type: "line",
      color: "rgba(255,255,255,0.3)",
      data: [[this.chartAnchor, -1], [this.chartAnchor, Math.max(maxPower * 1.1, 1)]],
      showSymbol: false,
      lineStyle: { width: 1, type: "dashed" },
      tooltip: { show: false },
      z: -2,
    });
    const options = {
      animation: false,
      grid: { top: 15, left: 10, right: 10, bottom: 5, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { snap: false },
        valueFormatter: (value: number) => `${Math.round(value)} W`,
      },
      xAxis: {
        type: "time",
        min: this.rangeStart,
        max: isLive ? this.chartAnchor + FORECAST_MS : this.rangeEnd,
      },
      yAxis: { type: "value", min: 0, name: "W", nameGap: 12, splitLine: { show: true } },
      dataZoom: [{ type: "inside", xAxisIndex: 0, filterMode: "none" }],
    };

    return html`
      <ha-card>
        <div class="card-header">
          <span>${localize("analytics.energy_title", this.language)}</span>
          <ha-icon
            class="info-icon chart-info-toggle ${this._chartInfoExpanded ? "info-active" : ""}"
            icon="mdi:information-outline"
            @click=${() => {
              this._chartInfoExpanded = !this._chartInfoExpanded;
            }}
          ></ha-icon>
        </div>
        ${this._chartInfoExpanded
          ? html`<div class="chart-info-panel">
              ${localize("analytics.energy_chart_info_body", this.language)}
            </div>`
          : nothing}
        <div class="stats">
          <div class="stat">
            <span>${localize("analytics.energy_now", this.language)}</span
            ><strong
              >${latest?.ac_power_w != null ? `${Math.round(latest.ac_power_w)} W` : "—"}</strong
            >
          </div>
          <div class="stat">
            <span>${localize("analytics.energy_period", this.language)}</span
            ><strong>${actualEnergy.toFixed(2)} kWh</strong>
          </div>
          <div class="stat">
            <span>${localize("analytics.energy_next_3h", this.language)}</span
            ><strong>${predicted.length > 0 ? `${forecastEnergy.toFixed(2)} kWh` : "—"}</strong>
          </div>
          <div class="stat">
            <span>${localize("analytics.energy_learning", this.language)}</span
            ><strong>${latestSamples}</strong>
          </div>
          <div class="stat">
            <span>${localize("analytics.energy_confidence", this.language)}</span
            ><strong
              >${latestConfidence
                ? localize(`analytics.energy_confidence_${latestConfidence}`, this.language)
                : "â€”"}</strong
            >
          </div>
          ${cost
            ? html`
                <div class="stat">
                  <span>${localize("analytics.energy_cost_today", this.language)}</span
                  ><strong>€${cost.today_eur.toFixed(2)}</strong>
                </div>
                <div class="stat">
                  <span>${localize("analytics.energy_cost_7d", this.language)}</span
                  ><strong>€${cost.last_7d_eur.toFixed(2)}</strong>
                </div>
                <div class="stat">
                  <span>${localize("analytics.energy_cost_next_3h", this.language)}</span
                  ><strong>€${cost.forecast_3h_eur.toFixed(2)}</strong>
                </div>
              `
            : nothing}
        </div>
        <ha-chart-base
          .hass=${this.hass}
          .data=${displaySeries}
          .options=${options}
          .height=${"300px"}
          style="height: 300px"
        ></ha-chart-base>
        <div class="series-legend">
          ${series.map((s) => {
            const id = s.id as string;
            const hidden = this._hiddenSeries.has(id);
            return html`
              <button
                class="legend-item ${hidden ? "legend-hidden" : ""}"
                @click=${() => this._toggleSeries(id)}
              >
                <span class="legend-dot" style="background: ${s.color as string}"></span>
                ${s.name as string}
              </button>
            `;
          })}
        </div>
      </ha-card>
    `;
  }

  static styles = [
    infoIconStyles,
    css`
    :host {
      display: block;
    }
    ha-card {
      margin-bottom: 16px;
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 16px 0;
      font-size: 16px;
      font-weight: 500;
    }
    .chart-info-toggle {
      --mdc-icon-size: 20px;
    }
    .chart-info-panel {
      margin: 8px 16px 4px;
      padding: 12px 14px;
      border-radius: 8px;
      background: var(--secondary-background-color, rgba(128, 128, 128, 0.06));
      font-size: 13px;
      line-height: 1.6;
      color: var(--secondary-text-color);
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
      padding: 12px 16px 4px;
    }
    .stat {
      background: var(--secondary-background-color);
      border-radius: 10px;
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
      gap: 3px;
    }
    .stat span {
      font-size: 11px;
      color: var(--secondary-text-color);
    }
    .stat strong {
      font-size: 15px;
      font-weight: 600;
    }
    .series-legend {
      display: flex;
      justify-content: center;
      flex-wrap: wrap;
      gap: 6px;
      padding: 8px 16px 12px;
    }
    .legend-item {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border: none;
      border-radius: 12px;
      background: transparent;
      color: var(--primary-text-color);
      font-size: 12px;
      font-family: inherit;
      cursor: pointer;
      transition: opacity 0.2s;
    }
    .legend-item:hover {
      background: var(--secondary-background-color, rgba(128, 128, 128, 0.1));
    }
    .legend-item.legend-hidden {
      opacity: 0.35;
    }
    .legend-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex-shrink: 0;
    }
    @media (max-width: 700px) {
      .stats {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-energy-analytics-chart": RsEnergyAnalyticsChart;
  }
}
