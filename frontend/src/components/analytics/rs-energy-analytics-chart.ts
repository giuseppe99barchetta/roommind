/** Energy analytics card: measured room/device consumption + learned forecast. */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { AnalyticsData, AnalyticsDataPoint, HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";

const PALETTE = ["#03a9f4", "#ff9800", "#8bc34a", "#9c27b0", "#009688", "#f44336"];

@customElement("rs-energy-analytics-chart")
export class RsEnergyAnalyticsChart extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public data: AnalyticsData | null = null;
  @property({ type: String }) public language = "en";

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

  render() {
    const points = this._points();
    const forecast = this.data?.forecast ?? [];
    const hasEnergy =
      points.some((p) => p.ac_power_w != null) || forecast.some((p) => p.predicted_power_w != null);
    if (!hasEnergy) return nothing;

    const deviceIds = this._deviceIds(points, forecast);
    const measured = points
      .filter((p) => p.ac_power_w != null)
      .map((p) => [p.ts * 1000, p.ac_power_w]);
    const predicted = forecast
      .filter((p) => p.predicted_power_w != null)
      .map((p) => [p.ts * 1000, p.predicted_power_w]);
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
        data: predicted,
        color: primaryColor,
        lineStyle: { width: 2, type: "dashed" },
        emphasis: { disabled: true },
      });
    }
    deviceIds.forEach((id, index) => {
      const color = PALETTE[index % PALETTE.length];
      const actual = points
        .filter((p) => p.ac_device_power_w?.[id] != null)
        .map((p) => [p.ts * 1000, p.ac_device_power_w![id]]);
      const future = forecast
        .filter((p) => p.predicted_device_power_w?.[id] != null)
        .map((p) => [p.ts * 1000, p.predicted_device_power_w![id]]);
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
          data: future,
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

    const options = {
      animation: false,
      grid: { left: 55, right: 20, top: 24, bottom: 42 },
      tooltip: {
        trigger: "axis",
        axisPointer: { snap: false },
        valueFormatter: (value: number) => `${Math.round(value)} W`,
      },
      xAxis: { type: "time", axisLabel: { hideOverlap: true } },
      yAxis: { type: "value", min: 0, name: "W", nameGap: 12, splitLine: { show: true } },
    };

    return html`
      <ha-card>
        <div class="header">
          <div>
            <div class="title">${localize("analytics.energy_title", this.language)}</div>
            <div class="subtitle">${localize("analytics.energy_subtitle", this.language)}</div>
          </div>
          <ha-icon icon="mdi:lightning-bolt-outline"></ha-icon>
        </div>
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
        </div>
        <ha-chart-base
          .hass=${this.hass}
          .data=${series}
          .options=${options}
          .height=${"280px"}
          style="height:280px"
        ></ha-chart-base>
        <div class="legend">
          ${series.map(
            (s) =>
              html`<span><i style="background:${s.color as string}"></i>${s.name as string}</span>`,
          )}
        </div>
      </ha-card>
    `;
  }

  static styles = css`
    :host {
      display: block;
    }
    ha-card {
      margin-bottom: 16px;
      padding-bottom: 10px;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 16px 8px;
    }
    .title {
      font-size: 16px;
      font-weight: 500;
    }
    .subtitle {
      font-size: 12px;
      color: var(--secondary-text-color);
      margin-top: 3px;
    }
    .header ha-icon {
      color: var(--primary-color);
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
      padding: 6px 16px 4px;
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
    .legend {
      display: flex;
      justify-content: center;
      flex-wrap: wrap;
      gap: 8px 14px;
      padding: 2px 16px 8px;
      font-size: 11px;
      color: var(--secondary-text-color);
    }
    .legend span {
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }
    .legend i {
      width: 8px;
      height: 8px;
      border-radius: 50%;
    }
    @media (max-width: 700px) {
      .stats {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-energy-analytics-chart": RsEnergyAnalyticsChart;
  }
}
