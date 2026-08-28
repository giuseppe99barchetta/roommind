from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str, *, count: int = 1) -> None:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"anchor not found in {path}: {old[:120]!r}")
    text = text.replace(old, new, count)
    p.write_text(text, encoding="utf-8")


energy_manager = '''\
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
'''
(ROOT / "custom_components/roommind/managers/energy_manager.py").write_text(energy_manager, encoding="utf-8")

# History schema + storage.
replace(
    "custom_components/roommind/utils/history_store.py",
    '    "room_temp",\n    "outdoor_temp",\n',
    '    "room_temp",\n    "current_humidity",\n    "outdoor_temp",\n',
)
replace(
    "custom_components/roommind/utils/history_store.py",
    '    "occupancy",\n]',
    '    "occupancy",\n    "energy_mode",\n    "ac_power_w",\n    "ac_energy_today_kwh",\n    "predicted_power_w",\n    "predicted_energy_1h_kwh",\n    "energy_learning_samples",\n]',
)
replace(
    "custom_components/roommind/utils/history_store.py",
    '                    "room_temp": data.get("room_temp", ""),\n                    "outdoor_temp": data.get("outdoor_temp", ""),',
    '                    "room_temp": data.get("room_temp", ""),\n                    "current_humidity": data.get("current_humidity", ""),\n                    "outdoor_temp": data.get("outdoor_temp", ""),',
)
replace(
    "custom_components/roommind/utils/history_store.py",
    '                    "occupancy": data.get("occupancy", ""),\n                }',
    '                    "occupancy": data.get("occupancy", ""),\n                    "energy_mode": data.get("energy_mode", ""),\n                    "ac_power_w": data.get("ac_power_w", ""),\n                    "ac_energy_today_kwh": data.get("ac_energy_today_kwh", ""),\n                    "predicted_power_w": data.get("predicted_power_w", ""),\n                    "predicted_energy_1h_kwh": data.get("predicted_energy_1h_kwh", ""),\n                    "energy_learning_samples": data.get("energy_learning_samples", ""),\n                }',
)
replace(
    "custom_components/roommind/utils/history_store.py",
    '                "mode": bucket[0]["mode"],\n                "window_open": bucket[0].get("window_open", ""),',
    '                "mode": bucket[0]["mode"],\n                "energy_mode": bucket[0].get("energy_mode", ""),\n                "window_open": bucket[0].get("window_open", ""),',
)
replace(
    "custom_components/roommind/utils/history_store.py",
    '                "blind_position",\n            ):',
    '                "blind_position",\n                "current_humidity",\n                "ac_power_w",\n                "ac_energy_today_kwh",\n                "predicted_power_w",\n                "predicted_energy_1h_kwh",\n                "energy_learning_samples",\n            ):',
)

# Mold manager: strategy-aware prevention.
replace(
    "custom_components/roommind/managers/mold_manager.py",
    '    prevention_active: bool = False\n    prevention_delta: float = 0.0\n',
    '    prevention_active: bool = False\n    prevention_delta: float = 0.0\n    prevention_strategy: str | None = None\n',
)
replace(
    "custom_components/roommind/managers/mold_manager.py",
    '        settings: dict,\n        celsius_delta_to_ha_fn: Callable[[float], float] | None = None,',
    '        settings: dict,\n        can_dry: bool = False,\n        can_cool: bool = False,\n        automation_enabled: bool = True,\n        celsius_delta_to_ha_fn: Callable[[float], float] | None = None,',
)
replace(
    "custom_components/roommind/managers/mold_manager.py",
    '            if settings.get("mold_prevention_enabled") and risk_level in (MOLD_RISK_WARNING, MOLD_RISK_CRITICAL):\n                intensity = settings.get("mold_prevention_intensity", "medium")\n                result.prevention_delta = mold_prevention_delta(intensity)\n',
    '            if (\n                settings.get("mold_prevention_enabled")\n                and automation_enabled\n                and risk_level in (MOLD_RISK_WARNING, MOLD_RISK_CRITICAL)\n            ):\n                intensity = settings.get("mold_prevention_intensity", "medium")\n                warm_weather = current_temp >= 23.0 or (\n                    outdoor_temp is not None and outdoor_temp >= 18.0 and current_temp >= 21.5\n                )\n                if can_dry and warm_weather:\n                    result.prevention_strategy = "dry"\n                    result.prevention_delta = 0.0\n                elif can_cool and current_temp >= 24.0:\n                    result.prevention_strategy = "cool"\n                    result.prevention_delta = 0.0\n                else:\n                    result.prevention_strategy = "heat"\n                    result.prevention_delta = mold_prevention_delta(intensity)\n',
)
replace(
    "custom_components/roommind/managers/mold_manager.py",
    '                                f"temperature raised by "\n                                f"{celsius_delta_to_ha_fn(result.prevention_delta):.0f}{ha_temp_unit_str_fn()}"\n',
    '                                (\n                                    f"AC dehumidification enabled ({result.prevention_strategy})"\n                                    if result.prevention_strategy in ("dry", "cool")\n                                    else f"temperature raised by "\n                                    f"{celsius_delta_to_ha_fn(result.prevention_delta):.0f}{ha_temp_unit_str_fn()}"\n                                )\n',
)

# Coordinator: imports, manager, bootstrap, energy state, strategy override.
replace(
    "custom_components/roommind/coordinator.py",
    'from .managers.ekf_training_manager import EkfTrainingManager\n',
    'from .managers.ekf_training_manager import EkfTrainingManager\nfrom .managers.energy_manager import EnergyManager\n',
)
replace(
    "custom_components/roommind/coordinator.py",
    '    "_heat_source_reason",\n)',
    '    "_heat_source_reason",\n    "_power",\n    "_energy_today",\n    "_predicted_power",\n    "_predicted_energy_1h",\n)',
)
replace(
    "custom_components/roommind/coordinator.py",
    '        # Mold risk tracking\n        self._mold_manager = MoldManager(hass)\n',
    '        # Mold risk tracking\n        self._mold_manager = MoldManager(hass)\n        # AC power history + adaptive consumption prediction\n        self._energy_manager = EnergyManager(hass)\n',
)
replace(
    "custom_components/roommind/coordinator.py",
    '        if self._history_store is None:\n            self._history_store = HistoryStore(self.hass.config.path(".storage/roommind_history"))\n\n        room_states: dict[str, dict] = {}\n',
    '        if self._history_store is None:\n            self._history_store = HistoryStore(self.hass.config.path(".storage/roommind_history"))\n\n        # Rebuild energy-learning statistics from persisted RoomMind history after\n        # restart. Only rows written by versions with power fields contribute.\n        if self._history_store is not None:\n            for area_id in rooms:\n                if not self._energy_manager.needs_bootstrap(area_id):\n                    continue\n                try:\n                    detail = await self.hass.async_add_executor_job(\n                        self._history_store.read_detail, area_id, 14 * 24 * 3600\n                    )\n                    history = await self.hass.async_add_executor_job(\n                        self._history_store.read_history, area_id, 30 * 24 * 3600\n                    )\n                    self._energy_manager.bootstrap(area_id, history + detail)\n                except Exception:  # noqa: BLE001\n                    _LOGGER.warning("Energy history bootstrap failed for \'%s\'", area_id)\n\n        room_states: dict[str, dict] = {}\n',
)
replace(
    "custom_components/roommind/coordinator.py",
    '        # Control master devices based on aggregate room demand\n',
    '        # Attach measured AC power, daily integrated energy and learned\n        # consumption forecasts to each room before entities/history consume it.\n        for area_id, room_state in room_states.items():\n            room = rooms.get(area_id, {})\n            if room.get("is_outdoor", False):\n                continue\n            room_state.update(\n                self._energy_manager.update_room(\n                    area_id, room, room_state, self.outdoor_temp_effective\n                )\n            )\n\n        # Control master devices based on aggregate room demand\n',
)
replace(
    "custom_components/roommind/coordinator.py",
    '                            "occupancy": rs.get("q_occupancy", 0.0) > 0,\n',
    '                            "occupancy": rs.get("q_occupancy", 0.0) > 0,\n                            "current_humidity": rs.get("current_humidity"),\n                            "energy_mode": rs.get("energy_mode"),\n                            "ac_power_w": rs.get("ac_power_w"),\n                            "ac_energy_today_kwh": rs.get("ac_energy_today_kwh"),\n                            "predicted_power_w": rs.get("predicted_power_w"),\n                            "predicted_energy_1h_kwh": rs.get("predicted_energy_1h_kwh"),\n                            "energy_learning_samples": rs.get("energy_learning_samples"),\n',
)
replace(
    "custom_components/roommind/coordinator.py",
    '    ) -> tuple[str, float | None, bool, float]:\n        """Evaluate mold risk for a room.\n\n        Returns (mold_risk_level, mold_surface_rh, mold_prevention_active, mold_prevention_delta).\n        """\n        mold = await self._mold_manager.evaluate(\n',
    '        room: dict,\n    ) -> tuple[str, float | None, bool, float, str | None]:\n        """Evaluate mold risk and select an automatic prevention strategy."""\n        ac_modes: set[str] = set()\n        for eid in get_ac_eids(room.get("devices", [])):\n            state = self.hass.states.get(eid)\n            if state is not None:\n                ac_modes.update(state.attributes.get("hvac_modes", []) or [])\n        automation_enabled = bool(\n            settings.get("climate_control_active", True)\n            and room.get("climate_control_enabled", True)\n        )\n        mold = await self._mold_manager.evaluate(\n',
)
replace(
    "custom_components/roommind/coordinator.py",
    '            settings,\n            celsius_delta_to_ha_fn=',
    '            settings,\n            can_dry="dry" in ac_modes,\n            can_cool=bool(ac_modes & {"cool", "heat_cool", "auto"}),\n            automation_enabled=automation_enabled,\n            celsius_delta_to_ha_fn=',
)
replace(
    "custom_components/roommind/coordinator.py",
    '        return mold.risk_level, mold.surface_rh, mold.prevention_active, mold.prevention_delta\n',
    '        return (\n            mold.risk_level,\n            mold.surface_rh,\n            mold.prevention_active,\n            mold.prevention_delta,\n            mold.prevention_strategy,\n        )\n',
)
replace(
    "custom_components/roommind/coordinator.py",
    '            mold_prevention_temp_delta,\n        ) = await self._evaluate_mold_risk(area_id, current_temp, current_humidity, settings)\n',
    '            mold_prevention_temp_delta,\n            mold_prevention_strategy,\n        ) = await self._evaluate_mold_risk(\n            area_id, current_temp, current_humidity, settings, room\n        )\n',
)
old_mold_block = '''        # Mold prevention may override autonomous schedule/presence OFF, but
        # never an explicit manual OFF/FAN_ONLY/DRY selection on the canonical
        # climate entity. Manual intent is authoritative; mold risk remains
        # visible while prevention is reported active only when actually applied.
        manual_aux_or_off = requested_hvac_mode in ("off", "dry", "fan_only")
        force_off = targets.heat is None and targets.cool is None or manual_aux_or_off
        mold_prevention_effective = bool(
            mold_prevention_active_room and mold_prevention_temp_delta > 0 and not manual_aux_or_off
        )
        if mold_prevention_effective:
            if targets.heat is None:
                eco_heat = room.get("eco_heat", room.get("eco_temp", DEFAULT_ECO_HEAT))
                eco_cool = room.get("eco_cool", DEFAULT_ECO_COOL)
                targets = TargetTemps(
                    heat=eco_heat + mold_prevention_temp_delta,
                    cool=eco_cool,
                )
                force_off = False
            else:
                targets = TargetTemps(
                    heat=targets.heat + mold_prevention_temp_delta,
                    cool=targets.cool,
                )
        mold_prevention_active_room = mold_prevention_effective
'''
new_mold_block = '''        # Mold prevention is an automatic safety policy. While RoomMind automatic
        # control is enabled it temporarily supersedes OFF/FAN_ONLY/DRY, but the
        # persisted room_hvac_mode is never overwritten. When risk clears the next
        # tick therefore restores exactly the user's previous mode.
        automation_enabled = bool(
            settings.get("climate_control_active", True)
            and room.get("climate_control_enabled", True)
        )
        mold_prevention_effective = bool(
            mold_prevention_active_room and automation_enabled and mold_prevention_strategy
        )
        effective_requested_hvac_mode = requested_hvac_mode
        if mold_prevention_effective:
            effective_requested_hvac_mode = mold_prevention_strategy
            force_off = False
            if mold_prevention_strategy == "heat":
                base_heat = targets.heat
                if base_heat is None:
                    base_heat = room.get("eco_heat", room.get("eco_temp", DEFAULT_ECO_HEAT))
                targets = TargetTemps(
                    heat=float(base_heat) + mold_prevention_temp_delta,
                    cool=None,
                )
            elif mold_prevention_strategy == "cool":
                base_cool = targets.cool
                if base_cool is None:
                    base_cool = room.get("eco_cool", DEFAULT_ECO_COOL)
                targets = TargetTemps(heat=None, cool=float(base_cool))
            else:  # dry: no thermal setpoint; AC auxiliary routing owns actuation
                targets = TargetTemps(heat=None, cool=None)
        else:
            manual_aux_or_off = requested_hvac_mode in ("off", "dry", "fan_only")
            force_off = targets.heat is None and targets.cool is None or manual_aux_or_off
        mold_prevention_active_room = mold_prevention_effective
'''
replace("custom_components/roommind/coordinator.py", old_mold_block, new_mold_block)
replace(
    "custom_components/roommind/coordinator.py",
    '        controller = MPCController(\n            self.hass,\n            room,\n',
    '        control_room = room\n        if mold_prevention_effective and effective_requested_hvac_mode != requested_hvac_mode:\n            control_room = dict(room)\n            control_room["room_hvac_mode"] = effective_requested_hvac_mode\n\n        controller = MPCController(\n            self.hass,\n            control_room,\n',
)
# Make DRY mold prevention intentionally activate the AC after safe idling.
replace(
    "custom_components/roommind/coordinator.py",
    '                if requested_hvac_mode in ("dry", "fan_only"):\n                    # Controller has safely idled every managed device; only\n                    # the AC is then allowed to receive the auxiliary mode.\n                    await async_apply_ac_auxiliary_mode(self.hass, room, window_open=window_open)\n',
    '                if mold_prevention_effective and mold_prevention_strategy == "dry" and not window_open:\n                    # Unlike a persisted user DRY mode, prevention is an explicit\n                    # automatic activation request. TRVs have just been idled by\n                    # the controller; activate every capable AC in DRY.\n                    for ac_eid in get_ac_eids(room.get("devices", [])):\n                        ac_state = self.hass.states.get(ac_eid)\n                        if ac_state is None or "dry" not in (ac_state.attributes.get("hvac_modes") or []):\n                            continue\n                        await self.hass.services.async_call(\n                            "climate",\n                            "set_hvac_mode",\n                            {"entity_id": ac_eid, "hvac_mode": "dry"},\n                            blocking=True,\n                            context=make_roommind_context(),\n                        )\n                elif requested_hvac_mode in ("dry", "fan_only"):\n                    # Persisted auxiliary state is preservation-only; it must not\n                    # power an AC back on after restart or an external power-off.\n                    await async_apply_ac_auxiliary_mode(self.hass, room, window_open=window_open)\n',
)
replace(
    "custom_components/roommind/coordinator.py",
    '            mold_prevention_temp_delta=mold_prevention_temp_delta,\n            shading_factor=shading_factor,',
    '            mold_prevention_temp_delta=mold_prevention_temp_delta,\n            mold_prevention_strategy=mold_prevention_strategy if mold_prevention_effective else None,\n            shading_factor=shading_factor,',
)
replace(
    "custom_components/roommind/coordinator.py",
    '        mold_prevention_temp_delta: float,\n        shading_factor: float | None,',
    '        mold_prevention_temp_delta: float,\n        mold_prevention_strategy: str | None,\n        shading_factor: float | None,',
)
replace(
    "custom_components/roommind/coordinator.py",
    '            "mold_prevention_delta": mold_prevention_temp_delta,\n',
    '            "mold_prevention_delta": mold_prevention_temp_delta,\n            "mold_prevention_strategy": mold_prevention_strategy,\n',
)
replace(
    "custom_components/roommind/coordinator.py",
    '        self._model_manager.remove_room(area_id)\n        self._heat_source_states.pop(area_id, None)\n',
    '        self._model_manager.remove_room(area_id)\n        self._energy_manager.remove_room(area_id)\n        self._heat_source_states.pop(area_id, None)\n',
)

# Sensor entities.
replace(
    "custom_components/roommind/sensor.py",
    'from homeassistant.components.sensor import SensorEntity\n',
    'from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass\n',
)
replace(
    "custom_components/roommind/sensor.py",
    '        RoomMindHeatSourceReasonSensor(coordinator, area_id),\n    ]',
    '        RoomMindHeatSourceReasonSensor(coordinator, area_id),\n        RoomMindPowerSensor(coordinator, area_id),\n        RoomMindEnergyTodaySensor(coordinator, area_id),\n        RoomMindPredictedPowerSensor(coordinator, area_id),\n        RoomMindPredictedEnergySensor(coordinator, area_id),\n    ]',
)
insert_sensor_anchor = '''class _GlobalSensor(CoordinatorEntity, SensorEntity):
'''
energy_sensors = '''class RoomMindPowerSensor(_RoomMindBaseSensor):
    _data_key = "ac_power_w"
    _attr_native_unit_of_measurement = "W"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator, area_id, "power", "AC Power")


class RoomMindEnergyTodaySensor(_RoomMindBaseSensor):
    _data_key = "ac_energy_today_kwh"
    _attr_native_unit_of_measurement = "kWh"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator, area_id, "energy_today", "AC Energy Today")


class RoomMindPredictedPowerSensor(_RoomMindBaseSensor):
    _data_key = "predicted_power_w"
    _attr_native_unit_of_measurement = "W"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator, area_id, "predicted_power", "Predicted AC Power")


class RoomMindPredictedEnergySensor(_RoomMindBaseSensor):
    _data_key = "predicted_energy_1h_kwh"
    _attr_native_unit_of_measurement = "kWh"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator, area_id, "predicted_energy_1h", "Predicted AC Energy 1h")


'''
replace("custom_components/roommind/sensor.py", insert_sensor_anchor, energy_sensors + insert_sensor_anchor)

# Websocket device config + live energy/mold fields.
replace(
    "custom_components/roommind/websocket_api.py",
    '                    vol.Optional("setpoint_mode", default="proportional"): vol.In(["proportional", "direct"]),\n',
    '                    vol.Optional("setpoint_mode", default="proportional"): vol.In(["proportional", "direct"]),\n                    vol.Optional("power_sensor_entity_id", default=""): str,\n',
)
replace(
    "custom_components/roommind/websocket_api.py",
    '            "mold_prevention_delta": live.get("mold_prevention_delta", 0),\n',
    '            "mold_prevention_delta": live.get("mold_prevention_delta", 0),\n            "mold_prevention_strategy": live.get("mold_prevention_strategy"),\n            "ac_power_w": live.get("ac_power_w"),\n            "ac_energy_today_kwh": live.get("ac_energy_today_kwh"),\n            "predicted_power_w": live.get("predicted_power_w"),\n            "predicted_energy_1h_kwh": live.get("predicted_energy_1h_kwh"),\n            "energy_learning_samples": live.get("energy_learning_samples", 0),\n',
)

# Frontend types.
replace(
    "frontend/src/types/index.ts",
    '  setpoint_mode?: "proportional" | "direct"; // default "proportional"\n}',
    '  setpoint_mode?: "proportional" | "direct"; // default "proportional"\n  power_sensor_entity_id?: string; // instantaneous AC consumption sensor (W/kW)\n}',
)
replace(
    "frontend/src/types/index.ts",
    '  mold_prevention_delta: number;\n',
    '  mold_prevention_delta: number;\n  mold_prevention_strategy?: "heat" | "dry" | "cool" | null;\n  ac_power_w?: number | null;\n  ac_energy_today_kwh?: number | null;\n  predicted_power_w?: number | null;\n  predicted_energy_1h_kwh?: number | null;\n  energy_learning_samples?: number;\n',
)
replace(
    "frontend/src/types/index.ts",
    '  device_setpoint?: number | null;\n}',
    '  device_setpoint?: number | null;\n  current_humidity?: number | null;\n  energy_mode?: string;\n  ac_power_w?: number | null;\n  ac_energy_today_kwh?: number | null;\n  predicted_power_w?: number | null;\n  predicted_energy_1h_kwh?: number | null;\n}',
)

# Device UI power-sensor picker for ACs.
replace(
    "frontend/src/components/rs-device-section.ts",
    '            ${device.idle_action === "fan_only"\n',
    '            <div class="detail-field with-info">\n              <ha-entity-picker\n                .hass=${this.hass}\n                .includeDomains=${["sensor"]}\n                .value=${device.power_sensor_entity_id ?? ""}\n                .label=${localize("devices.power_sensor", lang)}\n                @value-changed=${(e: CustomEvent) =>\n                  this._onPowerSensorChange(entityId, (e.detail?.value as string) ?? "")}\n              ></ha-entity-picker>\n              <rs-info-icon .text=${localize("devices.power_sensor_hint", lang)}></rs-info-icon>\n            </div>\n            ${device.idle_action === "fan_only"\n',
)
replace(
    "frontend/src/components/rs-device-section.ts",
    '  private _onSetpointModeChange(entityId: string, mode: string): void {\n',
    '  private _onPowerSensorChange(entityId: string, powerSensor: string): void {\n    const newDevices = this.devices.map((d) =>\n      d.entity_id === entityId ? { ...d, power_sensor_entity_id: powerSensor } : d,\n    );\n    this._fireDeviceChanged(newDevices);\n  }\n\n  private _onSetpointModeChange(entityId: string, mode: string): void {\n',
)

# Locale strings (flat-key JSON files).
locale_values = {
    "en.json": {
        "devices.power_sensor": "Power sensor",
        "devices.power_sensor_hint": "Instantaneous electrical consumption sensor for this AC. W and kW sensors are supported and used for energy history and adaptive predictions.",
    },
    "de.json": {
        "devices.power_sensor": "Leistungssensor",
        "devices.power_sensor_hint": "Sensor für den momentanen Stromverbrauch dieser Klimaanlage. W- und kW-Sensoren werden für Energieverlauf und adaptive Prognosen unterstützt.",
    },
    "fr.json": {
        "devices.power_sensor": "Capteur de puissance",
        "devices.power_sensor_hint": "Capteur de consommation électrique instantanée de ce climatiseur. Les capteurs en W et kW servent à l’historique et aux prévisions adaptatives.",
    },
}
for filename, additions in locale_values.items():
    p = ROOT / "frontend/src/locales" / filename
    data = json.loads(p.read_text(encoding="utf-8"))
    data.update(additions)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# Analytics service: expose new history fields if present.
analytics = ROOT / "custom_components/roommind/services/analytics_service.py"
if analytics.exists():
    text = analytics.read_text(encoding="utf-8")
    old = '            "device_setpoint": _safe_float(row.get("device_setpoint")),\n'
    if old in text:
        text = text.replace(
            old,
            old
            + '            "current_humidity": _safe_float(row.get("current_humidity")),\n'
            + '            "energy_mode": row.get("energy_mode") or None,\n'
            + '            "ac_power_w": _safe_float(row.get("ac_power_w")),\n'
            + '            "ac_energy_today_kwh": _safe_float(row.get("ac_energy_today_kwh")),\n'
            + '            "predicted_power_w": _safe_float(row.get("predicted_power_w")),\n'
            + '            "predicted_energy_1h_kwh": _safe_float(row.get("predicted_energy_1h_kwh")),\n',
            1,
        )
        analytics.write_text(text, encoding="utf-8")

# Focused tests.
test_file = '''\
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.roommind.managers.energy_manager import EnergyManager
from custom_components.roommind.managers.mold_manager import MoldManager
from custom_components.roommind.const import MOLD_RISK_WARNING


class _State:
    def __init__(self, state, attrs=None):
        self.state = state
        self.attributes = attrs or {}


def _hass(states):
    hass = MagicMock()
    hass.states.get.side_effect = states.get
    return hass


def test_energy_manager_integrates_and_learns_power():
    states = {
        "sensor.ac_power": _State("500", {"unit_of_measurement": "W"}),
        "climate.ac": _State("cool", {"hvac_modes": ["off", "cool", "dry"]}),
    }
    manager = EnergyManager(_hass(states))
    room = {
        "devices": [
            {"entity_id": "climate.ac", "type": "ac", "power_sensor_entity_id": "sensor.ac_power"}
        ]
    }
    rs = {"current_temp": 28.0, "current_humidity": 60.0, "target_temp": 26.0, "mode": "cooling"}
    base = 1_700_000_000.0
    result = None
    for i in range(8):
        result = manager.update_room("studio", room, rs, 32.0, now=base + i * 60)
    assert result is not None
    assert result["ac_power_w"] == 500.0
    assert result["ac_energy_today_kwh"] > 0
    assert result["energy_mode"] == "cooling"
    assert result["energy_learning_samples"] >= 6
    assert result["predicted_power_w"] is not None


def test_energy_manager_converts_kw_sensor():
    states = {
        "sensor.ac_power": _State("0.72", {"unit_of_measurement": "kW"}),
        "climate.ac": _State("cool", {"hvac_modes": ["cool"]}),
    }
    manager = EnergyManager(_hass(states))
    power, configured = manager.read_power_w(
        {"devices": [{"entity_id": "climate.ac", "type": "ac", "power_sensor_entity_id": "sensor.ac_power"}]}
    )
    assert configured == 1
    assert power == pytest.approx(720.0)


@pytest.mark.asyncio
async def test_mold_prevention_prefers_dry_in_warm_weather(monkeypatch):
    manager = MoldManager(MagicMock())
    monkeypatch.setattr(
        "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
        lambda *_: (MOLD_RISK_WARNING, 82.0),
    )
    result = await manager.evaluate(
        "studio",
        "Studio",
        27.0,
        72.0,
        29.0,
        {"mold_prevention_enabled": True, "mold_humidity_threshold": 65},
        can_dry=True,
        can_cool=True,
        automation_enabled=True,
    )
    assert result.prevention_active is True
    assert result.prevention_strategy == "dry"
    assert result.prevention_delta == 0.0


@pytest.mark.asyncio
async def test_mold_prevention_uses_heat_in_cold_weather(monkeypatch):
    manager = MoldManager(MagicMock())
    monkeypatch.setattr(
        "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
        lambda *_: (MOLD_RISK_WARNING, 82.0),
    )
    result = await manager.evaluate(
        "bedroom",
        "Bedroom",
        19.0,
        72.0,
        5.0,
        {"mold_prevention_enabled": True, "mold_humidity_threshold": 65},
        can_dry=True,
        can_cool=True,
        automation_enabled=True,
    )
    assert result.prevention_strategy == "heat"
    assert result.prevention_delta > 0


@pytest.mark.asyncio
async def test_mold_prevention_does_not_act_when_automation_disabled(monkeypatch):
    manager = MoldManager(MagicMock())
    monkeypatch.setattr(
        "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
        lambda *_: (MOLD_RISK_WARNING, 82.0),
    )
    result = await manager.evaluate(
        "studio",
        "Studio",
        27.0,
        72.0,
        29.0,
        {"mold_prevention_enabled": True, "mold_humidity_threshold": 65},
        can_dry=True,
        automation_enabled=False,
    )
    assert result.prevention_active is False
    assert result.prevention_strategy is None
'''
(ROOT / "tests/test_energy_mold_v2.py").write_text(test_file, encoding="utf-8")

print("energy + mold v2 patch applied")
