/**
 * rs-settings – Global RoomMind settings page (orchestrator).
 * Owns all state, loads/saves settings (the fork's diff + queue), shows the 2.0 list of
 * categories with the selected one's panel beside it (wide) or as its own page (narrow).
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type {
  HomeAssistant,
  GlobalSettings,
  RoomConfig,
  RoomWithoutArea,
  NotificationTarget,
  CompressorGroup,
} from "../types";
import { localize } from "../utils/localize";
import { fireSaveStatus } from "../utils/events";
import {
  normalizeBypassEntities,
  normalizeHeatingSettingsForWebsocket,
  normalizePowerSensorMode,
} from "../utils/heating-settings";
import { VACATION_SENTINEL } from "../utils/constants";
import {
  SETTINGS_GROUPS,
  getSettingsCategory,
  resolveSettingsCategory,
  type SettingsCategoryId,
} from "./settings/settings-categories";
import { tokens } from "../styles/tokens";
import { formatNumber, formatPercent } from "../utils/format";
import { formatTempLocale, tempUnit, toCelsius } from "../utils/temperature";
import { learningRoomIds } from "../utils/learning";
import "./shared/rs-list-row";
import "./shared/rs-badge";
import "./settings/rs-settings-general";
import "./settings/rs-settings-sensors";
import "./settings/rs-settings-control";
import "./settings/rs-settings-presence";
import "./settings/rs-settings-vacation";
import "./settings/rs-settings-valve";
import "./settings/rs-settings-head-offset";
import "./settings/rs-settings-orphans";
import type { HeadOffsets } from "./settings/rs-settings-head-offset";
import "./settings/rs-settings-compressor";
import "./settings/rs-settings-mold";
import "./settings/rs-settings-notifications";
import "./settings/rs-settings-learning";
import "./settings/rs-settings-reset";
import "./settings/rs-settings-heating-system";
import "./settings/rs-settings-preview";
import { changedSettings, snapshotSettings } from "../utils/settings-diff";
import { serverNow } from "../utils/server-clock";

@customElement("rs-settings")
export class RsSettings extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public rooms: Record<string, RoomConfig> = {};
  @property({ attribute: false }) public roomsWithoutArea: RoomWithoutArea[] = [];
  /** Requested category (from the URL); unknown or unavailable ones fall back. */
  @property({ type: String }) public category = "";
  /** List and panel side by side; otherwise list, then the panel as a subpage. */
  @property({ type: Boolean }) public wide = true;

  @state() private _groupByFloor = false;
  @state() private _climateControlActive = true;
  @state() private _temperatureRoundingMode: "nearest" | "down" | "up" = "nearest";
  @state() private _learningDisabledRooms: string[] = [];
  @state() private _outdoorTempSensor = "";
  @state() private _outdoorHumiditySensor = "";
  @state() private _outdoorCoolingMin = 16;
  @state() private _outdoorHeatingMax = 22;
  @state() private _comfortWeight = 70;
  @state() private _weatherEntity = "";
  @state() private _outdoorUnavailableNotify = true;
  @state() private _predictionEnabled = true;
  @state() private _vacationActive = false;
  @state() private _vacationTemp = 15;
  @state() private _vacationUntil = "";
  @state() private _presenceEnabled = false;
  @state() private _presencePersons: string[] = [];
  @state() private _presenceAwayAction: "eco" | "off" = "eco";
  @state() private _presenceClearsOverride = false;
  @state() private _scheduleOffAction: "eco" | "off" = "eco";
  @state() private _valveProtectionEnabled = false;
  @state() private _acHeadOffsetEnabled = false;
  @state() private _acHeadOffsets: HeadOffsets = {};
  @state() private _valveProtectionInterval = 7;
  @state() private _moldDetectionEnabled = false;
  @state() private _moldHumidityThreshold = 70;
  @state() private _moldSustainedMinutes = 30;
  @state() private _moldNotificationCooldown = 60;
  @state() private _moldNotificationsEnabled = true;
  @state() private _moldNotificationTargets: NotificationTarget[] = [];
  @state() private _moldPreventionEnabled = false;
  @state() private _moldPreventionSustainedMinutes = 15;
  @state() private _moldPreventionDehumidificationEnabled = true;
  @state() private _moldPreventionDryMinTemperature = 23;
  @state() private _moldPreventionNotify = false;
  @state() private _windowOpenNotificationMinutes = 0;
  @state() private _compressorGroups: CompressorGroup[] = [];
  @state() private _boostAppliedAt: Record<string, number> = {};
  @state() private _boilerEntity = "";
  @state() private _boilerControlType: "climate" | "switch" = "climate";
  @state() private _bypassEntities: string[] = [];
  @state() private _startupDelay = 30;
  @state() private _shutdownDelay = 60;
  @state() private _bypassTemperature = 28;
  @state() private _bypassChildLock = true;
  @state() private _minDemandRooms = 1;
  @state() private _demandUnit: "valves" | "rooms" = "valves";
  @state() private _minRunMinutes = 5;
  @state() private _minOffMinutes = 3;
  @state() private _faultRetryMinutes = 5;
  @state() private _maxWaitMinutes = 120;
  @state() private _budgetEnabled = false;
  @state() private _powerSensor = "";
  @state() private _powerMode: "available" | "consumption" = "available";
  @state() private _powerModeDirty = false;
  @state() private _maxPower = 3300;
  @state() private _reserve = 200;
  @state() private _unavailableBehavior: "boiler" | "allow" = "boiler";
  @state() private _energyPricePerKwh = 0;
  @state() private _loaded = false;
  // Load failed: the fields hold defaults, so nothing may be saved (it would reset settings).
  @state() private _loadFailed = false;
  // Last payload known to the backend, per key (JSON); a save sends only keys that differ,
  // so a page left open does not undo changes made elsewhere.
  private _savedPayload: Record<string, string> | null = null;
  // Saves run one after another: each compares against what the previous one stored,
  // so reverting a value while a save is in flight still reaches the backend.
  private _saveQueue: Promise<void> = Promise.resolve();
  private _savesInFlight = 0;

  private _saveDebounce?: ReturnType<typeof setTimeout>;

  connectedCallback() {
    super.connectedCallback();
    this._loadSettings();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._saveDebounce) {
      clearTimeout(this._saveDebounce);
      this._saveDebounce = undefined;
      this._doSave();
    }
  }

  private async _loadSettings() {
    this._loadFailed = false;
    try {
      const result = await this.hass.callWS<{ settings: GlobalSettings }>({
        type: "roommind/settings/get",
      });
      const s = result.settings;
      this._groupByFloor = s.group_by_floor ?? false;
      this._climateControlActive = s.climate_control_active ?? true;
      this._temperatureRoundingMode = s.temperature_rounding_mode ?? "nearest";
      this._learningDisabledRooms = s.learning_disabled_rooms ?? [];
      this._outdoorTempSensor = s.outdoor_temp_sensor ?? "";
      this._outdoorHumiditySensor = s.outdoor_humidity_sensor ?? "";
      this._outdoorCoolingMin = s.outdoor_cooling_min ?? 16;
      this._outdoorHeatingMax = s.outdoor_heating_max ?? 22;
      this._comfortWeight = s.comfort_weight ?? 70;
      this._weatherEntity = s.weather_entity ?? "";
      this._outdoorUnavailableNotify = s.outdoor_unavailable_notify ?? true;
      this._predictionEnabled = s.prediction_enabled ?? true;
      const vUntil = s.vacation_until;
      this._vacationActive = !!(vUntil && vUntil > serverNow() / 1000);
      this._vacationTemp = s.vacation_temp ?? 15;
      if (vUntil && vUntil > serverNow() / 1000 && vUntil < VACATION_SENTINEL) {
        this._vacationUntil = this._tsToDatetimeLocal(vUntil);
      } else {
        this._vacationUntil = "";
      }
      this._presenceEnabled = s.presence_enabled ?? false;
      this._presencePersons = s.presence_persons ?? [];
      this._presenceAwayAction = s.presence_away_action ?? "eco";
      this._presenceClearsOverride = s.presence_clears_override ?? false;
      this._scheduleOffAction = s.schedule_off_action ?? "eco";
      this._valveProtectionEnabled = s.valve_protection_enabled ?? false;
      this._acHeadOffsetEnabled = s.ac_head_offset_enabled ?? false;
      this._acHeadOffsets = (s.ac_head_offsets ?? {}) as HeadOffsets;
      this._valveProtectionInterval = s.valve_protection_interval_days ?? 7;
      this._moldDetectionEnabled = s.mold_detection_enabled ?? false;
      this._moldHumidityThreshold = s.mold_humidity_threshold ?? 70;
      this._moldSustainedMinutes = s.mold_sustained_minutes ?? 30;
      this._moldNotificationCooldown = s.mold_notification_cooldown ?? 60;
      this._moldNotificationsEnabled = s.mold_notifications_enabled ?? true;
      this._moldNotificationTargets = s.mold_notification_targets ?? [];
      this._moldPreventionEnabled = s.mold_prevention_enabled ?? false;
      this._moldPreventionSustainedMinutes = s.mold_prevention_sustained_minutes ?? 60;
      this._moldPreventionDehumidificationEnabled =
        s.mold_prevention_dehumidification_enabled ?? true;
      this._moldPreventionDryMinTemperature = s.mold_prevention_dry_min_temperature ?? 22;
      this._moldPreventionNotify = s.mold_prevention_notify_enabled ?? false;
      this._windowOpenNotificationMinutes = s.window_open_notification_minutes ?? 0;
      this._compressorGroups = s.compressor_groups ?? [];
      this._boostAppliedAt = s.boost_applied_at ?? {};
      this._boilerEntity = s.boiler_entity ?? "";
      this._boilerControlType = s.boiler_control_type ?? "climate";
      this._bypassEntities = normalizeBypassEntities(s.hydraulic_bypass_entities);
      this._startupDelay = s.boiler_startup_delay_seconds ?? 30;
      this._shutdownDelay = s.boiler_shutdown_delay_seconds ?? 60;
      this._bypassTemperature = s.hydraulic_bypass_open_temperature ?? 28;
      this._bypassChildLock = s.hydraulic_bypass_child_lock ?? true;
      this._minDemandRooms = s.boiler_min_demand_rooms ?? 1;
      this._demandUnit = s.boiler_demand_unit ?? "valves";
      this._minRunMinutes = s.boiler_min_run_minutes ?? 5;
      this._minOffMinutes = s.boiler_min_off_minutes ?? 3;
      this._faultRetryMinutes = s.boiler_fault_retry_minutes ?? 5;
      this._maxWaitMinutes = s.boiler_max_wait_minutes ?? 120;
      this._budgetEnabled = s.power_budget_enabled ?? false;
      this._powerSensor = s.power_sensor ?? "";
      if (!this._powerModeDirty) {
        this._powerMode = normalizePowerSensorMode(s.power_sensor_mode);
      }
      this._maxPower = s.power_budget_max_watts ?? 3300;
      this._reserve = s.power_budget_reserve_watts ?? 200;
      this._unavailableBehavior = s.power_budget_unavailable_behavior ?? "boiler";
      this._energyPricePerKwh = s.energy_price_per_kwh ?? 0;
      this._savedPayload = snapshotSettings(this._buildPayload());
    } catch (err) {
      // eslint-disable-next-line no-console
      console.debug("[RoomMind] loadSettings:", err);
      this._loadFailed = true;
      this._savedPayload = null;
    } finally {
      this._loaded = true;
    }
  }

  protected render() {
    if (!this._loaded) {
      return html`<div class="loading">${localize("panel.loading", this.hass.language)}</div>`;
    }
    if (this._loadFailed) {
      return html`<div class="loading">
        <p>${localize("settings.load_failed", this.hass.language)}</p>
        <ha-button @click=${() => this._loadSettings()}
          >${localize("settings.retry", this.hass.language)}</ha-button
        >
      </div>`;
    }

    const selected = resolveSettingsCategory(this.category, this._hasOrphans(), this.wide);
    const subpage = !this.wide && !!selected;
    // Every panel stays mounted (only the selected one shown): panels with their own state
    // (preview result, a vacation time picked before the date, orphan deletions) keep it.
    return html`<div class="layout ${this.wide ? "wide" : ""}">
      <div class="nav-wrap" ?hidden=${subpage}>${this._renderNav(selected)}</div>
      <ha-card class="page ${this.wide ? "" : "subpage"}" ?hidden=${!selected}>
        ${selected ? this._renderPageHead(selected) : nothing}
        <div class="page-body">${this._renderPanels(selected)}</div>
      </ha-card>
    </div>`;
  }

  private _renderNav(selected: SettingsCategoryId | "") {
    const l = this.hass.language;
    const hasOrphans = this._hasOrphans();
    return html`<nav aria-label=${localize("panel.tab.settings", l)}>
      ${SETTINGS_GROUPS.map((group) => {
        const categories = group.categories.filter((c) => c.id !== "orphans" || hasOrphans);
        if (!categories.length) return nothing;
        return html`<section class="group">
          <h2 class="group-label">${localize(group.label, l)}</h2>
          <ha-card class="nav-card">
            ${categories.map((c) => {
              const summary = this._summary(c.id);
              const attention = c.id === "orphans";
              return html`<rs-list-row
                data-id=${c.id}
                href=${`/roommind/settings/${c.id}`}
                single-line
                .icon=${c.icon}
                .iconColor=${attention ? "var(--rs-warn)" : ""}
                .variant=${attention ? "warn" : "default"}
                .heading=${localize(c.title, l)}
                .secondary=${summary.text}
                .status=${summary.on === undefined ? "" : summary.on ? "on" : "off"}
                .selected=${this.wide && selected === c.id}
                .chevron=${!this.wide}
                @click=${(e: MouseEvent) => this._onNavClick(e, c.id)}
              ></rs-list-row>`;
            })}
          </ha-card>
        </section>`;
      })}
    </nav>`;
  }

  private _renderPageHead(id: SettingsCategoryId) {
    const l = this.hass.language;
    const category = getSettingsCategory(id)!;
    // As its own page the toolbar already shows the title; the heading stays for screen readers
    return html`<header class="page-head">
      <span class="page-icon ${id === "orphans" ? "attention" : ""}" aria-hidden="true">
        <ha-icon .icon=${category.icon}></ha-icon>
      </span>
      <div class="page-text">
        <div class="page-title-row">
          <h2 id="page-title" tabindex="-1">${localize(category.title, l)}</h2>
          ${id === "notifications"
            ? html`<rs-badge
                .label=${localize("badge.beta", l)}
                .hint=${localize("badge.beta_hint", l)}
              ></rs-badge>`
            : nothing}
        </div>
        <p>${localize(category.intro, l)}</p>
      </div>
    </header>`;
  }

  private _renderPanels(selected: SettingsCategoryId | "") {
    const show = (id: SettingsCategoryId) => selected !== id;
    return html`
      <div class="panel" ?hidden=${show("heating_system")}>
        <rs-settings-heating-system
          .hass=${this.hass}
          .boilerEntity=${this._boilerEntity}
          .boilerControlType=${this._boilerControlType}
          .bypassEntities=${this._bypassEntities}
          .startupDelay=${this._startupDelay}
          .shutdownDelay=${this._shutdownDelay}
          .bypassTemperature=${this._bypassTemperature}
          .bypassChildLock=${this._bypassChildLock}
          .minDemandRooms=${this._minDemandRooms}
          .demandUnit=${this._demandUnit}
          .minRunMinutes=${this._minRunMinutes}
          .minOffMinutes=${this._minOffMinutes}
          .faultRetryMinutes=${this._faultRetryMinutes}
          .maxWaitMinutes=${this._maxWaitMinutes}
          .budgetEnabled=${this._budgetEnabled}
          .powerSensor=${this._powerSensor}
          .powerMode=${this._powerMode}
          .maxPower=${this._maxPower}
          .reserve=${this._reserve}
          .energyPricePerKwh=${this._energyPricePerKwh}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-heating-system>
      </div>
      <div class="panel" ?hidden=${show("preview")}>
        <rs-settings-preview .hass=${this.hass}></rs-settings-preview>
      </div>
      <div class="panel" ?hidden=${show("general")}>
        <rs-settings-general
          .hass=${this.hass}
          .groupByFloor=${this._groupByFloor}
          .climateControlActive=${this._climateControlActive}
          .temperatureRoundingMode=${this._temperatureRoundingMode}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-general>
      </div>
      <div class="panel" ?hidden=${show("sensors")}>
        <rs-settings-sensors
          .hass=${this.hass}
          .outdoorTempSensor=${this._outdoorTempSensor}
          .outdoorHumiditySensor=${this._outdoorHumiditySensor}
          .weatherEntity=${this._weatherEntity}
          .outdoorUnavailableNotify=${this._outdoorUnavailableNotify}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-sensors>
      </div>
      <div class="panel" ?hidden=${show("control")}>
        <rs-settings-control
          .hass=${this.hass}
          .comfortWeight=${this._comfortWeight}
          .outdoorCoolingMin=${this._outdoorCoolingMin}
          .outdoorHeatingMax=${this._outdoorHeatingMax}
          .predictionEnabled=${this._predictionEnabled}
          .scheduleOffAction=${this._scheduleOffAction}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-control>
      </div>
      <div class="panel" ?hidden=${show("presence")}>
        <rs-settings-presence
          .hass=${this.hass}
          .presenceEnabled=${this._presenceEnabled}
          .presencePersons=${this._presencePersons}
          .presenceAwayAction=${this._presenceAwayAction}
          .presenceClearsOverride=${this._presenceClearsOverride}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-presence>
      </div>
      <div class="panel" ?hidden=${show("vacation")}>
        <rs-settings-vacation
          .hass=${this.hass}
          .vacationActive=${this._vacationActive}
          .vacationTemp=${this._vacationTemp}
          .vacationUntil=${this._vacationUntil}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-vacation>
      </div>
      <div class="panel" ?hidden=${show("valve")}>
        <rs-settings-valve
          .hass=${this.hass}
          .valveProtectionEnabled=${this._valveProtectionEnabled}
          .valveProtectionInterval=${this._valveProtectionInterval}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-valve>
      </div>
      <div class="panel" ?hidden=${show("compressor")}>
        <rs-settings-compressor
          .hass=${this.hass}
          .compressorGroups=${this._compressorGroups}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-compressor>
      </div>
      <div class="panel" ?hidden=${show("orphans")}>
        <rs-settings-orphans
          .hass=${this.hass}
          .rooms=${this.roomsWithoutArea}
        ></rs-settings-orphans>
      </div>
      <div class="panel" ?hidden=${show("head_offset")}>
        <rs-settings-head-offset
          .hass=${this.hass}
          .acHeadOffsetEnabled=${this._acHeadOffsetEnabled}
          .acHeadOffsets=${this._acHeadOffsets}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-head-offset>
      </div>
      <div class="panel" ?hidden=${show("mold")}>
        <rs-settings-mold
          .hass=${this.hass}
          .moldDetectionEnabled=${this._moldDetectionEnabled}
          .moldHumidityThreshold=${this._moldHumidityThreshold}
          .moldSustainedMinutes=${this._moldSustainedMinutes}
          .moldPreventionEnabled=${this._moldPreventionEnabled}
          .moldPreventionSustainedMinutes=${this._moldPreventionSustainedMinutes}
          .moldPreventionDehumidificationEnabled=${this._moldPreventionDehumidificationEnabled}
          .moldPreventionDryMinTemperature=${this._moldPreventionDryMinTemperature}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-mold>
      </div>
      <div class="panel" ?hidden=${show("notifications")}>
        <rs-settings-notifications
          .hass=${this.hass}
          .notificationsEnabled=${this._moldNotificationsEnabled}
          .notificationTargets=${this._moldNotificationTargets}
          .notificationCooldown=${this._moldNotificationCooldown}
          .moldPreventionEnabled=${this._moldPreventionEnabled}
          .moldPreventionNotify=${this._moldPreventionNotify}
          .windowOpenNotificationMinutes=${this._windowOpenNotificationMinutes}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-notifications>
      </div>
      <div class="panel" ?hidden=${show("learning")}>
        <rs-settings-learning
          .hass=${this.hass}
          .rooms=${this.rooms}
          .learningDisabledRooms=${this._learningDisabledRooms}
          .boostAppliedAt=${this._boostAppliedAt}
          .roomsLive=${Object.fromEntries(
            // eslint-disable-next-line @typescript-eslint/no-explicit-any -- HA room data includes untyped live state
            Object.entries(this.rooms).map(([id, r]) => [id, (r as any).live ?? {}]),
          )}
          @setting-changed=${this._onSettingChanged}
          @boost-applied=${this._onBoostApplied}
        ></rs-settings-learning>
      </div>
      <div class="panel" ?hidden=${show("reset")}>
        <rs-settings-reset .hass=${this.hass} .rooms=${this.rooms}></rs-settings-reset>
      </div>
    `;
  }

  /** One line per category in the list: what is set right now; `on` only for on/off features. */
  private _summary(id: SettingsCategoryId): { text: string; on?: boolean } {
    const l = this.hass.language;
    const off = localize("settings.summary.off", l);
    const count = (n: number) => formatNumber(n, this.hass);
    switch (id) {
      case "orphans": {
        const names = this.roomsWithoutArea.map((r) => r.display_name || r.area_id);
        return {
          text: localize(
            names.length === 1 ? "settings.summary.orphans_one" : "settings.summary.orphans",
            l,
            { count: count(names.length), names: new Intl.ListFormat(l).format(names) },
          ),
        };
      }
      case "general": {
        if (!this._climateControlActive) {
          return { text: localize("settings.summary.general_off", l), on: false };
        }
        const n = Object.values(this.rooms).filter(
          (r) =>
            (r.devices?.length ?? 0) > 0 && !r.is_outdoor && r.climate_control_enabled !== false,
        ).length;
        return {
          text: localize(
            n === 1 ? "settings.summary.general_on_one" : "settings.summary.general_on",
            l,
            { count: count(n) },
          ),
          on: true,
        };
      }
      case "vacation": {
        if (!this._vacationActive) return { text: off, on: false };
        const temp = `${formatTempLocale(this._vacationTemp, this.hass, 0, 1)} ${tempUnit(this.hass)}`;
        const until = this._vacationUntil ? new Date(this._vacationUntil) : null;
        return {
          text:
            until && !isNaN(until.getTime())
              ? localize("settings.summary.vacation_until", l, {
                  temp,
                  date: new Intl.DateTimeFormat(l, {
                    weekday: "short",
                    day: "numeric",
                    month: "short",
                    hour: "numeric",
                    minute: "2-digit",
                  }).format(until),
                })
              : localize("settings.summary.vacation_open", l, { temp }),
          on: true,
        };
      }
      case "presence": {
        if (!this._presenceEnabled) return { text: off, on: false };
        const n = this._presencePersons.filter((p) => p).length;
        const action = localize(
          this._presenceAwayAction === "off"
            ? "settings.summary.away_off"
            : "settings.summary.away_eco",
          l,
        );
        const key =
          n === 0
            ? "settings.summary.presence_none"
            : n === 1
              ? "settings.summary.presence_one"
              : "settings.summary.presence";
        return { text: localize(key, l, { count: count(n), action }), on: true };
      }
      case "control":
        // The fork has no Simple mode: "bangbang" from rooms/list only means MPC still learning
        return {
          text: localize("settings.summary.control_mpc", l, {
            weight: formatPercent(this._comfortWeight, this.hass),
          }),
        };
      case "sensors": {
        const parts: string[] = [];
        if (this._outdoorTempSensor) {
          const v = this._sensorValue(this._outdoorTempSensor);
          // As the backend reads it (temp_utils): the sensor's own unit, else Home Assistant's
          const unit = this.hass.states[this._outdoorTempSensor]?.attributes?.unit_of_measurement;
          const celsius =
            v === null
              ? null
              : unit
                ? unit === "°F"
                  ? ((v - 32) * 5) / 9
                  : v
                : toCelsius(v, this.hass);
          parts.push(
            celsius === null
              ? localize("settings.summary.outdoor_waiting", l)
              : localize("settings.summary.outdoor", l, {
                  value: `${formatTempLocale(celsius, this.hass, 0, 1)} ${tempUnit(this.hass)}`,
                }),
          );
        }
        if (this._outdoorHumiditySensor) {
          const v = this._sensorValue(this._outdoorHumiditySensor);
          if (v !== null) parts.push(formatPercent(v, this.hass));
        }
        if (this._weatherEntity) {
          const name =
            this.hass.states[this._weatherEntity]?.attributes?.friendly_name ?? this._weatherEntity;
          parts.push(localize("settings.summary.weather", l, { name: String(name) }));
        }
        return {
          text: parts.length ? parts.join(" · ") : localize("settings.summary.not_set_up", l),
        };
      }
      case "heating_system": {
        if (!this._boilerEntity) return { text: localize("settings.summary.not_set_up", l) };
        const name =
          this.hass.states[this._boilerEntity]?.attributes?.friendly_name ?? this._boilerEntity;
        return { text: localize("settings.summary.boiler", l, { name: String(name) }) };
      }
      case "head_offset":
        return this._acHeadOffsetEnabled
          ? { text: localize("settings.summary.on", l), on: true }
          : { text: off, on: false };
      case "preview":
        return { text: localize("preview.intro", l) };
      case "learning": {
        const ids = learningRoomIds(this.rooms);
        const paused = this._learningDisabledRooms.filter((rid) => ids.includes(rid)).length;
        let text: string;
        if (!ids.length) text = localize("settings.summary.learning_no_rooms", l);
        else if (!paused) {
          text = localize(
            ids.length === 1
              ? "settings.summary.learning_all_one"
              : "settings.summary.learning_all",
            l,
            { count: count(ids.length) },
          );
        } else if (paused === ids.length) {
          text = localize("settings.summary.learning_paused_all", l);
        } else {
          text = localize("settings.summary.learning_some", l, {
            paused: count(paused),
            count: count(ids.length),
          });
        }
        return { text };
      }
      case "mold": {
        const parts: string[] = [];
        if (this._moldDetectionEnabled) {
          parts.push(
            localize("settings.summary.mold_detect", l, {
              value: formatPercent(this._moldHumidityThreshold, this.hass),
            }),
          );
        }
        // The fork's prevention has no intensity setting (upstream's summary names its delta)
        if (this._moldPreventionEnabled)
          parts.push(localize("settings.summary.mold_prevent_on", l));
        return parts.length ? { text: parts.join(" · "), on: true } : { text: off, on: false };
      }
      case "valve":
        return this._valveProtectionEnabled
          ? {
              text: localize("settings.summary.valve_on", l, {
                days: count(this._valveProtectionInterval),
              }),
              on: true,
            }
          : { text: off, on: false };
      case "compressor": {
        const groups = this._compressorGroups.length;
        if (!groups) return { text: localize("settings.summary.compressor_none", l) };
        const devices = this._compressorGroups.reduce((n, g) => n + g.members.length, 0);
        return {
          text: [
            localize(groups === 1 ? "settings.summary.groups_one" : "settings.summary.groups", l, {
              count: count(groups),
            }),
            localize(
              devices === 1 ? "settings.summary.devices_one" : "settings.summary.devices",
              l,
              { count: count(devices) },
            ),
          ].join(" · "),
        };
      }
      case "notifications": {
        if (!this._moldNotificationsEnabled) return { text: off, on: false };
        // Mold detection, the prevention notice and the open-window notice send from this page
        if (
          !this._moldDetectionEnabled &&
          !(this._moldPreventionEnabled && this._moldPreventionNotify) &&
          !this._windowOpenNotificationMinutes
        ) {
          return { text: localize("settings.summary.notify_no_source", l), on: false };
        }
        const n = this._moldNotificationTargets.filter((t) => t.entity_id).length;
        const key =
          n === 0
            ? "settings.summary.notify_none"
            : n === 1
              ? "settings.summary.notify_one"
              : "settings.summary.notify";
        return { text: localize(key, l, { count: count(n) }), on: true };
      }
      case "reset":
        return { text: localize("settings.summary.reset", l) };
    }
  }

  private _sensorValue(entityId: string): number | null {
    const st = this.hass.states[entityId];
    if (!st || st.state === "unavailable" || st.state === "unknown") return null;
    const v = parseFloat(st.state);
    return isNaN(v) ? null : v;
  }

  private _hasOrphans(): boolean {
    return this.roomsWithoutArea.length > 0;
  }

  private _onNavClick(e: MouseEvent, id: SettingsCategoryId) {
    // Ctrl/Cmd/Shift/middle click keep the browser's "open in new tab".
    if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) return;
    e.preventDefault();
    this._selectCategory(id);
  }

  private _selectCategory(category: SettingsCategoryId | "") {
    this.dispatchEvent(
      new CustomEvent("settings-category-changed", {
        detail: { category },
        bubbles: true,
        composed: true,
      }),
    );
  }

  protected updated(changed: Map<string, unknown>) {
    // A deep link (e.g. the room page's presence link) can arrive before the settings loaded:
    // the heading only exists once they did, so focus then
    const loadedNow = changed.has("_loaded") && this._loaded;
    if ((!changed.has("category") && !loadedNow) || this.wide) return;
    const previous = changed.has("category") ? (changed.get("category") as string | undefined) : "";
    if (this.category && resolveSettingsCategory(this.category, this._hasOrphans(), false)) {
      // Subpage opened from a scrolled list: start at its top, focus its heading.
      window.scrollTo({ top: 0 });
      this.renderRoot.querySelector<HTMLElement>("#page-title")?.focus({ preventScroll: true });
    } else if (previous) {
      // Back to the list: return to the entry the subpage was opened from.
      const row = this.renderRoot.querySelector<HTMLElement>(`rs-list-row[data-id="${previous}"]`);
      row?.scrollIntoView({ block: "center" });
      row?.focus();
    }
  }

  private _onBoostApplied(e: CustomEvent<{ area_id: string; n_observations: number }>) {
    const { area_id, n_observations } = e.detail;
    this._boostAppliedAt = { ...this._boostAppliedAt, [area_id]: n_observations };
  }

  private _onSettingChanged(e: CustomEvent<{ key: string; value: unknown }>) {
    const { key, value } = e.detail;
    if (key === "bypassEntities") {
      this._bypassEntities = normalizeBypassEntities(value);
    } else if (key === "powerMode") {
      this._powerMode = normalizePowerSensorMode(value);
      this._powerModeDirty = true;
    } else {
      (this as Record<string, unknown>)[`_${key}`] = value;
    }
    this._autoSave();
  }

  private _tsToDatetimeLocal(ts: number): string {
    const d = new Date(ts * 1000);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  private _autoSave() {
    if (this._saveDebounce) clearTimeout(this._saveDebounce);
    this._saveDebounce = setTimeout(() => {
      this._saveDebounce = undefined;
      this._doSave();
    }, 500);
  }

  private _buildPayload() {
    // This is the final untrusted UI boundary. Do not rely on picker event
    // shapes here: Home Assistant components differ across releases.
    const { hydraulicBypassEntities, powerSensorMode } = normalizeHeatingSettingsForWebsocket(
      this._bypassEntities,
      this._powerMode,
    );
    return {
      group_by_floor: this._groupByFloor,
      climate_control_active: this._climateControlActive,
      temperature_rounding_mode: this._temperatureRoundingMode,
      learning_disabled_rooms: this._learningDisabledRooms,
      outdoor_temp_sensor: this._outdoorTempSensor,
      outdoor_humidity_sensor: this._outdoorHumiditySensor,
      outdoor_cooling_min: this._outdoorCoolingMin,
      outdoor_heating_max: this._outdoorHeatingMax,
      comfort_weight: this._comfortWeight,
      weather_entity: this._weatherEntity,
      outdoor_unavailable_notify: this._outdoorUnavailableNotify,
      prediction_enabled: this._predictionEnabled,
      vacation_temp: this._vacationTemp,
      vacation_until: this._vacationActive
        ? this._vacationUntil
          ? new Date(this._vacationUntil).getTime() / 1000
          : VACATION_SENTINEL
        : null,
      presence_enabled: this._presenceEnabled,
      presence_persons: this._presencePersons.filter((p) => p),
      presence_away_action: this._presenceAwayAction,
      presence_clears_override: this._presenceClearsOverride,
      schedule_off_action: this._scheduleOffAction,
      valve_protection_enabled: this._valveProtectionEnabled,
      ac_head_offset_enabled: this._acHeadOffsetEnabled,
      valve_protection_interval_days: this._valveProtectionInterval,
      compressor_groups: this._compressorGroups.filter((g) => g.members.length > 0),
      boiler_entity: this._boilerEntity,
      boiler_control_type: this._boilerControlType,
      boiler_startup_delay_seconds: this._startupDelay,
      boiler_shutdown_delay_seconds: this._shutdownDelay,
      hydraulic_bypass_entities: hydraulicBypassEntities,
      hydraulic_bypass_open_temperature: this._bypassTemperature,
      hydraulic_bypass_child_lock: this._bypassChildLock,
      boiler_min_demand_rooms: this._minDemandRooms,
      boiler_demand_unit: this._demandUnit,
      boiler_min_run_minutes: this._minRunMinutes,
      boiler_min_off_minutes: this._minOffMinutes,
      boiler_fault_retry_minutes: this._faultRetryMinutes,
      boiler_max_wait_minutes: this._maxWaitMinutes,
      power_budget_enabled: this._budgetEnabled,
      power_sensor: this._powerSensor,
      power_sensor_mode: powerSensorMode,
      power_budget_max_watts: this._maxPower,
      power_budget_reserve_watts: this._reserve,
      power_budget_unavailable_behavior: this._unavailableBehavior,
      energy_price_per_kwh: this._energyPricePerKwh,
      mold_detection_enabled: this._moldDetectionEnabled,
      mold_humidity_threshold: this._moldHumidityThreshold,
      mold_sustained_minutes: this._moldSustainedMinutes,
      mold_notification_cooldown: this._moldNotificationCooldown,
      mold_notifications_enabled: this._moldNotificationsEnabled,
      mold_notification_targets: this._moldNotificationTargets.filter((t) => t.entity_id),
      mold_prevention_enabled: this._moldPreventionEnabled,
      mold_prevention_sustained_minutes: this._moldPreventionSustainedMinutes,
      mold_prevention_dehumidification_enabled: this._moldPreventionDehumidificationEnabled,
      mold_prevention_dry_min_temperature: this._moldPreventionDryMinTemperature,
      mold_prevention_notify_enabled: this._moldPreventionNotify,
      mold_prevention_notify_targets: this._moldPreventionNotify
        ? this._moldNotificationTargets.filter((t) => t.entity_id)
        : [],
      window_open_notification_minutes: this._windowOpenNotificationMinutes,
    };
  }

  private _doSave(): Promise<void> {
    // Idle: start right away; busy: after the running one, against what it stored.
    const started =
      this._savesInFlight === 0 ? this._saveNow() : this._saveQueue.then(() => this._saveNow());
    this._savesInFlight++;
    this._saveQueue = started.finally(() => {
      this._savesInFlight--;
    });
    return this._saveQueue;
  }

  private async _saveNow() {
    // Never save after a failed load: the fields hold defaults and would reset everything.
    if (this._loadFailed || !this._savedPayload) return;
    fireSaveStatus(this, "saving");

    try {
      const full = this._buildPayload();
      const saved = this._savedPayload;
      const changed = changedSettings(full, saved);
      if (Object.keys(changed).length) {
        // eslint-disable-next-line no-console
        console.debug("RoomMind settings save payload", changed);
        await this.hass.callWS({ type: "roommind/settings/save", ...changed });
        Object.assign(saved, snapshotSettings(changed));
      }
      if (this._powerMode === full.power_sensor_mode) {
        this._powerModeDirty = false;
      }
      fireSaveStatus(this, "saved");
    } catch {
      fireSaveStatus(this, "error");
    }
  }

  static styles = [
    tokens,
    css`
      :host {
        display: block;
      }

      [hidden] {
        display: none !important;
      }

      .layout {
        display: flex;
        flex-direction: column;
        gap: var(--rs-space-5);
      }

      .layout.wide {
        display: grid;
        grid-template-columns: 330px minmax(0, 1fr);
        align-items: start;
      }

      nav {
        display: flex;
        flex-direction: column;
        gap: var(--rs-space-4);
        min-width: 0;
      }

      .group-label {
        margin: 0 var(--rs-space-2) var(--rs-space-2);
        font-size: var(--rs-font-sm);
        font-weight: 500;
        color: var(--secondary-text-color);
      }

      .nav-card {
        padding: var(--rs-space-1);
        --rs-list-row-padding: var(--rs-space-3);
      }

      .page {
        min-width: 0;
      }

      .page-head {
        display: flex;
        gap: var(--rs-space-4);
        align-items: flex-start;
        padding: var(--rs-space-5) var(--rs-space-5) var(--rs-space-4);
      }

      .page-icon {
        width: 48px;
        height: 48px;
        border-radius: 50%;
        flex: none;
        display: grid;
        place-items: center;
        background: var(--rs-fill-primary);
        color: var(--primary-color);
        --mdc-icon-size: 26px;
      }

      .page-icon.attention {
        background: color-mix(in srgb, var(--rs-warn) 14%, transparent);
        color: var(--rs-warn);
      }

      .page-text {
        min-width: 0;
      }

      .page-title-row {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: var(--rs-space-2);
        margin-top: 2px;
      }

      h2 {
        margin: 0;
        font-size: 22px;
        font-weight: 400;
        line-height: 1.3;
        overflow-wrap: anywhere;
      }

      h2:focus {
        outline: none;
      }

      .subpage .page-icon {
        display: none;
      }

      .subpage h2 {
        position: absolute;
        width: 1px;
        height: 1px;
        overflow: hidden;
        clip-path: inset(50%);
        white-space: nowrap;
      }

      .page-text p {
        margin: var(--rs-space-1) 0 0;
        color: var(--secondary-text-color);
        font-size: 13px;
        line-height: 1.5;
        max-width: 70ch;
      }

      .page-body {
        --rs-settings-inline: var(--rs-space-5);
        padding: 0 var(--rs-space-5) var(--rs-space-4);
      }

      @media (max-width: 600px) {
        .page-head {
          padding: var(--rs-space-4) var(--rs-space-4) var(--rs-space-3);
        }

        .page-body {
          --rs-settings-inline: var(--rs-space-4);
          padding: 0 var(--rs-space-4) var(--rs-space-3);
        }

        h2 {
          font-size: var(--rs-font-xl);
        }
      }

      .loading {
        padding: 80px 16px;
        text-align: center;
        color: var(--secondary-text-color);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings": RsSettings;
  }
}
