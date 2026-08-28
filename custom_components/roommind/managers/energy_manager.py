"""Adaptive AC energy tracking and prediction for RoomMind."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime

from homeassistant.core import HomeAssistant

_MIN_ACTIVE_POWER_W = 10.0
_MIN_SAMPLES_FOR_PREDICTION = 6
_MAX_REASONABLE_POWER_W = 20000.0


@dataclass
class _LinearStats:
    """Small online ridge-regression accumulator for one HVAC mode."""

    n: int = 0
    xtx: list[list[float]] = field(default_factory=lambda: [[0.0] * 4 for _ in range(4)])
    xty: list[float] = field(default_factory=lambda: [0.0] * 4)
    observed_max_w: float = 0.0

    def add(self, features: list[float], power_w: float) -> None:
        self.n += 1
        self.observed_max_w = max(self.observed_max_w, power_w)
        for i in range(4):
            self.xty[i] += features[i] * power_w
            for j in range(4):
                self.xtx[i][j] += features[i] * features[j]

    def coefficients(self) -> list[float] | None:
        if self.n < _MIN_SAMPLES_FOR_PREDICTION:
            return None
        # Solve (X'X + lambda I)b = X'y with a tiny Gaussian eliminator.
        ridge = 0.15
        a = [row[:] + [self.xty[i]] for i, row in enumerate(self.xtx)]
        for i in range(4):
            a[i][i] += ridge
        for col in range(4):
            pivot = max(range(col, 4), key=lambda r: abs(a[r][col]))
            if abs(a[pivot][col]) < 1e-9:
                return None
            if pivot != col:
                a[col], a[pivot] = a[pivot], a[col]
            div = a[col][col]
            a[col] = [v / div for v in a[col]]
            for row in range(4):
                if row == col:
                    continue
                factor = a[row][col]
                if factor:
                    a[row] = [a[row][k] - factor * a[col][k] for k in range(5)]
        return [a[i][4] for i in range(4)]


@dataclass
class _RoomEnergyState:
    models: dict[str, _LinearStats] = field(default_factory=dict)
    last_ts: float | None = None
    last_power_w: float = 0.0
    day_key: str = ""
    energy_today_kwh: float = 0.0
    bootstrapped: bool = False


class EnergyManager:
    """Track measured AC power and learn a lightweight per-mode predictor."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._rooms: dict[str, _RoomEnergyState] = {}

    def remove_room(self, area_id: str) -> None:
        self._rooms.pop(area_id, None)

    def needs_bootstrap(self, area_id: str) -> bool:
        return not self._rooms.setdefault(area_id, _RoomEnergyState()).bootstrapped

    @staticmethod
    def _safe_float(value: object) -> float | None:
        try:
            value_f = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return value_f if math.isfinite(value_f) else None

    @staticmethod
    def _features(
        room_temp: float | None,
        target_temp: float | None,
        outdoor_temp: float | None,
        humidity: float | None,
    ) -> list[float]:
        temp_error = abs(room_temp - target_temp) if room_temp is not None and target_temp is not None else 0.0
        outdoor_delta = abs(room_temp - outdoor_temp) if room_temp is not None and outdoor_temp is not None else 0.0
        humidity_excess = max(0.0, (humidity or 50.0) - 50.0) / 10.0
        return [1.0, min(temp_error, 15.0), min(outdoor_delta, 30.0), min(humidity_excess, 5.0)]

    @staticmethod
    def _physical_mode(hass: HomeAssistant, room: dict, fallback: str) -> str:
        states: list[str] = []
        for dev in room.get("devices", []):
            if dev.get("type") != "ac":
                continue
            state = hass.states.get(dev.get("entity_id", ""))
            if state is not None and state.state not in ("unknown", "unavailable", "off"):
                states.append(state.state)
        if "dry" in states:
            return "dry"
        if "cool" in states:
            return "cooling"
        if "heat" in states:
            return "heating"
        if "fan_only" in states:
            return "fan_only"
        return fallback

    def read_power_w(self, room: dict) -> tuple[float, int]:
        total = 0.0
        configured = 0
        for dev in room.get("devices", []):
            if dev.get("type") != "ac":
                continue
            power_eid = dev.get("power_sensor_entity_id")
            if not power_eid:
                continue
            configured += 1
            state = self.hass.states.get(power_eid)
            if state is None or state.state in ("unknown", "unavailable", ""):
                continue
            value = self._safe_float(state.state)
            if value is None:
                continue
            unit = str(state.attributes.get("unit_of_measurement", "W")).lower()
            if unit == "kw":
                value *= 1000.0
            elif unit == "mw":
                value /= 1000.0
            total += max(0.0, value)
        return min(total, _MAX_REASONABLE_POWER_W), configured

    def bootstrap(self, area_id: str, rows: list[dict]) -> None:
        state = self._rooms.setdefault(area_id, _RoomEnergyState())
        if state.bootstrapped:
            return
        today = datetime.now().astimezone().date()
        today_rows: list[tuple[float, float]] = []
        for row in rows:
            power = self._safe_float(row.get("ac_power_w"))
            if power is None:
                continue
            mode = str(row.get("energy_mode") or row.get("mode") or "idle")
            room_temp = self._safe_float(row.get("room_temp"))
            target = self._safe_float(row.get("target_temp"))
            outdoor = self._safe_float(row.get("outdoor_temp"))
            humidity = self._safe_float(row.get("current_humidity"))
            if power >= _MIN_ACTIVE_POWER_W and mode in ("heating", "cooling", "dry"):
                model = state.models.setdefault(mode, _LinearStats())
                model.add(self._features(room_temp, target, outdoor, humidity), power)
            ts = self._safe_float(row.get("timestamp"))
            if ts is not None and datetime.fromtimestamp(ts).astimezone().date() == today:
                today_rows.append((ts, power))
        today_rows.sort()
        if len(today_rows) >= 2:
            energy_wh = 0.0
            for (t0, p0), (t1, p1) in zip(today_rows, today_rows[1:], strict=False):
                dt_h = min(max(t1 - t0, 0.0), 900.0) / 3600.0
                energy_wh += (p0 + p1) * 0.5 * dt_h
            state.energy_today_kwh = energy_wh / 1000.0
            state.last_ts, state.last_power_w = today_rows[-1]
        state.day_key = today.isoformat()
        state.bootstrapped = True

    def update_room(
        self,
        area_id: str,
        room: dict,
        room_state: dict,
        outdoor_temp: float | None,
        *,
        now: float | None = None,
    ) -> dict:
        now_ts = now or time.time()
        state = self._rooms.setdefault(area_id, _RoomEnergyState())
        state.bootstrapped = True
        power_w, configured = self.read_power_w(room)
        day_key = datetime.fromtimestamp(now_ts).astimezone().date().isoformat()
        if state.day_key != day_key:
            state.day_key = day_key
            state.energy_today_kwh = 0.0
            state.last_ts = None
            state.last_power_w = 0.0
        if state.last_ts is not None:
            dt_s = min(max(now_ts - state.last_ts, 0.0), 300.0)
            state.energy_today_kwh += ((state.last_power_w + power_w) * 0.5) * (dt_s / 3600.0) / 1000.0
        state.last_ts = now_ts
        state.last_power_w = power_w

        fallback_mode = str(room_state.get("commanded_mode") or room_state.get("mode") or "idle")
        mode = self._physical_mode(self.hass, room, fallback_mode)
        room_temp = self._safe_float(room_state.get("current_temp"))
        target = self._safe_float(room_state.get("target_temp"))
        humidity = self._safe_float(room_state.get("current_humidity"))
        features = self._features(room_temp, target, outdoor_temp, humidity)
        if power_w >= _MIN_ACTIVE_POWER_W and mode in ("heating", "cooling", "dry"):
            state.models.setdefault(mode, _LinearStats()).add(features, power_w)

        prediction: float | None = None
        samples = 0
        model = state.models.get(mode)
        if model is not None:
            samples = model.n
            coeff = model.coefficients()
            if coeff is not None:
                prediction = sum(coeff[i] * features[i] for i in range(4))
                ceiling = max(model.observed_max_w * 1.35, 250.0)
                prediction = max(0.0, min(prediction, ceiling, _MAX_REASONABLE_POWER_W))
        if prediction is None and mode in ("heating", "cooling", "dry"):
            nominal = self._safe_float(room.get("heat_pump_power_watts"))
            if nominal and nominal > 0:
                prediction = nominal

        return {
            "ac_power_w": round(power_w, 1) if configured else None,
            "ac_power_sensors": configured,
            "ac_energy_today_kwh": round(state.energy_today_kwh, 3) if configured else None,
            "energy_mode": mode,
            "predicted_power_w": round(prediction, 1) if prediction is not None else None,
            "predicted_energy_1h_kwh": round(prediction / 1000.0, 3) if prediction is not None else None,
            "energy_learning_samples": samples,
        }
