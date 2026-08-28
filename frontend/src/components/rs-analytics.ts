/**
 * rs-analytics – Analytics tab orchestrator.
 * Delegates rendering to rs-analytics-toolbar, rs-analytics-chart, rs-analytics-model.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, RoomConfig, AnalyticsData } from "../types";
import { localize, type TranslationKey } from "../utils/localize";
import "./analytics/rs-analytics-toolbar";
import "./analytics/rs-analytics-chart";
import "./analytics/rs-energy-analytics-chart";
import "./analytics/rs-analytics-model";

type ComparisonRoom = Record<string, string | number | null | string[]>;

@customElement("rs-analytics")
export class RsAnalytics extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Object }) public rooms: Record<string, RoomConfig> = {};
  @property() public initialRoom = "";
  @property() public controlMode: "mpc" | "bangbang" = "bangbang";

  @state() private _selectedRoom = "";
  @state() private _rangeStart: number = new Date(new Date().setHours(0, 0, 0, 0)).getTime();
  @state() private _rangeEnd: number = Date.now();
  @state() private _data: AnalyticsData | null = null;
  @state() private _chartAnchor: number = Date.now();
  @state() private _loading = false;
  @state() private _activeQuick: string | null = "24h";
  @state() private _comparison: ComparisonRoom[] = [];
  @state() private _comparisonInfoExpanded = false;

  private _refreshInterval?: ReturnType<typeof setInterval>;

  private static readonly _comparisonQualityKeys: Record<string, TranslationKey> = {
    insufficient_samples: "analytics.comparison_quality_insufficient_samples",
    no_power_measurements: "analytics.comparison_quality_no_power_measurements",
    history_gaps: "analytics.comparison_quality_history_gaps",
  };

  connectedCallback() {
    super.connectedCallback();
    this._refreshInterval = setInterval(() => this._silentRefresh(), 60_000);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._refreshInterval) {
      clearInterval(this._refreshInterval);
      this._refreshInterval = undefined;
    }
  }

  protected willUpdate(changedProps: Map<string, unknown>) {
    if (changedProps.has("initialRoom") && this.initialRoom) {
      this._selectedRoom = this.initialRoom;
    }
    let autoSelected = false;
    if (changedProps.has("rooms") && !this._selectedRoom) {
      const configured = Object.keys(this.rooms);
      if (configured.length > 0) {
        this._selectedRoom = configured[0];
        autoSelected = true;
        this.dispatchEvent(
          new CustomEvent("room-selected", {
            detail: { areaId: configured[0] },
            bubbles: true,
            composed: true,
          }),
        );
      }
    }
    if (
      autoSelected ||
      changedProps.has("_selectedRoom") ||
      changedProps.has("_rangeStart") ||
      changedProps.has("_rangeEnd")
    ) {
      if (this._selectedRoom) {
        this._fetchData();
      }
    }
  }

  protected render() {
    const l = this.hass.language;

    return html`
      <rs-analytics-toolbar
        .hass=${this.hass}
        .rooms=${this.rooms}
        .selectedRoom=${this._selectedRoom}
        .rangeStart=${this._rangeStart}
        .rangeEnd=${this._rangeEnd}
        .activeQuick=${this._activeQuick}
        .data=${this._data}
        .language=${l}
        @room-selected=${this._onRoomSelected}
        @range-changed=${this._onRangeChanged}
      ></rs-analytics-toolbar>
      ${this._selectedRoom
        ? this._loading
          ? html`<div class="loading">${localize("panel.loading", l)}</div>`
          : html`
              <rs-analytics-chart
                .hass=${this.hass}
                .data=${this._data}
                .rangeStart=${this._rangeStart}
                .rangeEnd=${this._rangeEnd}
                .chartAnchor=${this._chartAnchor}
                .language=${l}
                .isOutdoor=${this.rooms[this._selectedRoom]?.is_outdoor ?? false}
              ></rs-analytics-chart>
              ${!this.rooms[this._selectedRoom]?.is_outdoor
                ? html`
                    <rs-energy-analytics-chart
                      .hass=${this.hass}
                      .data=${this._data}
                      .rangeStart=${this._rangeStart}
                      .rangeEnd=${this._rangeEnd}
                      .chartAnchor=${this._chartAnchor}
                      .language=${l}
                    ></rs-energy-analytics-chart>
                    ${this._comparison.length > 1
                      ? html`<ha-card class="comparison">
                          <div class="comparison-header">
                            <h3>${localize("analytics.comparison_title", l)}</h3>
                            <ha-icon
                              class="info-icon ${this._comparisonInfoExpanded ? "info-active" : ""}"
                              icon="mdi:information-outline"
                              @click=${() => {
                                this._comparisonInfoExpanded = !this._comparisonInfoExpanded;
                              }}
                            ></ha-icon>
                          </div>
                          ${this._comparisonInfoExpanded
                            ? html`<div class="info-panel comparison-info-panel">
                                ${localize("analytics.comparison_info", l)}
                              </div>`
                            : nothing}
                          <table>
                            <thead><tr><th>${localize("analytics.comparison_room", l)}</th><th>kWh</th><th>€</th><th>${localize("analytics.comparison_active", l)}</th><th>${localize("analytics.comparison_efficiency", l)}</th><th>${localize("analytics.comparison_target", l)}</th></tr></thead>
                            <tbody>
                              ${this._comparison.map(
                                (room) => html`<tr>
                                  <td>
                                    ${room.name}
                                    ${Array.isArray(room.data_quality) && room.data_quality.length
                                      ? html`<div class="comparison-quality">
                                          ${localize("analytics.comparison_data_incomplete", l)}:
                                          ${room.data_quality
                                            .map((issue) =>
                                              localize(
                                                RsAnalytics._comparisonQualityKeys[issue] ??
                                                  "analytics.comparison_data_incomplete",
                                                l,
                                              ),
                                            )
                                            .join(", ")}
                                        </div>`
                                      : nothing}
                                  </td><td>${room.energy_kwh ?? "—"}</td><td>${room.cost_eur ?? "—"}</td>
                                  <td>${room.active_minutes != null ? `${room.active_minutes} min` : "—"}</td>
                                  <td>${room.delta_t_per_kwh ?? "—"}</td>
                                  <td>${room.target_reach_minutes != null ? `${room.target_reach_minutes} min` : "—"}</td>
                                </tr>`,
                              )}
                            </tbody>
                          </table>
                        </ha-card>`
                      : nothing}
                    <rs-analytics-model
                    .hass=${this.hass}
                    .data=${this._data}
                    .language=${l}
                  ></rs-analytics-model>`
                : nothing}
            `
        : html`
            <div class="no-data">
              <ha-icon icon="mdi:chart-line" style="--mdc-icon-size: 48px; opacity: 0.4"></ha-icon>
              <p>${localize("analytics.select_room", l)}</p>
            </div>
          `}
    `;
  }

  private _onRoomSelected(e: CustomEvent) {
    const areaId = e.detail.areaId;
    if (areaId && areaId !== this._selectedRoom) {
      this._selectedRoom = areaId;
      this.dispatchEvent(
        new CustomEvent("room-selected", {
          detail: { areaId },
          bubbles: true,
          composed: true,
        }),
      );
    }
  }

  private _onRangeChanged(e: CustomEvent) {
    const { activeQuick, rangeStart, rangeEnd, chartAnchor } = e.detail;
    this._activeQuick = activeQuick;
    this._rangeStart = rangeStart;
    this._rangeEnd = rangeEnd;
    this._chartAnchor = chartAnchor;
  }

  private _buildWsParams(): Record<string, unknown> {
    return {
      type: "roommind/analytics/get",
      area_id: this._selectedRoom,
      start_ts: this._rangeStart / 1000,
      end_ts: this._rangeEnd / 1000,
    };
  }

  private async _fetchData() {
    if (!this._selectedRoom) return;
    this._loading = true;
    this._data = null;
    this._chartAnchor = this._rangeEnd;

    try {
      const result = await this.hass.callWS<AnalyticsData>(this._buildWsParams());
      this._data = result;
      try {
        const comparison = await this.hass.callWS<{ rooms: ComparisonRoom[] }>({
          type: "roommind/analytics/compare",
          start_ts: this._rangeStart / 1000,
          end_ts: this._rangeEnd / 1000,
        });
        this._comparison = comparison.rooms;
      } catch (err) {
        // eslint-disable-next-line no-console
        console.debug("[RoomMind] comparison:", err);
      }
    } catch (err) {
      // eslint-disable-next-line no-console
      console.debug("[RoomMind] fetchData:", err);
      this._data = null;
    } finally {
      this._loading = false;
    }
  }

  private async _silentRefresh() {
    if (!this._selectedRoom || this._loading) return;
    try {
      const result = await this.hass.callWS<AnalyticsData>(this._buildWsParams());
      this._data = result;
      try {
        const comparison = await this.hass.callWS<{ rooms: ComparisonRoom[] }>({
          type: "roommind/analytics/compare",
          start_ts: this._rangeStart / 1000,
          end_ts: this._rangeEnd / 1000,
        });
        this._comparison = comparison.rooms;
      } catch (err) {
        // eslint-disable-next-line no-console
        console.debug("[RoomMind] comparison:", err);
      }
      this._chartAnchor = Date.now();
    } catch (err) {
      // eslint-disable-next-line no-console
      console.debug("[RoomMind] silentRefresh:", err);
    }
  }

  static styles = css`
    :host {
      display: block;
    }

    .no-data {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 80px 16px;
      text-align: center;
      color: var(--secondary-text-color);
    }

    .no-data p {
      font-size: 15px;
      max-width: 400px;
      line-height: 1.5;
      margin-top: 16px;
    }

    .loading {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 80px 16px;
      color: var(--secondary-text-color);
      font-size: 14px;
    }

    .comparison { margin: 0 0 16px; overflow-x: auto; padding: 12px 16px; }
    .comparison-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
    .comparison h3 { margin: 0; font-size: 16px; }
    .comparison-info-panel { margin-bottom: 10px; }
    .comparison-quality { margin-top: 3px; color: var(--warning-color, #ff9800); font-size: 11px; white-space: normal; }
    .info-icon { --mdc-icon-size: 20px; color: var(--secondary-text-color); cursor: pointer; opacity: 0.5; }
    .info-icon.info-active { color: var(--primary-color); opacity: 1; }
    .info-panel { padding: 12px; border-radius: 8px; background: var(--secondary-background-color, rgba(128, 128, 128, 0.06)); font-size: 13px; line-height: 1.6; color: var(--secondary-text-color); }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { padding: 8px; text-align: right; border-top: 1px solid var(--divider-color); white-space: nowrap; }
    th:first-child, td:first-child { text-align: left; }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-analytics": RsAnalytics;
  }
}
