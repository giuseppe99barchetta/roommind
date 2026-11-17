import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, RoomConfig, RoomWithoutArea } from "./types";
import { loadHaElements } from "./load-ha-elements";
import { localize } from "./utils/localize";
import "./components/rs-settings";
import {
  getSettingsCategory,
  resolveSettingsCategory,
} from "./components/settings/settings-categories";
import "./components/rs-analytics";
import { noteServerTime } from "./utils/server-clock";
import { computeAreaInfos, type AreaInfo } from "./utils/dashboard";
import type { HouseSummary } from "./components/dashboard/rs-dashboard";
import "./components/dashboard/rs-dashboard";
import "./components/dashboard/rs-dashboard-edit";
import "./components/shared/rs-icon-button";

/** From this own width the settings list and the selected panel sit side by side. */
const SETTINGS_WIDE_MIN = 900;

const BACK_PATH = "M20,11V13H8L13.5,18.5L12.08,19.92L4.16,12L12.08,4.08L13.5,5.5L8,11H20Z";

const DELETE_PATH =
  "M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z";

const CHART_PATH =
  "M16,11.78L20.24,4.45L21.97,5.45L16.74,14.5L10.23,10.75L5.46,19H22V21H2V3H4V17.54L9.5,8L16,11.78Z";

const THERMOMETER_PATH =
  "M15 13V5A3 3 0 0 0 9 5V13A5 5 0 1 0 15 13M12 4A1 1 0 0 1 13 5V8H11V5A1 1 0 0 1 12 4Z";

type TabId = "areas" | "analytics" | "settings";

@customElement("roommind-panel")
export class RoomMindPanel extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean, reflect: true }) public narrow = false;
  @property({ type: Object }) public route: { path: string } = { path: "" };
  @property({ type: Object }) public panel: Record<string, unknown> = {};

  @state() private _activeTab: TabId = "areas";
  @state() private _rooms: Record<string, RoomConfig> = {};
  @state() private _roomsWithoutArea: RoomWithoutArea[] = [];
  @state() private _roomsLoaded = false;
  @state() private _selectedAreaId: string | null = null;
  @state() private _analyticsRoom = "";
  @state() private _vacationActive = false;
  @state() private _vacationTemp: number | null = null;
  @state() private _vacationUntil: number | null = null;
  @state() private _hiddenRooms: string[] = [];
  @state() private _controlMode: "mpc" | "bangbang" = "bangbang";
  @state() private _climateControlActive = true;
  @state() private _presenceEnabled = false;
  @state() private _valveProtectionEnabled = false;
  @state() private _anyoneHome = true;
  @state() private _presencePersons: string[] = [];
  @state() private _presenceAwayAction: "eco" | "off" = "eco";
  @state() private _scheduleOffAction: "eco" | "off" = "eco";
  @state() private _saveStatus: "idle" | "saving" | "saved" | "error" = "idle";
  @state() private _roomOrder: string[] = [];
  @state() private _groupByFloor = false;
  @state() private _editing = false;
  @state() private _settingsCategory = "";
  @state() private _wide = typeof window !== "undefined" && window.innerWidth >= SETTINGS_WIDE_MIN;
  private _resizeObserver?: ResizeObserver;
  private _layoutRevisions: Record<string, number> = {};
  // Bumped on every local layout edit: a rooms/list answer sent before it keeps its layout fields out
  private _layoutEpoch = 0;
  @state() private _outdoorTemp: number | null = null;
  @state() private _elementsLoaded = false;

  private _refreshInterval?: ReturnType<typeof setInterval>;
  private _routeApplied = false;
  private _saveStatusTimeout?: ReturnType<typeof setTimeout>;
  private _areaInfosCache: AreaInfo[] = [];
  private _boundVisibilityHandler?: () => void;
  private _boundConnectionReady?: () => void;

  static styles = css`
    .edit-bar,
    .dashboard-actions {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      padding: 8px 16px 0;
    }
    .edit-bar {
      justify-content: space-between;
    }
    :host {
      display: block;
      font-family: var(
        --primary-font-family,
        Inter,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif
      );
      color: var(--primary-text-color);
      background: var(--primary-background-color);
      min-height: 100vh;
      --rs-radius: 18px;
      --rs-stroke: var(--divider-color, rgba(127, 127, 127, 0.16));

      /* Round the corners of all MDC-based inputs (ha-textfield, ha-select,
         ha-entity-picker, ha-combo-box) to match the rest of the design.
         The bottom corners are rounded via inputStyles in each component. */
      --mdc-shape-small: 12px;
      --mdc-shape-medium: 12px;
      --md-filled-text-field-container-shape: 12px;
      --md-outlined-text-field-container-shape: 12px;
    }

    .toolbar {
      display: flex;
      align-items: center;
      min-height: 64px;
      padding: 0 22px;
      font-size: 18px;
      background-color: var(--card-background-color, var(--primary-background-color));
      color: var(--primary-text-color);
      border-bottom: 1px solid var(--rs-stroke);
      box-sizing: border-box;
      position: sticky;
      top: 0;
      z-index: 4;
    }
    .brand-mark {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 34px;
      height: 34px;
      border-radius: 11px;
      background: var(--primary-color);
      color: white;
      margin-right: 10px;
      flex-shrink: 0;
    }
    .brand-mark ha-icon {
      --mdc-icon-size: 19px;
    }

    .toolbar .title {
      margin-left: 4px;
      font-weight: 750;
      letter-spacing: -0.035em;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      flex: 1;
    }

    .toolbar ha-icon-button {
      color: var(--app-header-text-color, var(--primary-text-color));
    }

    .save-indicator {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      font-weight: 400;
      margin-right: 8px;
      opacity: 1;
      transition: opacity 0.3s ease;
    }

    .save-indicator.fade-out {
      opacity: 0;
    }

    .save-indicator ha-icon {
      --mdc-icon-size: 18px;
    }

    .save-indicator.saving {
      color: var(--primary-color, #03a9f4);
    }

    .save-indicator.saved {
      color: var(--success-color, #4caf50);
    }

    .save-indicator.error {
      color: var(--error-color, #d32f2f);
    }

    .tabs {
      display: flex;
      gap: 6px;
      border-bottom: 1px solid var(--rs-stroke);
      padding: 8px 24px;
      background: var(--card-background-color, var(--primary-background-color));
      position: sticky;
      top: 64px;
      z-index: 3;
      overflow-x: auto;
      scrollbar-width: none;
    }

    .tab {
      padding: 11px 18px;
      cursor: pointer;
      border: none;
      border-radius: 11px;
      background: transparent;
      color: var(--secondary-text-color);
      font-size: 13px;
      font-weight: 650;
      transition:
        background 0.18s ease,
        color 0.18s ease;
      font-family: inherit;
      display: inline-flex;
      align-items: center;
      gap: 9px;
      white-space: nowrap;
    }
    .tab ha-icon {
      --mdc-icon-size: 18px;
    }

    .tab:hover {
      color: var(--primary-text-color);
    }

    .tab[active] {
      background: var(--primary-background-color);
      color: var(--primary-text-color);
    }
    .tab[active] ha-icon {
      color: var(--primary-color);
    }
    .tab:focus-visible {
      outline: 2px solid var(--primary-color);
      outline-offset: -2px;
    }

    .content {
      padding: 30px 24px 64px;
      max-width: 1320px;
      margin: 0 auto;
      box-sizing: border-box;
    }

    @media (max-width: 600px) {
      .toolbar {
        padding: 0 10px;
        min-height: 56px;
      }
      .tabs {
        top: 56px;
        padding: 7px 12px;
        gap: 4px;
      }
      .tab {
        padding: 10px 12px;
        font-size: 12px;
        gap: 6px;
      }
      .tab ha-icon {
        --mdc-icon-size: 16px;
      }
      .content {
        padding: 20px 14px 58px;
      }
    }

    .placeholder {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 80px 16px;
      text-align: center;
      color: var(--secondary-text-color);
    }

    .placeholder ha-icon {
      margin-bottom: 16px;
    }

    .placeholder p {
      font-size: 15px;
      max-width: 400px;
      line-height: 1.5;
    }

    .area-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(min(320px, 100%), 1fr));
      gap: 18px;
    }
    .dashboard-heading {
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      gap: 18px;
      margin: 0 0 20px;
    }
    .dashboard-heading h1 {
      margin: 7px 0 6px;
      font-weight: 750;
      letter-spacing: -0.04em;
      font-size: clamp(25px, 3vw, 34px);
      line-height: 1.2;
    }
    .dashboard-heading p {
      margin: 0;
      color: var(--secondary-text-color);
      line-height: 1.5;
      font-size: 13px;
    }
    .dashboard-eyebrow {
      text-transform: uppercase;
      font-size: 10px !important;
      letter-spacing: 0.14em;
      font-weight: 750;
    }
    .system-chip {
      display: inline-flex;
      align-items: center;
      gap: 9px;
      flex: 0 0 auto;
      padding: 10px 13px;
      font-size: 12px;
      font-weight: 650;
      border-radius: 999px;
      background: var(--card-background-color);
      border: 1px solid var(--rs-stroke);
    }
    .system-chip .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--secondary-text-color);
    }
    .system-chip.active .dot {
      background: var(--success-color, #36aa78);
    }
    @media (max-width: 650px) {
      .dashboard-heading {
        align-items: flex-start;
        flex-direction: column;
        gap: 13px;
      }
    }

    .loading {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 80px 16px;
      color: var(--secondary-text-color);
      font-size: 14px;
    }

    .stats-separator {
      width: 1px;
      height: 28px;
      background: var(--divider-color, #444);
      margin: 0 4px;
      flex-shrink: 0;
    }

    .stats-bar {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px 24px;
      margin-bottom: 24px;
      padding: 18px 22px;
      --ha-card-border-radius: var(--rs-radius);
      --ha-card-box-shadow: none;
      border: 1px solid var(--rs-stroke);
    }

    .stats-actions {
      display: flex;
      align-items: center;
      margin-left: auto;
      gap: 0;
    }

    .hidden-rooms-toggle {
      --mdc-icon-button-size: 36px;
      --mdc-icon-size: 20px;
      color: var(--secondary-text-color);
    }

    .hidden-rooms-panel {
      margin-bottom: 20px;
      padding: 12px 16px;
    }

    .hidden-rooms-header {
      font-size: 13px;
      font-weight: 500;
      color: var(--secondary-text-color);
      margin-bottom: 8px;
    }

    .hidden-room-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 6px 0;
    }

    .hidden-room-name {
      font-size: 14px;
      color: var(--primary-text-color);
    }

    .stat {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .stat-value {
      font-size: 24px;
      font-weight: 700;
      letter-spacing: -0.04em;
      color: var(--primary-text-color);
      --mdc-icon-size: 22px;
      line-height: 1;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 24px;
    }

    .stat-label {
      font-size: 10px;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.09em;
    }

    .floor-heading {
      font-size: 13px;
      font-weight: 750;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin: 20px 0 8px 0;
    }

    .floor-heading:first-of-type {
      margin-top: 0;
    }

    .reorder-btn {
      --mdc-icon-button-size: 36px;
      --mdc-icon-size: 20px;
      color: var(--secondary-text-color);
    }

    .reorder-done {
      font-size: 14px;
      margin-left: auto;
    }
  `;

  connectedCallback() {
    super.connectedCallback();
    this._resizeObserver ??= new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0;
      if (width > 0) this._wide = width >= SETTINGS_WIDE_MIN;
    });
    this._resizeObserver.observe(this);
    loadHaElements().then(() => {
      this._elementsLoaded = true;
    });
    this._loadRooms();
    this._refreshInterval = setInterval(() => this._loadRooms(), 5000);
    this.addEventListener("save-status", this._onSaveStatus as EventListener);
    if (!this._routeApplied) {
      this._applyRoute();
      this._routeApplied = true;
    }
    // Visibility handler survives disconnectedCallback (intentionally not removed).
    // HA's ha-panel-custom has a bug: after disconnect it clears _setProperties
    // but doesn't re-create the panel element on reconnect if the config hasn't
    // changed. This leaves a blank panel. Reload recovers from this state.
    if (!this._boundVisibilityHandler) {
      this._boundVisibilityHandler = () => {
        if (document.hidden) return;
        if (!this.isConnected) {
          window.location.reload();
          return;
        }
        this._loadRooms();
        this.requestUpdate();
      };
      document.addEventListener("visibilitychange", this._boundVisibilityHandler);
    }
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this._resizeObserver?.disconnect();
    if (this._refreshInterval) {
      clearInterval(this._refreshInterval);
      this._refreshInterval = undefined;
    }
    if (this._saveStatusTimeout) clearTimeout(this._saveStatusTimeout);
    this.removeEventListener("save-status", this._onSaveStatus as EventListener);
    // NOTE: _boundVisibilityHandler intentionally NOT removed here.
    // It must survive disconnect to detect when tab becomes visible again
    // and trigger re-navigation if HA removed our element during idle.
    if (this._boundConnectionReady) {
      this.hass?.connection?.removeEventListener("ready", this._boundConnectionReady);
      this._boundConnectionReady = undefined;
    }
  }

  render() {
    if (!this._elementsLoaded || !this.hass) return html``;

    const l = this.hass.language;
    const inDetail = !!this._selectedAreaId;
    const detailArea = inDetail ? this.hass?.areas?.[this._selectedAreaId!] : null;
    const settingsPage = this._settingsSubpage();

    const tabLabels: Record<TabId, string> = {
      areas: localize("panel.tab.rooms", l),
      analytics: localize("tabs.analytics", l),
      settings: localize("panel.tab.settings", l),
    };

    return html`
      <div class="toolbar">
        ${inDetail
          ? html`<ha-icon-button
              .path=${BACK_PATH}
              aria-label=${localize("panel.tab.rooms", l)}
              @click=${this._onBackFromDetail}
            ></ha-icon-button>`
          : settingsPage
            ? html`<ha-icon-button
                .path=${BACK_PATH}
                aria-label=${localize("settings.back", l)}
                @click=${this._onBackFromSettingsPage}
              ></ha-icon-button>`
            : html`<ha-menu-button .hass=${this.hass} .narrow=${this.narrow}></ha-menu-button>`}
        ${!inDetail && !settingsPage
          ? html`<span class="brand-mark"
              ><ha-icon icon="mdi:home-thermometer-outline"></ha-icon
            ></span>`
          : nothing}
        <div class="title">
          ${inDetail
            ? this._rooms[this._selectedAreaId!]?.display_name || detailArea?.name || ""
            : settingsPage
              ? localize(getSettingsCategory(settingsPage)!.title, l)
              : localize("panel.title", l)}
        </div>
        ${this._renderSaveIndicator()}
        ${inDetail && this._rooms[this._selectedAreaId!]
          ? html`<ha-icon-button
                .path=${CHART_PATH}
                @click=${this._onGoToAnalytics}
              ></ha-icon-button
              ><ha-icon-button .path=${DELETE_PATH} @click=${this._onDeleteRoom}></ha-icon-button>`
          : nothing}
        ${!inDetail && this._activeTab === "analytics" && this._analyticsRoom
          ? html`<ha-icon-button
              .path=${THERMOMETER_PATH}
              @click=${this._onGoToRoomFromAnalytics}
            ></ha-icon-button>`
          : nothing}
      </div>

      ${!inDetail
        ? html`
            <div class="tabs">
              ${(Object.keys(tabLabels) as TabId[]).map(
                (tab) => html`
                  <button
                    class="tab"
                    ?active=${this._activeTab === tab}
                    aria-current=${this._activeTab === tab ? "page" : "false"}
                    @click=${() => this._onTabClicked(tab)}
                  >
                    <ha-icon
                      icon=${tab === "areas"
                        ? "mdi:home-outline"
                        : tab === "analytics"
                          ? "mdi:chart-areaspline"
                          : "mdi:cog-outline"}
                    ></ha-icon>
                    ${tabLabels[tab]}
                  </button>
                `,
              )}
            </div>
          `
        : nothing}

      <div class="content">${this._renderTab()}</div>
    `;
  }

  private _renderTab() {
    switch (this._activeTab) {
      case "areas":
        return this._renderAreas();
      case "analytics":
        return html`<rs-analytics
          .hass=${this.hass}
          .rooms=${this._rooms}
          .initialRoom=${this._analyticsRoom}
          .controlMode=${this._controlMode}
          @room-selected=${this._onAnalyticsRoomSelected}
        ></rs-analytics>`;
      case "settings":
        return this._renderSettings();
      default:
        return nothing;
    }
  }

  private _renderAreas() {
    if (!this._roomsLoaded) {
      return html`<div class="loading">${localize("panel.loading", this.hass.language)}</div>`;
    }

    if (this._selectedAreaId) {
      const area = this.hass?.areas?.[this._selectedAreaId];
      if (area) {
        const config = this._rooms[this._selectedAreaId] ?? null;
        return html`
          <rs-room-detail
            .rooms=${this._rooms}
            .area=${area}
            .config=${config}
            .hass=${this.hass}
            .presenceEnabled=${this._presenceEnabled}
            .presencePersons=${this._presencePersons}
            .climateControlActive=${this._climateControlActive}
            .valveProtectionEnabled=${this._valveProtectionEnabled}
            .presenceAwayAction=${this._presenceAwayAction}
            .scheduleOffAction=${this._scheduleOffAction}
            .controlMode=${this._controlMode}
            .vacationActive=${this._vacationActive}
            .vacationUntil=${this._vacationUntil}
            .outdoorTemp=${this._outdoorTemp}
            @back-clicked=${this._onBackFromDetail}
            @room-updated=${this._onRoomUpdated}
          ></rs-room-detail>
        `;
      }
      this._selectedAreaId = null;
    }

    const common = {
      hass: this.hass,
      infos: this._areaInfosCache,
      hiddenRooms: this._hiddenRooms,
      groupByFloor: this._groupByFloor,
      controlMode: this._controlMode,
      climateControlActive: this._climateControlActive,
    };
    if (this._isEditing()) {
      return html`<div class="edit-bar">
          <span>${localize("panel.edit_rooms", this.hass.language)}</span>
          <ha-button @click=${this._stopEditing}
            >${localize("panel.edit.done", this.hass.language)}</ha-button
          >
        </div>
        <rs-dashboard-edit
          .hass=${common.hass}
          .infos=${common.infos}
          .hiddenRooms=${common.hiddenRooms}
          .groupByFloor=${common.groupByFloor}
          .controlMode=${common.controlMode}
          .climateControlActive=${common.climateControlActive}
          @room-order-changed=${this._onRoomOrderChanged}
          @room-hidden-changed=${this._onRoomHiddenChanged}
          @group-by-floor-changed=${this._onGroupByFloorChanged}
          @area-selected=${this._onAreaSelected}
        ></rs-dashboard-edit>`;
    }
    const summary: HouseSummary = {
      vacationActive: this._vacationActive,
      vacationUntil: this._vacationUntil,
      presenceEnabled: this._presenceEnabled,
      anyoneHome: this._anyoneHome,
      outdoorTemp: this._outdoorTemp,
    };
    return html`<div class="dashboard-actions">
        <rs-icon-button
          icon="mdi:pencil"
          .label=${localize("panel.edit_rooms", this.hass.language)}
          @click=${this._startEditing}
        ></rs-icon-button>
      </div>
      <rs-dashboard
        .hass=${common.hass}
        .infos=${common.infos}
        .hiddenRooms=${common.hiddenRooms}
        .groupByFloor=${common.groupByFloor}
        .controlMode=${common.controlMode}
        .climateControlActive=${common.climateControlActive}
        .summary=${summary}
        @area-selected=${this._onAreaSelected}
        @room-updated=${this._onRoomUpdated}
        @edit-requested=${this._startEditing}
      ></rs-dashboard>`;
  }

  private _renderSettings() {
    return html`<rs-settings
      .hass=${this.hass}
      .rooms=${this._rooms}
      .roomsWithoutArea=${this._roomsWithoutArea}
      .category=${this._settingsCategory}
      .wide=${this._wide}
      .controlMode=${this._controlMode}
      @settings-category-changed=${this._onSettingsCategoryChanged}
    ></rs-settings>`;
  }

  /** The settings category shown as its own page (narrow layout), else "". */
  private _settingsSubpage() {
    if (this._activeTab !== "settings" || this._selectedAreaId || this._wide) return "";
    return resolveSettingsCategory(
      this._settingsCategory,
      this._roomsWithoutArea.length > 0,
      false,
    );
  }

  private _onSettingsCategoryChanged(e: CustomEvent<{ category: string }>) {
    this._settingsCategory = e.detail.category;
    // Wide: a selection in the list/detail view; narrow: the category opens as its own page
    this._navigate(this._settingsCategory ? `/settings/${this._settingsCategory}` : "/settings", {
      replace: this._wide,
    });
  }

  private _onBackFromSettingsPage = () => {
    this._settingsCategory = "";
    this._navigateBack("/settings");
  };

  private async _loadRooms() {
    if (!this.hass) return;
    // A layout edit made while this request is out wins over its (older) layout fields
    const layoutEpoch = this._layoutEpoch;
    try {
      const result = await this.hass.callWS<{
        rooms: Record<string, RoomConfig>;
        rooms_without_area?: RoomWithoutArea[];
        vacation_active: boolean;
        server_time?: number;
        vacation_temp: number | null;
        vacation_until: number | null;
        hidden_rooms: string[];
        room_order: string[];
        outdoor_temp?: number | null;
        group_by_floor: boolean;
        control_mode: "mpc" | "bangbang";
        climate_control_active: boolean;
        presence_enabled: boolean;
        anyone_home: boolean;
        presence_persons: string[];
        presence_away_action: "eco" | "off";
        schedule_off_action: "eco" | "off";
        valve_protection_enabled: boolean;
      }>({
        type: "roommind/rooms/list",
      });
      noteServerTime(result.server_time);
      this._rooms = result.rooms;
      this._roomsWithoutArea = result.rooms_without_area ?? [];
      this._vacationActive = result.vacation_active ?? false;
      this._vacationTemp = result.vacation_temp ?? null;
      this._vacationUntil = result.vacation_until ?? null;
      if (layoutEpoch === this._layoutEpoch) {
        this._hiddenRooms = result.hidden_rooms ?? [];
        this._roomOrder = result.room_order ?? [];
        this._groupByFloor = result.group_by_floor ?? false;
      }
      this._outdoorTemp = result.outdoor_temp ?? null;
      this._controlMode = result.control_mode ?? "bangbang";
      this._climateControlActive = result.climate_control_active ?? true;
      this._presenceEnabled = result.presence_enabled ?? false;
      this._valveProtectionEnabled = result.valve_protection_enabled ?? false;
      this._anyoneHome = result.anyone_home ?? true;
      this._presencePersons = result.presence_persons ?? [];
      this._presenceAwayAction = result.presence_away_action ?? "eco";
      this._scheduleOffAction = result.schedule_off_action ?? "eco";
    } catch (err) {
      // eslint-disable-next-line no-console
      console.debug("[RoomMind] loadRooms:", err);
    } finally {
      this._roomsLoaded = true;
    }
  }

  private _onBackFromDetail() {
    this._selectedAreaId = null;
    this._navigateBack("");
  }

  private _deletingAreaId: string | null = null;

  private async _onDeleteRoom() {
    if (!this._selectedAreaId) return;
    // One delete at a time: an overlapping one could resume saving a deleted room.
    if (this._deletingAreaId) return;
    const areaId = this._selectedAreaId;
    const area = this.hass?.areas?.[areaId];
    if (!area) return;

    if (!confirm(localize("room.confirm_delete", this.hass.language, { name: area.name }))) {
      return;
    }

    // Otherwise the detail view flushes its pending edit on unmount and
    // rooms/save recreates the room that was just deleted.
    const detail = this.renderRoot.querySelector("rs-room-detail");
    detail?.beginDelete();
    this._deletingAreaId = areaId;
    // The user may open another room while the request is pending.
    const stillShown = () => this._selectedAreaId === areaId;
    try {
      await this.hass.callWS({ type: "roommind/rooms/delete", area_id: areaId });
      if (stillShown()) {
        this._selectedAreaId = null;
        this._navigateBack("");
      }
      this._loadRooms();
    } catch (err) {
      if (stillShown()) {
        detail?.deleteFailed(
          (err as { message?: string } | null)?.message ||
            localize("room.error_delete_fallback", this.hass.language),
        );
      }
    } finally {
      this._deletingAreaId = null;
    }
  }

  private _onTabClicked(tab: TabId) {
    this._activeTab = tab;
    this._selectedAreaId = null;
    this._settingsCategory = "";
    if (tab === "areas") {
      this._navigate("");
    } else {
      this._navigate(`/${tab}`);
    }
  }

  private _onAreaSelected(e: CustomEvent<{ areaId: string }>) {
    this._stopEditing();
    this._selectedAreaId = e.detail.areaId;
    this._navigate(`/room/${e.detail.areaId}`);
  }

  private _onGoToAnalytics() {
    if (!this._selectedAreaId) return;
    this._analyticsRoom = this._selectedAreaId;
    this._selectedAreaId = null;
    this._activeTab = "analytics";
    this._navigate(`/analytics/${this._analyticsRoom}`);
  }

  private _onGoToRoomFromAnalytics() {
    if (!this._analyticsRoom) return;
    this._selectedAreaId = this._analyticsRoom;
    this._activeTab = "areas";
    this._navigate(`/room/${this._analyticsRoom}`);
  }

  private _onAnalyticsRoomSelected(e: CustomEvent<{ areaId: string }>) {
    this._analyticsRoom = e.detail.areaId;
    this._navigate(`/analytics/${e.detail.areaId}`, { replace: true });
  }

  private _isEditing(): boolean {
    return this._editing && this._activeTab === "areas" && !this._selectedAreaId;
  }

  private _startEditing = () => {
    this._editing = true;
    window.addEventListener("keydown", this._onEditKey);
  };

  private _stopEditing = () => {
    this._editing = false;
    window.removeEventListener("keydown", this._onEditKey);
  };

  private _onEditKey = (e: KeyboardEvent) => {
    // Tooltips, menus and a running drag catch their own Esc first (capture phase).
    if (e.key === "Escape" && this._isEditing() && !e.defaultPrevented) this._stopEditing();
  };

  private _onRoomOrderChanged(e: CustomEvent<{ order: string[] }>) {
    const previous = this._roomOrder;
    this._roomOrder = e.detail.order;
    this._areaInfosCache = computeAreaInfos(this.hass, this._rooms, this._roomOrder);
    void this._saveLayout({ room_order: e.detail.order }, () => {
      this._roomOrder = previous;
      this._areaInfosCache = computeAreaInfos(this.hass, this._rooms, this._roomOrder);
    });
  }

  private _onRoomHiddenChanged(e: CustomEvent<{ areaId: string; hidden: boolean }>) {
    const previous = this._hiddenRooms;
    const { areaId, hidden } = e.detail;
    this._hiddenRooms = hidden
      ? [...new Set([...this._hiddenRooms, areaId])]
      : this._hiddenRooms.filter((id) => id !== areaId);
    void this._saveLayout({ hidden_rooms: this._hiddenRooms }, () => {
      this._hiddenRooms = previous;
    });
  }

  private _onGroupByFloorChanged(e: CustomEvent<{ value: boolean }>) {
    const previous = this._groupByFloor;
    this._groupByFloor = e.detail.value;
    void this._saveLayout({ group_by_floor: e.detail.value }, () => {
      this._groupByFloor = previous;
    });
  }

  /**
   * Dashboard layout through the settings merge (only the changed field). A failed save rolls
   * back only while it is still that field's latest change, then the server's state is reloaded:
   * an older failure must not undo a newer change that went through.
   */
  private async _saveLayout(changes: Record<string, unknown>, rollback: () => void) {
    const key = Object.keys(changes).join(",");
    const revision = (this._layoutRevisions[key] ?? 0) + 1;
    this._layoutRevisions[key] = revision;
    this._layoutEpoch++;
    try {
      await this.hass.callWS({ type: "roommind/settings/save", ...changes });
    } catch (err) {
      if (this._layoutRevisions[key] === revision) rollback();
      // eslint-disable-next-line no-console
      console.debug("[RoomMind] save layout:", err);
      await this._loadRooms();
    }
  }

  private _onRoomUpdated() {
    this._loadRooms();
  }

  private _onSaveStatus = (e: CustomEvent<{ status: "saving" | "saved" | "error" }>) => {
    e.stopPropagation();
    if (this._saveStatusTimeout) clearTimeout(this._saveStatusTimeout);
    this._saveStatus = e.detail.status;
    if (e.detail.status === "saved") {
      this._saveStatusTimeout = setTimeout(() => {
        this._saveStatus = "idle";
      }, 2000);
    }
  };

  private _renderSaveIndicator() {
    if (this._saveStatus === "idle") return nothing;
    const l = this.hass.language;
    const icon =
      this._saveStatus === "saving"
        ? "mdi:content-save-outline"
        : this._saveStatus === "saved"
          ? "mdi:check"
          : "mdi:alert-circle-outline";
    const label =
      this._saveStatus === "saving"
        ? localize("settings.saving", l)
        : this._saveStatus === "saved"
          ? localize("settings.saved", l)
          : localize("settings.error", l);
    return html`
      <span class="save-indicator ${this._saveStatus}">
        <ha-icon .icon=${icon}></ha-icon>
        ${label}
      </span>
    `;
  }

  protected willUpdate(changedProps: Map<string, unknown>) {
    if (changedProps.has("route") && this._routeApplied) {
      this._applyRoute();
    }
    if (changedProps.has("_rooms") || changedProps.has("hass")) {
      this._areaInfosCache = computeAreaInfos(this.hass, this._rooms, this._roomOrder);
    }
  }

  updated(changedProps: Map<string, unknown>) {
    if (changedProps.has("hass") && this.hass && !this._roomsLoaded) {
      this._loadRooms();
    }
    if (changedProps.has("hass") && this.hass?.connection && !this._boundConnectionReady) {
      this._boundConnectionReady = () => {
        this._loadRooms();
        this.requestUpdate();
      };
      this.hass.connection.addEventListener("ready", this._boundConnectionReady);
    }
  }

  /** A new page gets its own history entry, so the browser's back returns to the one before. */
  private _navigate(path: string, { replace = false } = {}) {
    const url = `/roommind${path}`;
    if (replace || url === location.pathname + location.search)
      history.replaceState(history.state, "", url);
    else history.pushState({ roommindFrom: location.pathname + location.search }, "", url);
    window.dispatchEvent(new Event("location-changed"));
  }

  /**
   * The toolbar's back: the browser's back when the page was opened from `path`, else `path`
   * in place of the current entry (a link opened straight into a room must not pile up pages).
   */
  private _navigateBack(path: string) {
    if ((history.state as { roommindFrom?: string } | null)?.roommindFrom === `/roommind${path}`) {
      history.back();
      return;
    }
    this._navigate(path, { replace: true });
  }

  private _applyRoute() {
    const path = this.route?.path ?? "";
    if (path.startsWith("/room/")) {
      this._activeTab = "areas";
      this._selectedAreaId = decodeURIComponent(path.slice(6));
    } else if (path.startsWith("/analytics/")) {
      this._activeTab = "analytics";
      this._selectedAreaId = null;
      this._analyticsRoom = decodeURIComponent(path.slice(11));
    } else if (path === "/analytics") {
      this._activeTab = "analytics";
      this._selectedAreaId = null;
      this._analyticsRoom = "";
    } else if (path === "/settings" || path.startsWith("/settings/")) {
      this._activeTab = "settings";
      this._selectedAreaId = null;
      const requested = decodeURIComponent(path.slice(10));
      this._settingsCategory = getSettingsCategory(requested) ? requested : "";
    } else {
      this._activeTab = "areas";
      this._selectedAreaId = null;
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "roommind-panel": RoomMindPanel;
  }
}
