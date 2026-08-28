from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"anchor not found in {path}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# ---------------------------------------------------------------------------
# Energy manager: retain per-device measured power and train per-device models.
# ---------------------------------------------------------------------------
p = ROOT / "custom_components/roommind/managers/energy_manager.py"
text = p.read_text(encoding="utf-8")
text = text.replace(
    "    models: dict[str, _LinearStats] = field(default_factory=dict)\n",
    "    models: dict[str, _LinearStats] = field(default_factory=dict)\n    device_models: dict[str, dict[str, _LinearStats]] = field(default_factory=dict)\n",
    1,
)
old = '''    def read_power_w(self, room: dict) -> tuple[float, int]:\n        total = 0.0\n        configured = 0\n        for dev in room.get("devices", []):\n            if dev.get("type") != "ac":\n                continue\n            power_eid = dev.get("power_sensor_entity_id")\n            if not power_eid:\n                continue\n            configured += 1\n            state = self.hass.states.get(power_eid)\n            if state is None or state.state in ("unknown", "unavailable", ""):\n                continue\n            value = self._safe_float(state.state)\n            if value is None:\n                continue\n            unit = str(state.attributes.get("unit_of_measurement", "W")).lower()\n            if unit == "kw":\n                value *= 1000.0\n            elif unit == "mw":\n                value /= 1000.0\n            total += max(0.0, value)\n        return min(total, _MAX_REASONABLE_POWER_W), configured\n'''
new = '''    def read_power_breakdown(self, room: dict) -> tuple[float, int, dict[str, float]]:\n        """Read aggregate and per-AC instantaneous power in watts."""\n        total = 0.0\n        configured = 0\n        breakdown: dict[str, float] = {}\n        for dev in room.get("devices", []):\n            if dev.get("type") != "ac":\n                continue\n            power_eid = dev.get("power_sensor_entity_id")\n            if not power_eid:\n                continue\n            configured += 1\n            state = self.hass.states.get(power_eid)\n            if state is None or state.state in ("unknown", "unavailable", ""):\n                continue\n            value = self._safe_float(state.state)\n            if value is None:\n                continue\n            unit = str(state.attributes.get("unit_of_measurement", "W")).lower()\n            if unit == "kw":\n                value *= 1000.0\n            elif unit == "mw":\n                value /= 1000.0\n            value = min(max(0.0, value), _MAX_REASONABLE_POWER_W)\n            entity_id = str(dev.get("entity_id") or power_eid)\n            breakdown[entity_id] = round(value, 1)\n            total += value\n        return min(total, _MAX_REASONABLE_POWER_W), configured, breakdown\n\n    def read_power_w(self, room: dict) -> tuple[float, int]:\n        total, configured, _ = self.read_power_breakdown(room)\n        return total, configured\n\n    @staticmethod\n    def _predict_stats(model: _LinearStats | None, features: list[float]) -> tuple[float | None, int]:\n        if model is None:\n            return None, 0\n        coeff = model.coefficients()\n        if coeff is None:\n            return None, model.n\n        prediction = sum(coeff[i] * features[i] for i in range(4))\n        ceiling = max(model.observed_max_w * 1.35, 250.0)\n        return max(0.0, min(prediction, ceiling, _MAX_REASONABLE_POWER_W)), model.n\n\n    def predict_power(\n        self,\n        area_id: str,\n        mode: str,\n        room_temp: float | None,\n        target_temp: float | None,\n        outdoor_temp: float | None,\n        humidity: float | None,\n        nominal_w: float | None = None,\n    ) -> tuple[float | None, int]:\n        """Predict aggregate room AC power for analytics and live entities."""\n        state = self._rooms.get(area_id)\n        features = self._features(room_temp, target_temp, outdoor_temp, humidity)\n        prediction, samples = self._predict_stats(state.models.get(mode) if state else None, features)\n        if prediction is None and mode in ("heating", "cooling", "dry") and nominal_w and nominal_w > 0:\n            prediction = min(float(nominal_w), _MAX_REASONABLE_POWER_W)\n        return prediction, samples\n\n    def predict_device_power(\n        self,\n        area_id: str,\n        mode: str,\n        room_temp: float | None,\n        target_temp: float | None,\n        outdoor_temp: float | None,\n        humidity: float | None,\n    ) -> dict[str, float]:\n        """Predict each configured AC from its own learned consumption model."""\n        state = self._rooms.get(area_id)\n        if state is None:\n            return {}\n        features = self._features(room_temp, target_temp, outdoor_temp, humidity)\n        result: dict[str, float] = {}\n        for entity_id, models in state.device_models.items():\n            prediction, _ = self._predict_stats(models.get(mode), features)\n            if prediction is not None:\n                result[entity_id] = round(prediction, 1)\n        return result\n'''
if old not in text:
    raise SystemExit("energy read_power anchor missing")
text = text.replace(old, new, 1)
text = text.replace(
    '''            if power >= _MIN_ACTIVE_POWER_W and mode in ("heating", "cooling", "dry"):\n                model = state.models.setdefault(mode, _LinearStats())\n                model.add(self._features(room_temp, target, outdoor, humidity), power)\n''',
    '''            features = self._features(room_temp, target, outdoor, humidity)\n            if power >= _MIN_ACTIVE_POWER_W and mode in ("heating", "cooling", "dry"):\n                model = state.models.setdefault(mode, _LinearStats())\n                model.add(features, power)\n            device_power = row.get("ac_device_power_w")\n            if isinstance(device_power, dict) and mode in ("heating", "cooling", "dry"):\n                for entity_id, raw_power in device_power.items():\n                    device_w = self._safe_float(raw_power)\n                    if device_w is not None and device_w >= _MIN_ACTIVE_POWER_W:\n                        state.device_models.setdefault(str(entity_id), {}).setdefault(mode, _LinearStats()).add(\n                            features, device_w\n                        )\n''',
    1,
)
text = text.replace(
    "        power_w, configured = self.read_power_w(room)\n",
    "        power_w, configured, device_power = self.read_power_breakdown(room)\n",
    1,
)
text = text.replace(
    '''        if power_w >= _MIN_ACTIVE_POWER_W and mode in ("heating", "cooling", "dry"):\n            state.models.setdefault(mode, _LinearStats()).add(features, power_w)\n\n        prediction: float | None = None\n        samples = 0\n        model = state.models.get(mode)\n        if model is not None:\n            samples = model.n\n            coeff = model.coefficients()\n            if coeff is not None:\n                prediction = sum(coeff[i] * features[i] for i in range(4))\n                ceiling = max(model.observed_max_w * 1.35, 250.0)\n                prediction = max(0.0, min(prediction, ceiling, _MAX_REASONABLE_POWER_W))\n        if prediction is None and mode in ("heating", "cooling", "dry"):\n            nominal = self._safe_float(room.get("heat_pump_power_watts"))\n            if nominal and nominal > 0:\n                prediction = nominal\n''',
    '''        if power_w >= _MIN_ACTIVE_POWER_W and mode in ("heating", "cooling", "dry"):\n            state.models.setdefault(mode, _LinearStats()).add(features, power_w)\n        if mode in ("heating", "cooling", "dry"):\n            for entity_id, measured_w in device_power.items():\n                if measured_w >= _MIN_ACTIVE_POWER_W:\n                    state.device_models.setdefault(entity_id, {}).setdefault(mode, _LinearStats()).add(\n                        features, measured_w\n                    )\n\n        nominal = self._safe_float(room.get("heat_pump_power_watts"))\n        prediction, samples = self.predict_power(\n            area_id, mode, room_temp, target, outdoor_temp, humidity, nominal\n        )\n        predicted_devices = self.predict_device_power(\n            area_id, mode, room_temp, target, outdoor_temp, humidity\n        )\n''',
    1,
)
text = text.replace(
    '''            "ac_power_w": round(power_w, 1) if configured else None,\n            "ac_power_sensors": configured,\n''',
    '''            "ac_power_w": round(power_w, 1) if configured else None,\n            "ac_device_power_w": device_power if configured else {},\n            "ac_power_sensors": configured,\n''',
    1,
)
text = text.replace(
    '''            "predicted_power_w": round(prediction, 1) if prediction is not None else None,\n            "predicted_energy_1h_kwh": round(prediction / 1000.0, 3) if prediction is not None else None,\n''',
    '''            "predicted_power_w": round(prediction, 1) if prediction is not None else None,\n            "predicted_device_power_w": predicted_devices,\n            "predicted_energy_1h_kwh": round(prediction / 1000.0, 3) if prediction is not None else None,\n''',
    1,
)
p.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# History: persist compact JSON maps for per-device power.
# ---------------------------------------------------------------------------
p = ROOT / "custom_components/roommind/utils/history_store.py"
text = p.read_text(encoding="utf-8")
text = text.replace("import csv\n", "import csv\nimport json\n", 1)
text = text.replace(
    '    "ac_power_w",\n',
    '    "ac_power_w",\n    "ac_device_power_w_json",\n',
    1,
)
text = text.replace(
    '    "predicted_power_w",\n',
    '    "predicted_power_w",\n    "predicted_device_power_w_json",\n',
    1,
)
text = text.replace(
    '''                    "ac_power_w": data.get("ac_power_w", ""),\n                    "ac_energy_today_kwh": data.get("ac_energy_today_kwh", ""),\n                    "predicted_power_w": data.get("predicted_power_w", ""),\n''',
    '''                    "ac_power_w": data.get("ac_power_w", ""),\n                    "ac_device_power_w_json": json.dumps(data.get("ac_device_power_w", {}), separators=(",", ":")),\n                    "ac_energy_today_kwh": data.get("ac_energy_today_kwh", ""),\n                    "predicted_power_w": data.get("predicted_power_w", ""),\n                    "predicted_device_power_w_json": json.dumps(\n                        data.get("predicted_device_power_w", {}), separators=(",", ":")\n                    ),\n''',
    1,
)
# Preserve latest JSON maps when downsampling rather than averaging them.
text = text.replace(
    '''                "device_setpoint": bucket[0].get("device_setpoint", ""),\n            }\n''',
    '''                "device_setpoint": bucket[0].get("device_setpoint", ""),\n                "ac_device_power_w_json": bucket[-1].get("ac_device_power_w_json", "{}"),\n                "predicted_device_power_w_json": bucket[-1].get("predicted_device_power_w_json", "{}"),\n            }\n''',
    1,
)
p.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# Analytics API: expose energy history + generate a 3h learned power forecast.
# ---------------------------------------------------------------------------
p = ROOT / "custom_components/roommind/services/analytics_service.py"
text = p.read_text(encoding="utf-8")
text = text.replace("import logging\n", "import json\nimport logging\n", 1)
old = '''def _safe_int(value: str) -> int | None:\n    """Convert CSV string to int, or None for empty/invalid values."""\n    if not value:\n        return None\n    try:\n        return int(float(value))\n    except (ValueError, TypeError):\n        return None\n\n\n'''
new = old + '''def _safe_power_map(value: object) -> dict[str, float]:\n    """Decode compact per-device power maps from history CSV rows."""\n    if isinstance(value, dict):\n        raw = value\n    elif isinstance(value, str) and value:\n        try:\n            parsed = json.loads(value)\n        except (TypeError, ValueError, json.JSONDecodeError):\n            return {}\n        raw = parsed if isinstance(parsed, dict) else {}\n    else:\n        return {}\n    result: dict[str, float] = {}\n    for key, item in raw.items():\n        try:\n            number = float(item)\n        except (TypeError, ValueError):\n            continue\n        if math.isfinite(number) and number >= 0:\n            result[str(key)] = round(number, 1)\n    return result\n\n\n'''
if old not in text:
    raise SystemExit("analytics safe_int anchor missing")
text = text.replace(old, new, 1)
text = text.replace(
    '''                "device_setpoint": _safe_float(row.get("device_setpoint", "")),\n            }\n''',
    '''                "device_setpoint": _safe_float(row.get("device_setpoint", "")),\n                "current_humidity": _safe_float(row.get("current_humidity", "")),\n                "energy_mode": row.get("energy_mode", ""),\n                "ac_power_w": _safe_float(row.get("ac_power_w", "")),\n                "ac_device_power_w": _safe_power_map(row.get("ac_device_power_w_json", "")),\n                "ac_energy_today_kwh": _safe_float(row.get("ac_energy_today_kwh", "")),\n                "predicted_power_w": _safe_float(row.get("predicted_power_w", "")),\n                "predicted_device_power_w": _safe_power_map(\n                    row.get("predicted_device_power_w_json", "")\n                ),\n                "predicted_energy_1h_kwh": _safe_float(row.get("predicted_energy_1h_kwh", "")),\n                "energy_learning_samples": _safe_int(row.get("energy_learning_samples", "")),\n            }\n''',
    1,
)
# Insert forecast energy prediction before merged forecast creation.
anchor = '''    # Merge into unified forecast points on shared 5-min grid\n    forecast: list[dict] = []\n'''
insert = '''    # Use the same future temperature/outdoor trajectory to predict electrical\n    # demand. This keeps the energy chart coupled to RoomMind's learned thermal\n    # forecast instead of extrapolating watts independently.\n    predicted_powers: list[float | None] = []\n    predicted_device_powers: list[dict[str, float]] = []\n    energy_manager = getattr(coordinator, "_energy_manager", None) if coordinator else None\n    if energy_manager and target_forecast:\n        live = coordinator.rooms.get(area_id, {})\n        humidity = _safe_float(str(live.get("current_humidity") or ""))\n        nominal = _safe_float(str(room_config.get("heat_pump_power_watts") or ""))\n        selected_mode = str(room_config.get("room_hvac_mode") or "auto")\n        for i, tf in enumerate(target_forecast):\n            predicted_t = pred_temps[i] if i < len(pred_temps) else None\n            heat_target = tf.get("heat_target")\n            cool_target = tf.get("cool_target")\n            if selected_mode == "dry":\n                energy_mode = "dry"\n                target_for_energy = cool_target or tf.get("target_temp")\n            elif selected_mode == "heat":\n                energy_mode = "heating"\n                target_for_energy = heat_target or tf.get("target_temp")\n            elif selected_mode == "cool":\n                energy_mode = "cooling"\n                target_for_energy = cool_target or tf.get("target_temp")\n            elif selected_mode in ("off", "fan_only"):\n                energy_mode = "idle"\n                target_for_energy = tf.get("target_temp")\n            else:\n                if predicted_t is not None and heat_target is not None and predicted_t < heat_target:\n                    energy_mode = "heating"\n                    target_for_energy = heat_target\n                elif predicted_t is not None and cool_target is not None and predicted_t > cool_target:\n                    energy_mode = "cooling"\n                    target_for_energy = cool_target\n                else:\n                    energy_mode = "idle"\n                    target_for_energy = tf.get("target_temp")\n            outdoor_for_energy = (\n                outdoor_series[i]\n                if "outdoor_series" in locals() and i < len(outdoor_series)\n                else coordinator.outdoor_temp_effective\n            )\n            power, _ = energy_manager.predict_power(\n                area_id,\n                energy_mode,\n                predicted_t,\n                target_for_energy,\n                outdoor_for_energy,\n                humidity,\n                nominal,\n            )\n            predicted_powers.append(round(power, 1) if power is not None else 0.0)\n            predicted_device_powers.append(\n                energy_manager.predict_device_power(\n                    area_id,\n                    energy_mode,\n                    predicted_t,\n                    target_for_energy,\n                    outdoor_for_energy,\n                    humidity,\n                )\n            )\n\n    # Merge into unified forecast points on shared 5-min grid\n    forecast: list[dict] = []\n'''
if anchor not in text:
    raise SystemExit("analytics forecast anchor missing")
text = text.replace(anchor, insert, 1)
text = text.replace(
    '''                "window_open": False,\n                "device_setpoint": None,\n            }\n''',
    '''                "window_open": False,\n                "device_setpoint": None,\n                "predicted_power_w": predicted_powers[i] if i < len(predicted_powers) else None,\n                "predicted_device_power_w": (\n                    predicted_device_powers[i] if i < len(predicted_device_powers) else {}\n                ),\n            }\n''',
    1,
)
p.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# Frontend types.
# ---------------------------------------------------------------------------
p = ROOT / "frontend/src/types/index.ts"
text = p.read_text(encoding="utf-8")
text = text.replace(
    "  ac_power_w?: number | null;\n",
    "  ac_power_w?: number | null;\n  ac_device_power_w?: Record<string, number>;\n",
    1,
)
text = text.replace(
    "  predicted_power_w?: number | null;\n",
    "  predicted_power_w?: number | null;\n  predicted_device_power_w?: Record<string, number>;\n",
    1,
)
# second occurrence in AnalyticsDataPoint
idx = text.find("export interface AnalyticsDataPoint")
head, tail = text[:idx], text[idx:]
tail = tail.replace(
    "  ac_power_w?: number | null;\n",
    "  ac_power_w?: number | null;\n  ac_device_power_w?: Record<string, number>;\n",
    1,
)
tail = tail.replace(
    "  predicted_power_w?: number | null;\n",
    "  predicted_power_w?: number | null;\n  predicted_device_power_w?: Record<string, number>;\n",
    1,
)
p.write_text(head + tail, encoding="utf-8")

# ---------------------------------------------------------------------------
# Energy analytics chart component.
# ---------------------------------------------------------------------------
energy_chart = r'''/** Energy analytics card: measured room/device consumption + learned forecast. */
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
    return typeof friendly === "string" && friendly ? friendly : entityId.split(".").pop()!.replaceAll("_", " ");
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
    const hasEnergy = points.some((p) => p.ac_power_w != null) || forecast.some((p) => p.predicted_power_w != null);
    if (!hasEnergy) return nothing;

    const deviceIds = this._deviceIds(points, forecast);
    const measured = points.filter((p) => p.ac_power_w != null).map((p) => [p.ts * 1000, p.ac_power_w]);
    const predicted = forecast.filter((p) => p.predicted_power_w != null).map((p) => [p.ts * 1000, p.predicted_power_w]);
    const series: Array<Record<string, unknown>> = [
      {
        id: "room_power",
        name: localize("analytics.energy_room_power", this.language),
        type: "line",
        showSymbol: false,
        data: measured,
        color: "var(--primary-color)",
        lineStyle: { width: 2.5 },
      },
      {
        id: "room_power_forecast",
        name: localize("analytics.energy_forecast", this.language),
        type: "line",
        showSymbol: false,
        data: predicted,
        color: "var(--primary-color)",
        lineStyle: { width: 2, type: "dashed" },
      },
    ];
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
        });
      }
    });

    const latest = [...points].reverse().find((p) => p.ac_power_w != null);
    const actualEnergy = this._integrate(points.map((p) => ({ ts: p.ts, value: p.ac_power_w })));
    const forecastEnergy = this._integrate(forecast.map((p) => ({ ts: p.ts, value: p.predicted_power_w })));
    const latestSamples = [...points].reverse().find((p) => p.energy_learning_samples != null)?.energy_learning_samples ?? 0;

    const options = {
      animation: false,
      grid: { left: 55, right: 20, top: 24, bottom: 42 },
      tooltip: { trigger: "axis", valueFormatter: (value: number) => `${Math.round(value)} W` },
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
          <div class="stat"><span>${localize("analytics.energy_now", this.language)}</span><strong>${latest?.ac_power_w != null ? `${Math.round(latest.ac_power_w)} W` : "—"}</strong></div>
          <div class="stat"><span>${localize("analytics.energy_period", this.language)}</span><strong>${actualEnergy.toFixed(2)} kWh</strong></div>
          <div class="stat"><span>${localize("analytics.energy_next_3h", this.language)}</span><strong>${forecastEnergy.toFixed(2)} kWh</strong></div>
          <div class="stat"><span>${localize("analytics.energy_learning", this.language)}</span><strong>${latestSamples}</strong></div>
        </div>
        <ha-chart-base .hass=${this.hass} .data=${series} .options=${options} .height=${"280px"} style="height:280px"></ha-chart-base>
        <div class="legend">
          ${series.map((s) => html`<span><i style="background:${s.color as string}"></i>${s.name as string}</span>`)}
        </div>
      </ha-card>
    `;
  }

  static styles = css`
    :host { display:block; }
    ha-card { margin-bottom:16px; padding-bottom:10px; }
    .header { display:flex; justify-content:space-between; align-items:center; padding:16px 16px 8px; }
    .title { font-size:16px; font-weight:500; }
    .subtitle { font-size:12px; color:var(--secondary-text-color); margin-top:3px; }
    .header ha-icon { color:var(--primary-color); }
    .stats { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; padding:6px 16px 4px; }
    .stat { background:var(--secondary-background-color); border-radius:10px; padding:10px 12px; display:flex; flex-direction:column; gap:3px; }
    .stat span { font-size:11px; color:var(--secondary-text-color); }
    .stat strong { font-size:15px; font-weight:600; }
    .legend { display:flex; justify-content:center; flex-wrap:wrap; gap:8px 14px; padding:2px 16px 8px; font-size:11px; color:var(--secondary-text-color); }
    .legend span { display:inline-flex; align-items:center; gap:5px; }
    .legend i { width:8px; height:8px; border-radius:50%; }
    @media (max-width:700px) { .stats { grid-template-columns:repeat(2,minmax(0,1fr)); } }
  `;
}

declare global { interface HTMLElementTagNameMap { "rs-energy-analytics-chart": RsEnergyAnalyticsChart; } }
'''
(ROOT / "frontend/src/components/analytics/rs-energy-analytics-chart.ts").write_text(energy_chart, encoding="utf-8")

# Wire into analytics page.
p = ROOT / "frontend/src/components/rs-analytics.ts"
text = p.read_text(encoding="utf-8")
text = text.replace('import "./analytics/rs-analytics-chart";\n', 'import "./analytics/rs-analytics-chart";\nimport "./analytics/rs-energy-analytics-chart";\n', 1)
text = text.replace(
    '''              ${!this.rooms[this._selectedRoom]?.is_outdoor\n                ? html` <rs-analytics-model\n''',
    '''              ${!this.rooms[this._selectedRoom]?.is_outdoor\n                ? html`\n                    <rs-energy-analytics-chart\n                      .hass=${this.hass}\n                      .data=${this._data}\n                      .language=${l}\n                    ></rs-energy-analytics-chart>\n                    <rs-analytics-model\n''',
    1,
)
p.write_text(text, encoding="utf-8")

# English fallback strings (localize falls back to English for missing locales).
p = ROOT / "frontend/src/locales/en.json"
text = p.read_text(encoding="utf-8")
anchor = '    "temperature": "Temperature",\n'
addition = '''    "energy_title": "Energy consumption",\n    "energy_subtitle": "Measured AC demand and learned 3-hour forecast",\n    "energy_room_power": "Room total",\n    "energy_forecast": "Room forecast",\n    "energy_forecast_short": "forecast",\n    "energy_now": "Power now",\n    "energy_period": "Energy in range",\n    "energy_next_3h": "Forecast next 3h",\n    "energy_learning": "Learning samples",\n'''
if anchor not in text:
    raise SystemExit("en locale analytics anchor missing")
text = text.replace(anchor, anchor + addition, 1)
p.write_text(text, encoding="utf-8")

# Focused regression tests for backend analytics energy fields.
p = ROOT / "tests/services/test_analytics_service.py"
text = p.read_text(encoding="utf-8")
if "test_csv_to_points_includes_energy_fields" not in text:
    text += '''\n\ndef test_csv_to_points_includes_energy_fields():\n    from custom_components.roommind.services.analytics_service import _csv_to_points\n\n    points = _csv_to_points(\n        [\n            {\n                "timestamp": "1000",\n                "ac_power_w": "512.4",\n                "ac_device_power_w_json": '{"climate.ac_sala":312.4,"climate.ac_studio":200}',\n                "predicted_power_w": "540",\n                "predicted_device_power_w_json": '{"climate.ac_sala":330}',\n                "ac_energy_today_kwh": "1.25",\n                "energy_learning_samples": "42",\n            }\n        ]\n    )\n    assert points[0]["ac_power_w"] == 512.4\n    assert points[0]["ac_device_power_w"] == {"climate.ac_sala": 312.4, "climate.ac_studio": 200.0}\n    assert points[0]["predicted_power_w"] == 540.0\n    assert points[0]["predicted_device_power_w"] == {"climate.ac_sala": 330.0}\n    assert points[0]["ac_energy_today_kwh"] == 1.25\n    assert points[0]["energy_learning_samples"] == 42\n'''
    p.write_text(text, encoding="utf-8")

p = ROOT / "tests/test_energy_mold_v2.py"
text = p.read_text(encoding="utf-8")
if "test_energy_manager_tracks_and_predicts_device_breakdown" not in text:
    text += '''\n\ndef test_energy_manager_tracks_and_predicts_device_breakdown():\n    from unittest.mock import MagicMock\n\n    from custom_components.roommind.managers.energy_manager import EnergyManager\n\n    hass = MagicMock()\n    power = MagicMock(state="0.45", attributes={"unit_of_measurement": "kW"})\n    climate = MagicMock(state="cool", attributes={})\n    hass.states.get.side_effect = {"sensor.ac_power": power, "climate.ac": climate}.get\n    manager = EnergyManager(hass)\n    room = {\n        "heat_pump_power_watts": 700,\n        "devices": [\n            {\n                "entity_id": "climate.ac",\n                "type": "ac",\n                "power_sensor_entity_id": "sensor.ac_power",\n            }\n        ],\n    }\n    room_state = {"current_temp": 28, "target_temp": 25, "current_humidity": 60, "commanded_mode": "cooling"}\n    for i in range(8):\n        result = manager.update_room("sala", room, room_state, 32, now=1000 + i * 60)\n    assert result["ac_device_power_w"] == {"climate.ac": 450.0}\n    assert result["predicted_device_power_w"]["climate.ac"] > 0\n    predicted, samples = manager.predict_power("sala", "cooling", 28, 25, 32, 60, 700)\n    assert predicted is not None and predicted > 0\n    assert samples >= 6\n'''
    p.write_text(text, encoding="utf-8")

print("energy analytics patch applied")
