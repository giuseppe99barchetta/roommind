/**
 * RoomMind room card for Lovelace dashboards (#346, contained port).
 *
 * Shows one room (temperature, state, target, override) and offers the panel's quick
 * actions: climate mode, the room's climate control switch and a temporary override.
 * It must not import panel components: the panel bundle defines them as well.
 */
import { LitElement, html, css, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { ClimateMode, HomeAssistant, OverrideType, RoomConfig } from "../types";
import { localize, type TranslationKey } from "../utils/localize";
import { formatMode, getModeClass } from "../utils/room-state";
import { formatTemp, tempUnit, toCelsius, toDisplay } from "../utils/temperature";
import { serverNow } from "../utils/server-clock";
import { refreshRooms, setFeedHass, subscribeRooms, type RoomsFeed } from "./rooms-feed";
import { errorText, overrideMessage, remainingText, roomName } from "./helpers";

export interface RoomCardConfig {
  type: string;
  area_id?: string;
  name?: string;
}

const CLIMATE_MODES: ClimateMode[] = ["auto", "heat_only", "cool_only"];
const OVERRIDES: OverrideType[] = ["boost", "eco", "custom"];
const DURATIONS_H = [1, 2, 4];
const OVERRIDE_KEYS: Record<OverrideType, TranslationKey> = {
  boost: "override.comfort",
  eco: "override.eco",
  custom: "override.custom",
};
const OVERRIDE_ICONS: Record<OverrideType, string> = {
  boost: "mdi:fire",
  eco: "mdi:leaf",
  custom: "mdi:thermometer",
};

@customElement("roommind-room-card")
export class RoomMindRoomCard extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @state() private _config: RoomCardConfig = { type: "custom:roommind-room-card" };
  @state() private _feed: RoomsFeed | null = null;
  @state() private _feedError = "";
  @state() private _error = "";
  @state() private _busy = false;
  @state() private _pending: OverrideType | null = null;
  @state() private _customTemp = 21;
  @state() private _now = serverNow();
  private _unsub?: () => void;
  private _tick?: ReturnType<typeof setInterval>;

  public static getConfigElement(): HTMLElement {
    return document.createElement("roommind-room-card-editor");
  }

  public static getStubConfig(): RoomCardConfig {
    return { type: "custom:roommind-room-card", area_id: "" };
  }

  public setConfig(config: RoomCardConfig): void {
    if (!config) throw new Error("Invalid configuration");
    this._config = config;
    this._pending = null;
    this._error = "";
  }

  public getCardSize(): number {
    return 4;
  }

  connectedCallback(): void {
    super.connectedCallback();
    this._unsub = subscribeRooms((feed, error) => {
      this._feed = feed;
      this._feedError = error;
    });
    this._tick = setInterval(() => (this._now = serverNow()), 30_000);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this._unsub?.();
    this._unsub = undefined;
    if (this._tick) clearInterval(this._tick);
  }

  protected willUpdate(changed: PropertyValues): void {
    if (changed.has("hass") && this.hass) setFeedHass(this.hass);
  }

  private get _lang(): string {
    return this.hass?.language ?? "en";
  }

  private get _room(): RoomConfig | undefined {
    const id = this._config.area_id;
    return id ? this._feed?.rooms[id] : undefined;
  }

  private async _call(msg: Record<string, unknown>, fallback: TranslationKey): Promise<boolean> {
    this._busy = true;
    this._error = "";
    try {
      await this.hass.callWS(msg);
      await refreshRooms(true);
      return true;
    } catch (err) {
      this._error = errorText(err, localize(fallback, this._lang));
      return false;
    } finally {
      this._busy = false;
    }
  }

  private _setMode(mode: ClimateMode): void {
    if (this._room?.climate_mode === mode) return;
    void this._call(
      {
        type: "roommind/rooms/save",
        area_id: this._config.area_id,
        update_only: true,
        climate_mode: mode,
      },
      "roomcard.error_save",
    );
  }

  private _toggleControl(): void {
    const enabled = this._room?.climate_control_enabled !== false;
    void this._call(
      {
        type: "roommind/rooms/save",
        area_id: this._config.area_id,
        update_only: true,
        climate_control_enabled: !enabled,
      },
      "roomcard.error_save",
    );
  }

  private _pickOverride(type: OverrideType): void {
    if (this._pending === type) {
      this._pending = null;
      return;
    }
    this._pending = type;
    this._error = "";
    if (type === "custom") {
      const room = this._room;
      const live = room?.live;
      const coolOnly = room?.climate_mode === "cool_only";
      const c = (coolOnly ? live?.cool_target : live?.heat_target) ?? live?.target_temp ?? 21;
      this._customTemp = toDisplay(c, this.hass);
    }
  }

  private _stepCustom(delta: number): void {
    this._customTemp = Math.round((this._customTemp + delta) * 10) / 10;
  }

  private async _activate(hours: number): Promise<void> {
    if (!this._pending || !this._config.area_id) return;
    const msg = overrideMessage(
      this._config.area_id,
      this._room,
      this._pending,
      hours,
      toCelsius(this._customTemp, this.hass),
    );
    if (!msg) {
      this._error = localize("override.invalid_band", this._lang);
      return;
    }
    if (await this._call(msg, "override.error_set")) this._pending = null;
  }

  private _clearOverride(): void {
    void this._call(
      { type: "roommind/override/clear", area_id: this._config.area_id },
      "override.error_clear",
    );
  }

  private _targetText(room: RoomConfig): string {
    const live = room.live;
    const unit = tempUnit(this.hass);
    if (!live) return "--";
    const heat = live.heat_target;
    const cool = live.cool_target;
    if (heat != null && cool != null && room.climate_mode === "auto") {
      return `${formatTemp(heat, this.hass)} – ${formatTemp(cool, this.hass)}${unit}`;
    }
    const single = room.climate_mode === "cool_only" ? (cool ?? live.target_temp) : (heat ?? live.target_temp);
    return single != null ? `${formatTemp(single, this.hass)}${unit}` : "--";
  }

  protected render() {
    const l = this._lang;
    if (!this._config.area_id) {
      return html`<ha-card><div class="msg">${localize("roomcard.select_room", l)}</div></ha-card>`;
    }
    const room = this._room;
    if (!room) {
      const text = this._feedError
        ? this._feedError
        : this._feed
          ? localize("roomcard.room_not_found", l)
          : localize("hero.waiting", l);
      return html`<ha-card><div class="msg">${text}</div></ha-card>`;
    }
    const live = room.live;
    const name = this._config.name || roomName(room, this.hass, room.area_id);
    const mode = live?.mode ?? "idle";
    const controlOn = room.climate_control_enabled !== false;
    const ovActive = !!live?.override_active;
    const ovType = (live?.override_type ?? null) as OverrideType | null;
    const until = live?.override_until ?? null;
    const remaining = until ? remainingText(until, this._now) : "";
    return html`
      <ha-card>
        <div class="header">
          <div class="name">${name}</div>
          <div class="state ${getModeClass(mode)}">${formatMode(mode, l)}</div>
        </div>
        <div class="readings">
          <span class="temp"
            >${live?.current_temp != null
              ? `${formatTemp(live.current_temp, this.hass)}${tempUnit(this.hass)}`
              : "--"}</span
          >
          ${live?.current_humidity != null
            ? html`<span class="hum"
                >${localize("hero.humidity", l, { value: Math.round(live.current_humidity) })}</span
              >`
            : nothing}
        </div>
        <div class="target">
          ${ovActive && ovType ? localize(OVERRIDE_KEYS[ovType], l) + " · " : ""}${localize(
            "hero.target",
            l,
          )}:
          <strong>${this._targetText(room)}</strong>
          ${ovActive
            ? html`<span class="remaining"
                >${remaining
                  ? localize("hero.remaining", l, { time: remaining })
                  : localize("hero.permanent", l)}</span
              >`
            : nothing}
        </div>
        ${room.is_outdoor ? nothing : this._renderControls(room, controlOn, ovActive, ovType)}
        ${this._error ? html`<div class="error">${this._error}</div>` : nothing}
      </ha-card>
    `;
  }

  private _renderControls(
    room: RoomConfig,
    controlOn: boolean,
    ovActive: boolean,
    ovType: OverrideType | null,
  ) {
    const l = this._lang;
    return html`
      <div class="row">
        ${CLIMATE_MODES.map(
          (m) => html`
            <button
              class="chip ${room.climate_mode === m ? "on" : ""}"
              ?disabled=${this._busy}
              @click=${() => this._setMode(m)}
            >
              ${localize(`mode.${m}` as TranslationKey, l)}
            </button>
          `,
        )}
        <button
          class="chip control ${controlOn ? "on" : ""}"
          ?disabled=${this._busy}
          title=${localize("room.climate_control_toggle", l)}
          @click=${() => this._toggleControl()}
        >
          <ha-icon icon=${controlOn ? "mdi:power" : "mdi:power-off"}></ha-icon>
        </button>
      </div>
      <div class="row">
        ${OVERRIDES.map((t) => {
          const active = ovActive && ovType === t;
          return html`
            <button
              class="chip ${active || this._pending === t ? "on" : ""}"
              ?disabled=${this._busy || (ovActive && !active)}
              @click=${() => (active ? this._clearOverride() : this._pickOverride(t))}
            >
              <ha-icon icon=${OVERRIDE_ICONS[t]}></ha-icon>${localize(OVERRIDE_KEYS[t], l)}
            </button>
          `;
        })}
        ${ovActive
          ? html`<button class="chip" ?disabled=${this._busy} @click=${() => this._clearOverride()}>
              ${localize("roomcard.clear", l)}
            </button>`
          : nothing}
      </div>
      ${this._pending && !ovActive
        ? html`
            ${this._pending === "custom"
              ? html`<div class="row custom">
                  <button class="chip" @click=${() => this._stepCustom(-0.5)}>−</button>
                  <span class="custom-temp">${this._customTemp.toFixed(1)}${tempUnit(this.hass)}</span>
                  <button class="chip" @click=${() => this._stepCustom(0.5)}>+</button>
                </div>`
              : nothing}
            <div class="row">
              <span class="label">${localize("override.activate_for", l)}</span>
              ${DURATIONS_H.map(
                (h) => html`<button
                  class="chip"
                  ?disabled=${this._busy}
                  @click=${() => this._activate(h)}
                >
                  ${h}h
                </button>`,
              )}
            </div>
          `
        : nothing}
    `;
  }

  static styles = css`
    ha-card {
      padding: 16px;
    }
    .msg {
      color: var(--secondary-text-color);
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
    }
    .name {
      font-size: 1.2em;
      font-weight: 500;
    }
    .state {
      font-size: 0.85em;
      padding: 2px 10px;
      border-radius: 12px;
      background: var(--secondary-background-color);
    }
    .state.mode-heating {
      color: var(--state-climate-heat-color, #ff8100);
    }
    .state.mode-cooling {
      color: var(--state-climate-cool-color, #2b9af9);
    }
    .readings {
      display: flex;
      align-items: baseline;
      gap: 12px;
      margin: 8px 0 4px;
    }
    .temp {
      font-size: 2em;
    }
    .hum,
    .remaining,
    .label {
      color: var(--secondary-text-color);
      font-size: 0.9em;
    }
    .target {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: baseline;
    }
    .row {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 6px;
      margin-top: 10px;
    }
    .chip {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      border: 1px solid var(--divider-color);
      border-radius: 16px;
      background: none;
      color: var(--primary-text-color);
      padding: 4px 12px;
      font: inherit;
      cursor: pointer;
      --mdc-icon-size: 18px;
    }
    .chip.on {
      background: var(--primary-color);
      border-color: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .chip:disabled {
      opacity: 0.5;
      cursor: default;
    }
    .custom-temp {
      min-width: 4em;
      text-align: center;
      font-weight: 500;
    }
    .error {
      color: var(--error-color);
      margin-top: 8px;
    }
  `;
}

/** Card editor: pick the room and an optional name. */
@customElement("roommind-room-card-editor")
export class RoomMindRoomCardEditor extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @state() private _config: RoomCardConfig = { type: "custom:roommind-room-card" };
  @state() private _feed: RoomsFeed | null = null;
  private _unsub?: () => void;

  public setConfig(config: RoomCardConfig): void {
    this._config = config;
  }

  connectedCallback(): void {
    super.connectedCallback();
    this._unsub = subscribeRooms((feed) => (this._feed = feed));
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this._unsub?.();
  }

  protected willUpdate(changed: PropertyValues): void {
    if (changed.has("hass") && this.hass) setFeedHass(this.hass);
  }

  private _changed(patch: Partial<RoomCardConfig>): void {
    const config = { ...this._config, ...patch };
    if (!config.name) delete config.name;
    this._config = config;
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
  }

  protected render() {
    const l = this.hass?.language ?? "en";
    const rooms = Object.values(this._feed?.rooms ?? {})
      .map((r) => ({ id: r.area_id, name: roomName(r, this.hass, r.area_id) }))
      .sort((a, b) => a.name.localeCompare(b.name));
    return html`
      <label>
        ${localize("roomcard.editor_room", l)}
        <select
          .value=${this._config.area_id ?? ""}
          @change=${(e: Event) => this._changed({ area_id: (e.target as HTMLSelectElement).value })}
        >
          <option value="">—</option>
          ${rooms.map(
            (r) =>
              html`<option value=${r.id} ?selected=${r.id === this._config.area_id}>${r.name}</option>`,
          )}
        </select>
      </label>
      <label>
        ${localize("roomcard.editor_name", l)}
        <input
          .value=${this._config.name ?? ""}
          @change=${(e: Event) => this._changed({ name: (e.target as HTMLInputElement).value })}
        />
      </label>
    `;
  }

  static styles = css`
    label {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin-bottom: 12px;
    }
    select,
    input {
      font: inherit;
      padding: 6px;
    }
  `;
}
