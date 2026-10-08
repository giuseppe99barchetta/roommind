/**
 * rs-settings – Global RoomMind settings page (orchestrator).
 * Owns all state, loads/saves settings, delegates rendering to sub-components
 * wrapped in ha-expansion-panel accordion sections.
 */
import { LitElement, html, css } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type {
  HomeAssistant,
  GlobalSettings,
  RoomConfig,
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
import "./settings/rs-settings-panel";
import "./settings/rs-settings-general";
import "./settings/rs-settings-sensors";
import "./settings/rs-settings-control";
import "./settings/rs-settings-presence";
import "./settings/rs-settings-vacation";
import "./settings/rs-settings-valve";
import "./settings/rs-settings-compressor";
import "./settings/rs-settings-mold";
import "./settings/rs-settings-notifications";
import "./settings/rs-settings-learning";
import "./settings/rs-settings-reset";
import "./settings/rs-settings-heating-system";
import "./settings/rs-settings-preview";

@customElement("rs-settings")
export class RsSettings extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public rooms: Record<string, RoomConfig> = {};

  @state() private _groupByFloor = false;
  @state() private _climateControlActive = true;
  @state() private _temperatureRoundingMode: "nearest" | "down" | "up" = "nearest";
  @state() private _learningDisabledRooms: string[] = [];
  @state() private _outdoorTempSensor = "";
  @state() private _outdoorHumiditySensor = "";
  @state() private _outdoorCoolingMin = 16;
  @state() private _outdoorHeatingMax = 22;
  @state() private _controlMode: "mpc" | "bangbang" = "mpc";
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
  @state() private _valveProtectionInterval = 7;
  @state() private _moldDetectionEnabled = false;
  @state() private _moldHumidityThreshold = 70;
  @state() private _moldSustainedMinutes = 30;
  @state() private _moldNotificationCooldown = 60;
  @state() private _moldNotificationsEnabled = true;
  @state() private _moldNotificationTargets: NotificationTarget[] = [];
  @state() private _moldPreventionEnabled = false;
  @state() private _moldPreventionSustainedMinutes = 15;
  @state() private _moldPreventionIntensity: "light" | "medium" | "strong" = "medium";
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
  @state() private _budgetEnabled = false;
  @state() private _powerSensor = "";
  @state() private _powerMode: "available" | "consumption" = "available";
  @state() private _powerModeDirty = false;
  @state() private _maxPower = 3300;
  @state() private _reserve = 200;
  @state() private _energyPricePerKwh = 0;
  @state() private _loaded = false;
  @state() private _category: "overview" | "system" | "protection" | "advanced" = "overview";

  private _saveDebounce?: ReturnType<typeof setTimeout>;

  connectedCallback() {
    super.connectedCallback();
    this._loadSettings();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._saveDebounce) clearTimeout(this._saveDebounce);
  }

  private async _loadSettings() {
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
      this._controlMode = s.control_mode ?? "mpc";
      this._comfortWeight = s.comfort_weight ?? 70;
      this._weatherEntity = s.weather_entity ?? "";
      this._outdoorUnavailableNotify = s.outdoor_unavailable_notify ?? true;
      this._predictionEnabled = s.prediction_enabled ?? true;
      const vUntil = s.vacation_until;
      this._vacationActive = !!(vUntil && vUntil > Date.now() / 1000);
      this._vacationTemp = s.vacation_temp ?? 15;
      if (vUntil && vUntil > Date.now() / 1000 && vUntil < VACATION_SENTINEL) {
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
      this._valveProtectionInterval = s.valve_protection_interval_days ?? 7;
      this._moldDetectionEnabled = s.mold_detection_enabled ?? false;
      this._moldHumidityThreshold = s.mold_humidity_threshold ?? 70;
      this._moldSustainedMinutes = s.mold_sustained_minutes ?? 30;
      this._moldNotificationCooldown = s.mold_notification_cooldown ?? 60;
      this._moldNotificationsEnabled = s.mold_notifications_enabled ?? true;
      this._moldNotificationTargets = s.mold_notification_targets ?? [];
      this._moldPreventionEnabled = s.mold_prevention_enabled ?? false;
      this._moldPreventionSustainedMinutes = s.mold_prevention_sustained_minutes ?? 60;
      this._moldPreventionIntensity = s.mold_prevention_intensity ?? "medium";
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
      this._budgetEnabled = s.power_budget_enabled ?? false;
      this._powerSensor = s.power_sensor ?? "";
      if (!this._powerModeDirty) {
        this._powerMode = normalizePowerSensorMode(s.power_sensor_mode);
      }
      this._maxPower = s.power_budget_max_watts ?? 3300;
      this._reserve = s.power_budget_reserve_watts ?? 200;
      this._energyPricePerKwh = s.energy_price_per_kwh ?? 0;
    } catch (err) {
      // eslint-disable-next-line no-console
      console.debug("[RoomMind] loadSettings:", err);
    } finally {
      this._loaded = true;
    }
  }

  protected render() {
    if (!this._loaded) {
      return html`<div class="loading">${localize("panel.loading", this.hass.language)}</div>`;
    }

    const l = this.hass.language;
    const categories = [
      { id: "overview", icon: "mdi:view-dashboard-outline", count: 4 },
      { id: "system", icon: "mdi:hvac", count: 4 },
      { id: "protection", icon: "mdi:shield-check-outline", count: 3 },
      { id: "advanced", icon: "mdi:tune-vertical", count: 2 },
    ] as const;

    return html`
      <div class="settings-intro">
        <div class="eyebrow">ROOMMIND / ${localize("settings.hub.eyebrow", l)}</div>
        <h1>${localize("settings.hub.title", l)}</h1>
        <p>${localize("settings.hub.description", l)}</p>
        <div class="control-status ${this._climateControlActive ? "running" : "paused"}">
          <span class="status-dot"></span>
          ${this._climateControlActive
            ? localize("settings.hub.running", l)
            : localize("settings.hub.paused", l)}
        </div>
      </div>
      <div class="settings-workspace">
        <nav class="settings-navigation" aria-label=${localize("settings.hub.navigation", l)}>
          ${categories.map(
            (category) => html`
              <button
                class="category-button ${this._category === category.id ? "selected" : ""}"
                type="button"
                aria-current=${this._category === category.id ? "page" : "false"}
                @click=${() => { this._category = category.id; }}
              >
                <ha-icon icon=${category.icon}></ha-icon>
                <span class="category-copy">
                  <strong>${localize(`settings.hub.${category.id}`, l)}</strong>
                  <small>${localize(`settings.hub.${category.id}_hint`, l)}</small>
                </span>
                <span class="category-count">${category.count}</span>
              </button>
            `,
          )}
        </nav>
        <div class="settings-body">
          <div class="category-heading">
            <div class="eyebrow">${localize("settings.hub.category_label", l)}</div>
            <h2>${localize(`settings.hub.${this._category}`, l)}</h2>
            <p>${localize(`settings.hub.${this._category}_hint`, l)}</p>
          </div>
      <rs-settings-panel
        ?hidden=${this._category !== "system"}
        icon="mdi:home-thermometer"
        .heading=${localize("settings.hub.heating", l)}
        .intro=${localize("settings.hub.heating_hint", l)}
        ><rs-settings-heating-system
          .hass=${this.hass}
          .boilerEntity=${this._boilerEntity}
          .boilerControlType=${this._boilerControlType}
          .bypassEntities=${this._bypassEntities}
          .startupDelay=${this._startupDelay}
          .shutdownDelay=${this._shutdownDelay}
          .bypassTemperature=${this._bypassTemperature}
          .budgetEnabled=${this._budgetEnabled}
          .powerSensor=${this._powerSensor}
          .powerMode=${this._powerMode}
          .maxPower=${this._maxPower}
          .reserve=${this._reserve}
          .energyPricePerKwh=${this._energyPricePerKwh}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-heating-system>
      </rs-settings-panel>

      <rs-settings-panel
        ?hidden=${this._category !== "protection"}
        icon="mdi:shield-search"
        .heading=${localize("preview.title", l)}
        .intro=${localize("preview.intro", l)}
      >
        <rs-settings-preview .hass=${this.hass}></rs-settings-preview>
      </rs-settings-panel>

      <rs-settings-panel
        ?hidden=${this._category !== "overview"}
        icon="mdi:power"
        .heading=${localize("settings.general_title", l)}
        .intro=${localize("settings.intro.general", l)}
      >
        <rs-settings-general
          .hass=${this.hass}
          .groupByFloor=${this._groupByFloor}
          .climateControlActive=${this._climateControlActive}
          .temperatureRoundingMode=${this._temperatureRoundingMode}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-general>
      </rs-settings-panel>

      <rs-settings-panel
        ?hidden=${this._category !== "system"}
        icon="mdi:thermometer"
        .heading=${localize("settings.sensors_title", l)}
        .intro=${localize("settings.intro.sensors", l)}
      >
        <rs-settings-sensors
          .hass=${this.hass}
          .outdoorTempSensor=${this._outdoorTempSensor}
          .outdoorHumiditySensor=${this._outdoorHumiditySensor}
          .weatherEntity=${this._weatherEntity}
          .outdoorUnavailableNotify=${this._outdoorUnavailableNotify}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-sensors>
      </rs-settings-panel>

      <rs-settings-panel
        ?hidden=${this._category !== "overview"}
        icon="mdi:tune-variant"
        .heading=${localize("settings.control_title", l)}
        .intro=${localize("settings.intro.control", l)}
      >
        <rs-settings-control
          .hass=${this.hass}
          .controlMode=${this._controlMode}
          .comfortWeight=${this._comfortWeight}
          .outdoorCoolingMin=${this._outdoorCoolingMin}
          .outdoorHeatingMax=${this._outdoorHeatingMax}
          .predictionEnabled=${this._predictionEnabled}
          .scheduleOffAction=${this._scheduleOffAction}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-control>
      </rs-settings-panel>

      <rs-settings-panel
        ?hidden=${this._category !== "overview"}
        icon="mdi:home-account"
        .heading=${localize("presence.title", l)}
        .intro=${localize("settings.intro.presence", l)}
      >
        <rs-settings-presence
          .hass=${this.hass}
          .presenceEnabled=${this._presenceEnabled}
          .presencePersons=${this._presencePersons}
          .presenceAwayAction=${this._presenceAwayAction}
          .presenceClearsOverride=${this._presenceClearsOverride}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-presence>
      </rs-settings-panel>

      <rs-settings-panel
        ?hidden=${this._category !== "overview"}
        icon="mdi:airplane"
        .heading=${localize("vacation.title", l)}
        .intro=${localize("settings.intro.vacation", l)}
      >
        <rs-settings-vacation
          .hass=${this.hass}
          .vacationActive=${this._vacationActive}
          .vacationTemp=${this._vacationTemp}
          .vacationUntil=${this._vacationUntil}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-vacation>
      </rs-settings-panel>

      <rs-settings-panel
        ?hidden=${this._category !== "system"}
        icon="mdi:shield-refresh"
        .heading=${localize("valve_protection.title", l)}
        .intro=${localize("settings.intro.valve", l)}
      >
        <rs-settings-valve
          .hass=${this.hass}
          .valveProtectionEnabled=${this._valveProtectionEnabled}
          .valveProtectionInterval=${this._valveProtectionInterval}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-valve>
      </rs-settings-panel>

      <rs-settings-panel
        ?hidden=${this._category !== "system"}
        icon="mdi:heat-pump-outline"
        .heading=${localize("compressor.title", l)}
        .intro=${localize("settings.intro.compressor", l)}
      >
        <rs-settings-compressor
          .hass=${this.hass}
          .compressorGroups=${this._compressorGroups}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-compressor>
      </rs-settings-panel>

      <rs-settings-panel
        ?hidden=${this._category !== "protection"}
        icon="mdi:water-alert"
        .heading=${localize("mold.title", l)}
        .intro=${localize("settings.intro.mold", l)}
      >
        <rs-settings-mold
          .hass=${this.hass}
          .moldDetectionEnabled=${this._moldDetectionEnabled}
          .moldHumidityThreshold=${this._moldHumidityThreshold}
          .moldSustainedMinutes=${this._moldSustainedMinutes}
          .moldPreventionEnabled=${this._moldPreventionEnabled}
          .moldPreventionSustainedMinutes=${this._moldPreventionSustainedMinutes}
          .moldPreventionIntensity=${this._moldPreventionIntensity}
          .moldPreventionDehumidificationEnabled=${this._moldPreventionDehumidificationEnabled}
          .moldPreventionDryMinTemperature=${this._moldPreventionDryMinTemperature}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-mold>
      </rs-settings-panel>

      <rs-settings-panel
        ?hidden=${this._category !== "protection"}
        icon="mdi:bell-outline"
        .heading=${localize("notifications.title", l)}
        .intro=${localize("settings.intro.notifications", l)}
        .badge=${localize("badge.beta", l)}
        .badgeHint=${localize("badge.beta_hint", l)}
      >
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
      </rs-settings-panel>

      <rs-settings-panel
        ?hidden=${this._category !== "advanced"}
        icon="mdi:brain"
        .heading=${localize("settings.learning_title", l)}
        .intro=${localize("settings.intro.learning", l)}
      >
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
      </rs-settings-panel>

      <rs-settings-panel
        ?hidden=${this._category !== "advanced"}
        icon="mdi:restart"
        .heading=${localize("settings.reset_title", l)}
        .intro=${localize("settings.intro.reset", l)}
      >
        <rs-settings-reset .hass=${this.hass} .rooms=${this.rooms}></rs-settings-reset>
      </rs-settings-panel>
        </div>
      </div>
    `;
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
    this._saveDebounce = setTimeout(() => this._doSave(), 500);
  }

  private async _doSave() {
    fireSaveStatus(this, "saving");

    try {
      // This is the final untrusted UI boundary. Do not rely on picker event
      // shapes here: Home Assistant components differ across releases.
      const rawBypass = this._bypassEntities;
      const rawPowerSensorMode = this._powerMode;
      const { hydraulicBypassEntities, powerSensorMode } = normalizeHeatingSettingsForWebsocket(
        rawBypass,
        rawPowerSensorMode,
      );
      const payload = {
        type: "roommind/settings/save",
        group_by_floor: this._groupByFloor,
        climate_control_active: this._climateControlActive,
        temperature_rounding_mode: this._temperatureRoundingMode,
        learning_disabled_rooms: this._learningDisabledRooms,
        outdoor_temp_sensor: this._outdoorTempSensor,
        outdoor_humidity_sensor: this._outdoorHumiditySensor,
        outdoor_cooling_min: this._outdoorCoolingMin,
        outdoor_heating_max: this._outdoorHeatingMax,
        control_mode: this._controlMode,
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
        valve_protection_interval_days: this._valveProtectionInterval,
        compressor_groups: this._compressorGroups.filter((g) => g.members.length > 0),
        boiler_entity: this._boilerEntity,
        boiler_control_type: this._boilerControlType,
        boiler_startup_delay_seconds: this._startupDelay,
        boiler_shutdown_delay_seconds: this._shutdownDelay,
        hydraulic_bypass_entities: hydraulicBypassEntities,
        hydraulic_bypass_open_temperature: this._bypassTemperature,
        power_budget_enabled: this._budgetEnabled,
        power_sensor: this._powerSensor,
        power_sensor_mode: powerSensorMode,
        power_budget_max_watts: this._maxPower,
        power_budget_reserve_watts: this._reserve,
        power_budget_unavailable_behavior: "boiler",
        energy_price_per_kwh: this._energyPricePerKwh,
        mold_detection_enabled: this._moldDetectionEnabled,
        mold_humidity_threshold: this._moldHumidityThreshold,
        mold_sustained_minutes: this._moldSustainedMinutes,
        mold_notification_cooldown: this._moldNotificationCooldown,
        mold_notifications_enabled: this._moldNotificationsEnabled,
        mold_notification_targets: this._moldNotificationTargets.filter((t) => t.entity_id),
        mold_prevention_enabled: this._moldPreventionEnabled,
        mold_prevention_sustained_minutes: this._moldPreventionSustainedMinutes,
        mold_prevention_intensity: this._moldPreventionIntensity,
        mold_prevention_dehumidification_enabled: this._moldPreventionDehumidificationEnabled,
        mold_prevention_dry_min_temperature: this._moldPreventionDryMinTemperature,
        mold_prevention_notify_enabled: this._moldPreventionNotify,
        mold_prevention_notify_targets: this._moldPreventionNotify
          ? this._moldNotificationTargets.filter((t) => t.entity_id)
          : [],
        window_open_notification_minutes: this._windowOpenNotificationMinutes,
      };
      // eslint-disable-next-line no-console
      console.debug("RoomMind heating settings save payload", payload);
      // eslint-disable-next-line no-console
      console.debug(
        "RoomMind heating settings save values",
        typeof payload.hydraulic_bypass_entities,
        payload.hydraulic_bypass_entities,
        payload.power_sensor_mode,
      );
      // eslint-disable-next-line no-console
      console.error("[RoomMind DEBUG FINAL PAYLOAD]", {
        hydraulic_bypass_entities: payload.hydraulic_bypass_entities,
        bypassIsArray: Array.isArray(payload.hydraulic_bypass_entities),
        power_sensor_mode: payload.power_sensor_mode,
        fullPayload: payload,
      });
      await this.hass.callWS(payload);
      if (this._powerMode === powerSensorMode) {
        this._powerModeDirty = false;
      }
      fireSaveStatus(this, "saved");
    } catch {
      fireSaveStatus(this, "error");
    }
  }

  static styles = css`
    :host {
      display: block;
      --rs-ui-line: var(--divider-color, rgba(125, 125, 125, .16));
    }
    .settings-intro { padding: 12px 2px 30px; position: relative; }
    .eyebrow { color: var(--secondary-text-color); text-transform: uppercase; font-size: 11px; letter-spacing: .13em; font-weight: 700; }
    .settings-intro h1 { font-size: clamp(27px, 3vw, 38px); line-height: 1.15; letter-spacing: -.035em; margin: 10px 0 10px; font-weight: 700; }
    .settings-intro p, .category-heading p { color: var(--secondary-text-color); font-size: 14px; line-height: 1.65; max-width: 620px; margin: 0; }
    .control-status { display: inline-flex; gap: 8px; align-items: center; margin-top: 17px; padding: 8px 12px; border-radius: 999px; font-size: 12px; font-weight: 650; background: var(--secondary-background-color, rgba(128,128,128,.1)); }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--secondary-text-color); }
    .running .status-dot { background: var(--success-color, #36a578); }
    .settings-workspace { display: grid; grid-template-columns: 250px minmax(0, 1fr); gap: 34px; align-items: start; }
    .settings-navigation { display: grid; gap: 6px; position: sticky; top: 132px; }
    .category-button { display: flex; align-items: center; gap: 12px; text-align: left; border: 1px solid transparent; border-radius: 14px; padding: 12px 14px; font: inherit; color: var(--secondary-text-color); background: transparent; cursor: pointer; min-height: 64px; transition: background .18s ease, border-color .18s ease; }
    .category-button:hover { background: var(--secondary-background-color, rgba(128,128,128,.08)); }
    .category-button.selected { color: var(--primary-text-color); border-color: var(--rs-ui-line); background: var(--card-background-color); box-shadow: 0 3px 18px rgba(0,0,0,.04); }
    .category-button ha-icon { --mdc-icon-size: 21px; flex-shrink: 0; }
    .category-button.selected ha-icon { color: var(--primary-color); }
    .category-copy { display: grid; gap: 4px; min-width: 0; flex: 1; }
    .category-copy strong { font-size: 14px; font-weight: 650; }
    .category-copy small { font-size: 11px; opacity: .75; line-height: 1.3; }
    .category-count { font-size: 11px; opacity: .55; font-variant-numeric: tabular-nums; }
    .category-button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
    .settings-body { display: grid; gap: 12px; min-width: 0; }
    .category-heading { padding: 5px 0 13px; }
    .category-heading h2 { font-size: 23px; font-weight: 650; letter-spacing: -.025em; margin: 8px 0 6px; }
    rs-settings-panel[hidden] { display: none !important; }
    @media (max-width: 850px) {
      .settings-workspace { display: block; }
      .settings-navigation { display: flex; overflow-x: auto; gap: 8px; position: relative; top: auto; padding: 0 0 14px; margin-bottom: 20px; scrollbar-width: thin; }
      .category-button { flex: 0 0 auto; min-height: 48px; padding: 10px 13px; white-space: nowrap; }
      .category-copy small, .category-count { display: none; }
      .category-copy { display: block; }
      .settings-intro { padding-bottom: 22px; }
    }
    @media (max-width: 500px) {
      .settings-intro h1 { font-size: 28px; }
      .category-button ha-icon { --mdc-icon-size: 18px; }
      .category-heading h2 { font-size: 21px; }
    }

    .loading {
      padding: 80px 16px;
      text-align: center;
      color: var(--secondary-text-color);
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings": RsSettings;
  }
}
