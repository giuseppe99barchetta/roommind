"""Analytics data assembly service for RoomMind."""

from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime
from typing import Any, cast

from homeassistant.core import HomeAssistant

from ..const import (
    CLIMATE_MODE_COOL_ONLY,
    CLIMATE_MODE_HEAT_ONLY,
    DEFAULT_COMFORT_COOL,
    DEFAULT_COMFORT_HEAT,
    DEFAULT_ECO_COOL,
    DEFAULT_ECO_HEAT,
)
from ..control.mpc_controller import (
    DEFAULT_OUTDOOR_TEMP_FALLBACK,
    check_acs_can_heat,
    get_can_heat_cool,
    is_mpc_active,
)
from ..utils.device_utils import room_has_power_sensor

_LOGGER = logging.getLogger(__name__)


def _safe_float(value: str) -> float | None:
    """Convert CSV string to float, or None for empty/invalid values."""
    if not value:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value: str) -> int | None:
    """Convert CSV string to int, or None for empty/invalid values."""
    if not value:
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _safe_power_map(value: object) -> dict[str, float]:
    """Decode compact per-device power maps from history CSV rows."""
    if isinstance(value, dict):
        raw = value
    elif isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        raw = parsed if isinstance(parsed, dict) else {}
    else:
        return {}
    result: dict[str, float] = {}
    for key, item in raw.items():
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number) and number >= 0:
            result[str(key)] = round(number, 1)
    return result


def _integrate_power_kwh(points: list[dict], start_ts: float | None = None) -> float:
    """Integrate measured or predicted watts using the trapezoidal rule."""
    usable = sorted(
        (point for point in points if point.get("ts") is not None and point.get("ac_power_w") is not None),
        key=lambda point: point["ts"],
    )
    watt_hours = 0.0
    for previous, current in zip(usable, usable[1:], strict=False):
        if start_ts is not None and previous["ts"] < start_ts:
            continue
        hours = min(max(current["ts"] - previous["ts"], 0.0), 900.0) / 3600.0
        watt_hours += (previous["ac_power_w"] + current["ac_power_w"]) * 0.5 * hours
    return watt_hours / 1000.0


def _integrate_forecast_kwh(points: list[dict]) -> float:
    """Integrate forecast watts without conflating them with measured power."""
    return _integrate_power_kwh(
        [{"ts": point.get("ts"), "ac_power_w": point.get("predicted_power_w")} for point in points]
    )


def _comparison_metrics(points: list[dict], price: float) -> dict[str, float | int | None]:
    """Summarize measured AC operation for a comparable room-level period."""
    points = sorted(points, key=lambda point: point["ts"])
    energy = _integrate_power_kwh(points)
    active_minutes = 0.0
    useful_delta = 0.0
    reaches: list[float] = []
    session_started: float | None = None
    session_mode = ""
    for previous, current in zip(points, points[1:], strict=False):
        dt_minutes = min(max(current["ts"] - previous["ts"], 0.0), 900.0) / 60.0
        mode = current.get("energy_mode") or current.get("mode")
        active = mode in ("heating", "cooling")
        if active:
            active_minutes += dt_minutes
            if previous.get("room_temp") is not None and current.get("room_temp") is not None:
                change = current["room_temp"] - previous["room_temp"]
                useful_delta += max(0.0, change if mode == "heating" else -change)
            if session_started is None or session_mode != mode:
                session_started, session_mode = previous["ts"], mode
            target = current.get("target_temp")
            temp = current.get("room_temp")
            if session_started is not None and target is not None and temp is not None:
                reached = temp >= target if mode == "heating" else temp <= target
                if reached:
                    reaches.append((current["ts"] - session_started) / 60.0)
                    session_started = None
        else:
            session_started, session_mode = None, ""
    return {
        "energy_kwh": round(energy, 2),
        "cost_eur": round(energy * price, 2) if price > 0 else None,
        "active_minutes": round(active_minutes),
        "delta_t_per_kwh": round(useful_delta / energy, 2) if energy > 0 else None,
        "target_reach_minutes": round(sum(reaches) / len(reaches)) if reaches else None,
    }


def _comparison_data_quality(points: list[dict]) -> list[str]:
    """Describe conditions that make comparison metrics less reliable."""
    issues: list[str] = []
    if len(points) < 10:
        issues.append("insufficient_samples")
    if not any(point.get("ac_power_w") is not None for point in points):
        issues.append("no_power_measurements")
    timestamps = sorted(point["ts"] for point in points if point.get("ts") is not None)
    if any(current - previous > 900 for previous, current in zip(timestamps, timestamps[1:], strict=False)):
        issues.append("history_gaps")
    return issues


async def build_comparison_data(
    hass: HomeAssistant,
    store: Any,
    coordinator: Any,
    custom_start: float | None = None,
    custom_end: float | None = None,
) -> dict:
    """Build cross-room AC analytics for the selected history range."""
    settings = store.get_settings()
    price = max(0.0, float(settings.get("energy_price_per_kwh", 0) or 0))
    history_store = getattr(coordinator, "_history_store", None)
    result: list[dict] = []
    for area_id, room in store.get_rooms().items():
        if not room_has_power_sensor(room):
            continue
        points: list[dict] = []
        if history_store:
            week = 7 * 24 * 3600
            if custom_start is not None:
                points = _csv_to_points(
                    await hass.async_add_executor_job(history_store.read_history, area_id, None, custom_start, custom_end)
                ) + _csv_to_points(
                    await hass.async_add_executor_job(history_store.read_detail, area_id, None, custom_start, custom_end)
                )
            else:
                points = _csv_to_points(
                    await hass.async_add_executor_job(history_store.read_history, area_id, week)
                ) + _csv_to_points(await hass.async_add_executor_job(history_store.read_detail, area_id, week))
        metrics = _comparison_metrics(points, price)
        live = getattr(coordinator, "rooms", {}).get(area_id, {})
        result.append(
            {
                "area_id": area_id,
                "name": room.get("display_name") or area_id.replace("_", " ").title(),
                **metrics,
                "data_quality": _comparison_data_quality(points),
                "today_kwh": live.get("ac_energy_today_kwh"),
                "today_cost_eur": live.get("energy_cost_today_eur"),
            }
        )
    return {"rooms": result, "price_eur_kwh": price}


def _csv_to_points(rows: list[dict]) -> list[dict]:
    """Convert CSV rows (string values, 'timestamp' key) to typed points ('ts' key)."""
    result = []
    for row in rows:
        ts = _safe_float(row.get("timestamp", ""))
        if ts is None:
            continue
        result.append(
            {
                "ts": ts,
                "room_temp": _safe_float(row.get("room_temp", "")),
                "outdoor_temp": _safe_float(row.get("outdoor_temp", "")),
                "target_temp": _safe_float(row.get("target_temp", "")),
                "mode": row.get("mode", ""),
                "predicted_temp": _safe_float(row.get("predicted_temp", "")),
                "window_open": row.get("window_open", "") in ("True", "true", "1"),
                "heating_power": _safe_float(row.get("heating_power", "")),
                "solar_irradiance": _safe_float(row.get("solar_irradiance", "")),
                "blind_position": _safe_int(row.get("blind_position", "")),
                "cover_reason": row.get("cover_reason", ""),
                "device_setpoint": _safe_float(row.get("device_setpoint", "")),
                "current_humidity": _safe_float(row.get("current_humidity", "")),
                "energy_mode": row.get("energy_mode", ""),
                "ac_power_w": _safe_float(row.get("ac_power_w", "")),
                "ac_device_power_w": _safe_power_map(row.get("ac_device_power_w_json", "")),
                "ac_energy_today_kwh": _safe_float(row.get("ac_energy_today_kwh", "")),
                "predicted_power_w": _safe_float(row.get("predicted_power_w", "")),
                "predicted_device_power_w": _safe_power_map(row.get("predicted_device_power_w_json", "")),
                "predicted_energy_1h_kwh": _safe_float(row.get("predicted_energy_1h_kwh", "")),
                "energy_learning_samples": _safe_int(row.get("energy_learning_samples", "")),
                "energy_prediction_confidence": row.get("energy_prediction_confidence") or None,
                "window_open_minutes": _safe_int(row.get("window_open_minutes", "")),
                "window_impact_c": _safe_float(row.get("window_impact_c", "")),
                "ac_efficiency_status": row.get("ac_efficiency_status") or None,
            }
        )
    return result


async def _compute_target_forecast(
    hass: HomeAssistant,
    room: dict,
    settings: dict,
    mold_prevention_delta: float = 0.0,
    hours: float = 3.0,
    interval_minutes: int = 5,
    schedule_blocks_cache: dict[str, dict] | None = None,
) -> list[dict]:
    """Compute target temperature forecast for the next N hours.

    Each point contains ``target_temp`` (chart display, mode-aware),
    ``heat_target`` and ``cool_target`` (for MPC simulator).
    """
    from ..utils.presence_utils import is_presence_away
    from ..utils.schedule_utils import (
        get_active_schedule_entity,
        read_schedule_blocks,
        resolve_targets_at_time,
    )
    from ..utils.temp_utils import ha_temp_to_celsius

    comfort_heat = room.get("comfort_heat", room.get("comfort_temp", DEFAULT_COMFORT_HEAT))
    comfort_cool = room.get("comfort_cool", DEFAULT_COMFORT_COOL)
    eco_heat = room.get("eco_heat", room.get("eco_temp", DEFAULT_ECO_HEAT))
    eco_cool = room.get("eco_cool", DEFAULT_ECO_COOL)
    override_until = room.get("override_until")
    override_heat = room.get("override_heat")
    override_cool = room.get("override_cool")
    vacation_until = settings.get("vacation_until")
    vacation_temp = settings.get("vacation_temp")
    climate_mode = room.get("climate_mode", "auto")

    presence_away = not room.get("ignore_presence", False) and is_presence_away(hass, room, settings)

    entity_id = get_active_schedule_entity(hass, room)
    schedule_blocks = await read_schedule_blocks(hass, entity_id, cache=schedule_blocks_cache) if entity_id else None

    _hass = hass
    converter = lambda v: ha_temp_to_celsius(_hass, v)  # noqa: E731

    # Generate forecast points
    now = time.time()
    end_ts = now + hours * 3600
    result: list[dict] = []
    ts = now
    while ts <= end_ts:
        targets = resolve_targets_at_time(
            ts,
            schedule_blocks,
            override_until,
            override_heat,
            override_cool,
            vacation_until,
            vacation_temp,
            comfort_heat,
            comfort_cool,
            eco_heat,
            eco_cool,
            presence_away=presence_away,
            block_temp_converter=converter,
            presence_away_action=settings.get("presence_away_action", "eco"),
            schedule_off_action=settings.get("schedule_off_action", "eco"),
            presence_clears_override=bool(settings.get("presence_clears_override", False)),
        )
        heat_target = targets.heat
        cool_target = targets.cool

        # Apply mold prevention delta to heat target only
        if heat_target is not None:
            heat_target = round(heat_target + mold_prevention_delta, 1)
        elif mold_prevention_delta > 0:
            heat_target = round(eco_heat + mold_prevention_delta, 1)

        # Chart display: mode-aware single value
        if climate_mode == CLIMATE_MODE_COOL_ONLY:
            target = cool_target
        elif climate_mode == CLIMATE_MODE_HEAT_ONLY:
            target = heat_target
        else:
            # Auto mode: show heat target (primary for chart line)
            target = heat_target

        result.append(
            {
                "ts": round(ts, 1),
                "target_temp": target,
                "heat_target": heat_target,
                "cool_target": cool_target,
            }
        )
        ts += interval_minutes * 60
    return result


async def build_analytics_data(
    hass: HomeAssistant,
    area_id: str,
    range_key: str,
    store: Any,
    coordinator: Any,
    custom_start: float | None = None,
    custom_end: float | None = None,
) -> dict:
    """Build analytics response data for a room.

    This is the core data assembly extracted from websocket_get_analytics.
    """
    settings = store.get_settings()
    history_store = getattr(coordinator, "_history_store", None)

    # Read history data -- custom timestamps take precedence over range preset
    detail: list = []
    history: list = []
    if history_store:
        if custom_start is not None:
            detail = _csv_to_points(
                await hass.async_add_executor_job(history_store.read_detail, area_id, None, custom_start, custom_end)
            )
            history = _csv_to_points(
                await hass.async_add_executor_job(history_store.read_history, area_id, None, custom_start, custom_end)
            )
        else:
            max_age_map = {
                "12h": 43200,
                "24h": 86400,
                "2d": 172800,
                "7d": 604800,
                "14d": 1209600,
                "30d": 2592000,
                "90d": 7776000,
            }
            max_age = max_age_map.get(range_key, 43200)
            detail = _csv_to_points(await hass.async_add_executor_job(history_store.read_detail, area_id, max_age))
            history = _csv_to_points(await hass.async_add_executor_job(history_store.read_history, area_id, max_age))

    # Model info (only if estimator exists -- avoid auto-creating for unknown rooms)
    model_info: dict = {}
    mpc_active = False
    if coordinator:
        mgr = coordinator._model_manager
        if area_id in mgr._estimators:
            est = mgr._estimators[area_id]
            rc = est.get_model()
            pred_std_idle = est.prediction_std(0.0, 20.0, 15.0, 5.0)
            pred_std_heat = est.prediction_std(rc.Q_heat, 20.0, 10.0, 5.0)
            room_config = store.get_room(area_id) or {}
            has_ext_sensor = bool(room_config.get("temperature_sensor"))
            if has_ext_sensor:
                can_heat, can_cool = get_can_heat_cool(
                    room_config,
                    coordinator.outdoor_temp_effective,
                    acs_can_heat=check_acs_can_heat(hass, room_config),
                )
                T_out = (
                    coordinator.outdoor_temp_effective
                    if coordinator.outdoor_temp_effective is not None
                    else DEFAULT_OUTDOOR_TEMP_FALLBACK
                )
                mpc_active = is_mpc_active(mgr, area_id, can_heat, can_cool, 20.0, T_out)
            else:
                mpc_active = False
            # EKF uncertainty: sqrt(P[0][0]) as proxy for sigma_e
            sigma_proxy = math.sqrt(max(est._P[0][0], 0.0))
            has_occupancy_sensors = len(room_config.get("occupancy_sensors", [])) > 0
            model_info = {
                "confidence": est.confidence,
                "model": rc.to_dict(),
                "n_samples": est._n_updates,
                "n_observations": est._n_updates,
                "n_heating": est._n_heating,
                "n_cooling": est._n_cooling,
                "applicable_modes": sorted(est._applicable_modes),
                "mpc_active": mpc_active,
                "sigma_e": round(sigma_proxy, 4),
                "prediction_std_idle": round(pred_std_idle, 4),
                "prediction_std_heating": round(pred_std_heat, 4),
                "has_occupancy_sensors": has_occupancy_sensors,
            }

    # Build merged forecast: same format as history points, on a shared 5-min grid
    room_config = store.get_room(area_id) or {}
    mold_delta = 0.0
    if coordinator:
        live = coordinator.rooms.get(area_id, {})
        mold_delta = live.get("mold_prevention_delta", 0.0)
    try:
        target_forecast = await _compute_target_forecast(
            hass,
            room_config,
            settings,
            mold_prevention_delta=mold_delta,
            schedule_blocks_cache=getattr(coordinator, "_schedule_blocks_cache", None),
        )
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Target forecast computation failed for '%s'", area_id)
        target_forecast = []

    # Forward-simulate temperature prediction for the forecast period.
    from ..control.analytics_simulator import (
        build_forecast_outdoor_series,
        build_forecast_solar_series,
        simulate_prediction,
    )

    pred_temps: list[float | None] = list()
    prediction_enabled = settings.get("prediction_enabled", True)
    if prediction_enabled and target_forecast and coordinator:
        mgr = coordinator._model_manager
        if area_id in mgr._estimators:
            model = mgr.get_model(area_id)
            est = mgr._estimators[area_id]
            all_points = detail if detail else history
            current_t: float | None = None
            for p in reversed(all_points):
                if p.get("room_temp") is not None:
                    current_t = p["room_temp"]
                    break
            if current_t is not None:
                T_out_now = (
                    coordinator.outdoor_temp_effective
                    if coordinator.outdoor_temp_effective is not None
                    else DEFAULT_OUTDOOR_TEMP_FALLBACK
                )
                outdoor_series = build_forecast_outdoor_series(
                    coordinator._weather_manager._outdoor_forecast,
                    T_out_now,
                    len(target_forecast),
                )
                # Shading factor from current cover positions
                live = coordinator.rooms.get(area_id, {})
                _shading = 1.0
                if live.get("blind_position") is not None:
                    from ..managers.cover_manager import compute_shading_factor

                    _shading = compute_shading_factor([live["blind_position"]])
                solar_series = build_forecast_solar_series(
                    hass.config.latitude,
                    hass.config.longitude,
                    coordinator._weather_manager._outdoor_forecast,
                    len(target_forecast),
                    shading_factor=_shading,
                )
                # Residual heat state for analytics simulation
                system_type = room_config.get("heating_system_type", "")
                sim_q_residual = 0.0
                sim_heat_dur = 0.0
                sim_last_pf = 1.0
                if system_type and area_id in getattr(coordinator._residual_tracker, "_off_since", {}):
                    import time as _time

                    off_since = coordinator._residual_tracker._off_since[area_id]
                    elapsed = (_time.time() - off_since) / 60.0
                    sim_heat_dur = (off_since - coordinator._residual_tracker._on_since.get(area_id, off_since)) / 60.0
                    sim_last_pf = coordinator._residual_tracker._off_power.get(area_id, 1.0)
                    from ..control.residual_heat import compute_residual_heat

                    sim_q_residual = compute_residual_heat(elapsed, system_type, sim_last_pf, sim_heat_dur)

                sim_q_occupancy = 0.0
                for occ_eid in room_config.get("occupancy_sensors", []):
                    occ_state = hass.states.get(occ_eid)
                    if occ_state and occ_state.state == "on":
                        sim_q_occupancy = 1.0
                        break

                pred_temps = cast(
                    list[float | None],
                    simulate_prediction(
                        model=model,
                        estimator=est,
                        target_forecast=target_forecast,
                        outdoor_series=outdoor_series,
                        current_temp=current_t,
                        window_open=coordinator._window_manager._paused.get(area_id, False),
                        mpc_active=mpc_active,
                        room_config=room_config,
                        settings=settings,
                        all_points=all_points,
                        solar_series=solar_series,
                        acs_can_heat=check_acs_can_heat(hass, room_config),
                        q_residual=sim_q_residual,
                        heating_system_type=system_type,
                        heating_duration_minutes=sim_heat_dur,
                        last_power_fraction=sim_last_pf,
                        q_occupancy=sim_q_occupancy,
                    ),
                )

    # Use the same future temperature/outdoor trajectory to predict electrical
    # demand. This keeps the energy chart coupled to RoomMind's learned thermal
    # forecast instead of extrapolating watts independently.
    predicted_powers: list[float | None] = []
    predicted_device_powers: list[dict[str, float]] = []
    predicted_confidences: list[str | None] = []
    energy_manager = (
        vars(coordinator).get("_energy_manager") if coordinator and hasattr(coordinator, "__dict__") else None
    )
    has_power_sensors = any(
        dev.get("type") == "ac" and dev.get("power_sensor_entity_id") for dev in room_config.get("devices", [])
    )
    if energy_manager is not None and target_forecast and has_power_sensors:
        live = coordinator.rooms.get(area_id, {})
        humidity = _safe_float(str(live.get("current_humidity") or ""))
        nominal = _safe_float(str(room_config.get("heat_pump_power_watts") or ""))
        selected_mode = str(room_config.get("room_hvac_mode") or "auto")
        for i, tf in enumerate(target_forecast):
            predicted_t = pred_temps[i] if i < len(pred_temps) else None
            heat_target = tf.get("heat_target")
            cool_target = tf.get("cool_target")
            if selected_mode == "dry":
                energy_mode = "dry"
                target_for_energy = cool_target or tf.get("target_temp")
            elif selected_mode == "heat":
                energy_mode = "heating"
                target_for_energy = heat_target or tf.get("target_temp")
            elif selected_mode == "cool":
                energy_mode = "cooling"
                target_for_energy = cool_target or tf.get("target_temp")
            elif selected_mode == "fan_only":
                # Fan-only has no compressor demand model. Keep its energy
                # analytics idle rather than fabricating a zero/nominal forecast.
                energy_mode = "idle"
                target_for_energy = tf.get("target_temp")
            elif selected_mode == "off":
                energy_mode = "idle"
                target_for_energy = tf.get("target_temp")
            else:
                if predicted_t is not None and heat_target is not None and predicted_t < heat_target:
                    energy_mode = "heating"
                    target_for_energy = heat_target
                elif predicted_t is not None and cool_target is not None and predicted_t > cool_target:
                    energy_mode = "cooling"
                    target_for_energy = cool_target
                else:
                    energy_mode = "idle"
                    target_for_energy = tf.get("target_temp")
            outdoor_for_energy = (
                outdoor_series[i]
                if "outdoor_series" in locals() and i < len(outdoor_series)
                else coordinator.outdoor_temp_effective
            )
            power, samples = energy_manager.predict_power(
                area_id,
                energy_mode,
                predicted_t,
                target_for_energy,
                outdoor_for_energy,
                humidity,
                nominal,
            )
            predicted_powers.append(round(power, 1) if power is not None else None)
            predicted_confidences.append(energy_manager.prediction_confidence(power, samples))
            predicted_device_powers.append(
                energy_manager.predict_device_power(
                    area_id,
                    energy_mode,
                    predicted_t,
                    target_for_energy,
                    outdoor_for_energy,
                    humidity,
                )
            )

    # Merge into unified forecast points on shared 5-min grid
    forecast: list[dict] = []
    grid = 300  # 5 minutes
    for i, tf in enumerate(target_forecast):
        snapped = round(tf["ts"] / grid) * grid
        forecast.append(
            {
                "ts": snapped,
                "room_temp": None,
                "outdoor_temp": None,
                "target_temp": tf["target_temp"],
                "mode": "forecast",
                "predicted_temp": pred_temps[i] if i < len(pred_temps) else None,
                "window_open": False,
                "device_setpoint": None,
                "predicted_power_w": predicted_powers[i] if i < len(predicted_powers) else None,
                "predicted_device_power_w": (predicted_device_powers[i] if i < len(predicted_device_powers) else {}),
                "energy_prediction_confidence": (
                    predicted_confidences[i] if i < len(predicted_confidences) else None
                ),
            }
        )

    price = max(0.0, float(settings.get("energy_price_per_kwh", 0) or 0))
    energy_cost: dict[str, float] | None = None
    if price > 0:
        cost_points = history + detail
        if history_store:
            week_age = 7 * 24 * 3600
            cost_points = _csv_to_points(
                await hass.async_add_executor_job(history_store.read_history, area_id, week_age)
            ) + _csv_to_points(await hass.async_add_executor_job(history_store.read_detail, area_id, week_age))
        now = time.time()
        today_start = datetime.fromtimestamp(now).astimezone().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        energy_cost = {
            "price_eur_kwh": price,
            "today_eur": round(_integrate_power_kwh(cost_points, today_start) * price, 2),
            "last_7d_eur": round(_integrate_power_kwh(cost_points, now - 7 * 24 * 3600) * price, 2),
            "forecast_3h_eur": round(_integrate_forecast_kwh(forecast) * price, 2),
        }

    return {
        "detail": detail,
        "history": history,
        "model": model_info,
        "forecast": forecast,
        "energy_cost": energy_cost,
    }
