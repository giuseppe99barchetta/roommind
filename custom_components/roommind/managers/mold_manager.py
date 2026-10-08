"""Mold risk detection and prevention manager for RoomMind."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.core import HomeAssistant

from ..const import (
    DEFAULT_MOLD_COOLDOWN_MINUTES,
    DEFAULT_MOLD_F_RSI,
    DEFAULT_MOLD_HUMIDITY_THRESHOLD,
    DEFAULT_MOLD_PREVENTION_SUSTAINED_MINUTES,
    DEFAULT_MOLD_SUSTAINED_MINUTES,
    DEFAULT_OUTDOOR_HEATING_MAX,
    MOLD_EXPOSURE_HIGH_HOURS,
    MOLD_HYSTERESIS,
    MOLD_PREVENTION_CRITICAL_SUSTAINED_MINUTES,
    MOLD_PREVENTION_DRY_STOP_TEMPERATURE,
    MOLD_PREVENTION_EARLY_SUSTAINED_MINUTES,
    MOLD_PREVENTION_HEAT_BELOW_TEMPERATURE,
    MOLD_PREVENTION_HEAT_TARGETS,
    MOLD_PREVENTION_MAX_RUN_MINUTES,
    MOLD_PREVENTION_MIN_RUN_MINUTES,
    MOLD_PREVENTION_NO_DRY_HEAT_TARGETS,
    MOLD_PREVENTION_PRE_NIGHT_SUSTAINED_MINUTES,
    MOLD_PREVENTION_REHEAT_MAX_RUN_MINUTES,
    MOLD_PREVENTION_RETRY_MINUTES,
    MOLD_RISK_CRITICAL,
    MOLD_RISK_OK,
    MOLD_RISK_WARNING,
    MOLD_SURFACE_RH_EARLY,
    MOLD_SURFACE_RH_WARNING,
)
from ..utils.mold_utils import (
    airing_recommended,
    calculate_mold_risk,
    dry_start_temperature,
    mold_prevention_delta,
)
from ..utils.notification_utils import (
    NotificationThrottler,
    async_send_mold_notification,
    dismiss_mold_notification,
)

_LOGGER = logging.getLogger(__name__)


# Restart recovery: rows are written every ~3 min; a longer hole means the
# condition was not observed and its timer must restart.
MOLD_BOOTSTRAP_MAX_GAP_SECONDS = 15 * 60


def _risk_flags(
    t_room: float,
    rh_room: float,
    t_outdoor: float | None,
    threshold: float,
    f_rsi: float = DEFAULT_MOLD_F_RSI,
) -> tuple[str, float, dict[str, bool]]:
    """Return (risk_level, surface_rh, timer conditions) for one observation."""
    risk_level, surface_rh = calculate_mold_risk(t_room, rh_room, t_outdoor, f_rsi)
    surface_risky = risk_level in (MOLD_RISK_WARNING, MOLD_RISK_CRITICAL)
    return (
        risk_level,
        surface_rh,
        {
            "risk": rh_room >= threshold or surface_risky,
            # Early dry-only intervention is intentionally more conservative
            # than an alarm: the surface estimate is not a moisture measurement.
            "early_risk": surface_rh >= MOLD_SURFACE_RH_EARLY and rh_room >= 60.0,
            "surface_risk": surface_risky,
            "critical_risk": risk_level == MOLD_RISK_CRITICAL,
        },
    )


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# Notification texts: Italian for Italian installs, English otherwise.
_TEXTS: dict[str, dict[str, str]] = {
    "it": {
        "risk_title": "RoomMind: rischio muffa – {room}",
        "risk_body": "Parete più fredda stimata al {srh}% di umidità (aria al {rh}%).",
        "advice_airing": "Apri le finestre 5–10 minuti: fuori l'aria è più secca.",
        "advice_dry": "Se il rischio continua il condizionatore deumidificherà in automatico.",
        "advice_no_dry": "Tieni chiusa la porta, asciuga le superfici bagnate ed evita panni stesi in casa.",
        "exposure": "Ultimi 7 giorni: {hours} h con la parete all'80% o più.",
        "prevention_title": "RoomMind: prevenzione muffa – {room}",
        "prevention_dry": "Avviato il DRY del condizionatore (parete al {srh}%).",
        "prevention_reheat": "DRY alternato al riscaldamento della pompa di calore, termosifoni spenti "
        "(parete al {srh}%).",
        "prevention_heat": "Riscaldamento attivato per scaldare le pareti fredde (parete al {srh}%).",
        "prevention_cool": "Raffrescamento attivato per deumidificare (parete al {srh}%).",
    },
    "en": {
        "risk_title": "RoomMind: Mold Risk Warning",
        "risk_body": "Coldest wall estimated at {srh}% humidity (air {rh}%).",
        "advice_airing": "Open the windows for 5–10 minutes: the outdoor air is drier.",
        "advice_dry": "If the risk persists the AC will dehumidify automatically.",
        "advice_no_dry": "Keep the door closed, wipe wet surfaces and avoid drying laundry indoors.",
        "exposure": "Last 7 days: {hours} h with the wall at 80% or more.",
        "prevention_title": "RoomMind: Mold Prevention",
        "prevention_dry": "AC dry mode started (wall at {srh}%).",
        "prevention_reheat": "DRY alternating with heat-pump heating, radiators off (wall at {srh}%).",
        "prevention_heat": "Heating started to warm the cold walls (wall at {srh}%).",
        "prevention_cool": "Cooling started to dehumidify (wall at {srh}%).",
    },
}


@dataclass
class MoldResult:
    """Result of mold risk evaluation for a room."""

    risk_level: str = MOLD_RISK_OK
    surface_rh: float | None = None
    prevention_active: bool = False
    prevention_delta: float = 0.0
    prevention_strategy: str | None = None
    heat_target: float | None = None


class MoldManager:
    """Manages mold risk detection and prevention per room."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._risk_since: dict[str, float] = {}
        self._prevention_active: dict[str, bool] = {}
        self._surface_risk_since: dict[str, float] = {}
        self._early_risk_since: dict[str, float] = {}
        self._critical_risk_since: dict[str, float] = {}
        self._prevention_started: dict[str, float] = {}
        self._prevention_cooldown_until: dict[str, float] = {}
        self._prevention_strategy: dict[str, str] = {}
        self._throttler = NotificationThrottler()

    async def evaluate(
        self,
        area_id: str,
        area_name: str,
        current_temp: float | None,
        current_humidity: float | None,
        outdoor_temp: float | None,
        settings: dict,
        can_dry: bool = False,
        can_cool: bool = False,
        can_heat_pump: bool = False,
        night_phase: str | None = None,
        window_open: bool = False,
        f_rsi: float = DEFAULT_MOLD_F_RSI,
        exposure_hours: float | None = None,
        outdoor_humidity: float | None = None,
        automation_enabled: bool = True,
        celsius_delta_to_ha_fn: Callable[[float], float] | None = None,
        ha_temp_unit_str_fn: Callable[[], str] | None = None,
    ) -> MoldResult:
        """Evaluate mold risk and prevention for a room.

        Returns a MoldResult with risk level, surface RH, and prevention state.
        """
        result = MoldResult()

        if not (settings.get("mold_detection_enabled") or settings.get("mold_prevention_enabled")):
            return result

        if current_humidity is None or current_temp is None:
            return result

        threshold = settings.get(
            "mold_humidity_threshold",
            DEFAULT_MOLD_HUMIDITY_THRESHOLD,
        )
        risk_level, surface_rh, flags = _risk_flags(current_temp, current_humidity, outdoor_temp, threshold, f_rsi)
        result.risk_level = risk_level
        result.surface_rh = surface_rh

        now = time.time()
        is_risky = flags["risk"]
        sustained_minutes = settings.get(
            "mold_sustained_minutes",
            DEFAULT_MOLD_SUSTAINED_MINUTES,
        )

        if is_risky:
            if area_id not in self._risk_since:
                self._risk_since[area_id] = now

            sustained_seconds = now - self._risk_since[area_id]

            # Notify if sustained long enough
            if (
                settings.get("mold_detection_enabled")
                and settings.get("mold_notifications_enabled", True)
                and sustained_seconds >= sustained_minutes * 60
            ):
                cooldown = (
                    settings.get(
                        "mold_notification_cooldown",
                        DEFAULT_MOLD_COOLDOWN_MINUTES,
                    )
                    * 60
                )
                if self._throttler.should_send(
                    f"detect_{area_id}",
                    cooldown,
                ):
                    targets = settings.get("mold_notification_targets", [])
                    text = self._texts()
                    if airing_recommended(current_temp, current_humidity, outdoor_temp, outdoor_humidity, surface_rh):
                        advice = text["advice_airing"]
                    elif can_dry and settings.get("mold_prevention_enabled"):
                        advice = text["advice_dry"]
                    else:
                        advice = text["advice_no_dry"]
                    message = " ".join(
                        part
                        for part in (
                            text["risk_body"].format(srh=f"{surface_rh:.0f}", rh=f"{current_humidity:.0f}"),
                            advice,
                            text["exposure"].format(hours=f"{exposure_hours:.0f}") if exposure_hours else "",
                        )
                        if part
                    )
                    await async_send_mold_notification(
                        self.hass,
                        area_id,
                        area_name,
                        targets,
                        message=message,
                        title=text["risk_title"].format(room=area_name),
                        tag_suffix="risk",
                    )
                    self._throttler.record_sent(f"detect_{area_id}")

        else:
            # Detection timers are separate from the surface-risk automation:
            # the air humidity warning may be active below the surface threshold.
            self._risk_since.pop(area_id, None)
            self._throttler.clear(f"detect_{area_id}")

        early_risky = flags["early_risk"]
        if early_risky:
            self._early_risk_since.setdefault(area_id, now)
        else:
            self._early_risk_since.pop(area_id, None)

        surface_risky = flags["surface_risk"]
        if surface_risky:
            self._surface_risk_since.setdefault(area_id, now)
        else:
            self._surface_risk_since.pop(area_id, None)
        if risk_level == MOLD_RISK_CRITICAL:
            self._critical_risk_since.setdefault(area_id, now)
        else:
            self._critical_risk_since.pop(area_id, None)

        activated = self._prevention_active.get(area_id, False)
        sustained = (
            max(
                0.0,
                float(settings.get("mold_prevention_sustained_minutes", DEFAULT_MOLD_PREVENTION_SUSTAINED_MINUTES)),
            )
            * 60
        )
        critical_sustained = min(sustained, MOLD_PREVENTION_CRITICAL_SUSTAINED_MINUTES * 60)
        # A wall that already spent many hours near condensation this week
        # gets no grace period: the early zone acts sooner and also at night.
        high_exposure = (exposure_hours or 0.0) >= MOLD_EXPOSURE_HIGH_HOURS
        # Before a room's night window, dry the early zone sooner so the room
        # is dry at bedtime; during the night the early zone is left alone.
        early_sustained = (
            MOLD_PREVENTION_PRE_NIGHT_SUSTAINED_MINUTES
            if night_phase == "pre_night" or high_exposure
            else MOLD_PREVENTION_EARLY_SUSTAINED_MINUTES
        ) * 60
        ready = (
            surface_risky
            and (
                now - self._surface_risk_since[area_id] >= sustained
                or (risk_level == MOLD_RISK_CRITICAL and now - self._critical_risk_since[area_id] >= critical_sustained)
            )
        ) or (early_risky and now - self._early_risk_since[area_id] >= early_sustained)
        # Once active, hold for at least ten minutes (unless the room gets
        # too cold); later stop when the surface returns below the early zone.
        held = activated and (
            surface_rh >= MOLD_SURFACE_RH_WARNING - MOLD_HYSTERESIS
            or now - self._prevention_started.get(area_id, now) < MOLD_PREVENTION_MIN_RUN_MINUTES * 60
        )
        # Earlier RoomMind settings allowed DRY as low as 20°C. Respect any
        # *higher* user threshold, but enforce the new 22°C safety minimum.
        dry_min_temperature = dry_start_temperature(settings)
        dry_stop_temperature = max(MOLD_PREVENTION_DRY_STOP_TEMPERATURE, dry_min_temperature - 1.0)
        dehumidification_enabled = settings.get("mold_prevention_dehumidification_enabled", True)
        # Optional DRY/heat-pump alternation: when DRY has cooled the room to
        # its stop temperature, the same AC heats it back (boiler stays off)
        # instead of abandoning dehumidification for an hour.
        reheat_allowed = bool(
            settings.get("mold_prevention_reheat_enabled", False)
            and dehumidification_enabled
            and can_dry
            and can_heat_pump
        )
        max_run_minutes = MOLD_PREVENTION_REHEAT_MAX_RUN_MINUTES if reheat_allowed else MOLD_PREVENTION_MAX_RUN_MINUTES
        cooling_down = now < self._prevention_cooldown_until.get(area_id, 0)
        # The runtime cap exists because DRY cools; a heating session is
        # bounded by its target and may run for as long as the wall needs it.
        timed_out = (
            activated
            and self._prevention_strategy.get(area_id) != "heat"
            and now - self._prevention_started.get(area_id, now) >= max_run_minutes * 60
        )
        dry_too_cold = (
            activated
            and not reheat_allowed
            and self._prevention_strategy.get(area_id) == "dry"
            and current_temp <= dry_stop_temperature
        )
        if timed_out or dry_too_cold:
            self._prevention_cooldown_until[area_id] = now + MOLD_PREVENTION_RETRY_MINUTES * 60
        # Quiet night: below the warning zone a sleeping room is not woken by
        # the compressor; timers keep running so DRY starts at night end.
        quiet_night = night_phase == "night" and not surface_risky and not high_exposure
        # An open window ends the session without a retry pause: nothing can
        # be dried meanwhile, so it must not burn the session's runtime cap.
        # Risk timers keep running and prevention resumes once it closes.
        should_prevent = bool(
            settings.get("mold_prevention_enabled")
            and automation_enabled
            and (ready or held)
            and not (cooling_down or timed_out or dry_too_cold or quiet_night or window_open)
        )
        if should_prevent:
            intensity = settings.get("mold_prevention_intensity", "medium")
            # A dry cycle can lower the room temperature.  Prefer it only
            # when explicitly enabled and the room has enough thermal
            # headroom; otherwise use the heating plan (which can route to
            # a heat pump, gas boiler, or both).
            continuing_dry = activated and self._prevention_strategy.get(area_id) == "dry"
            can_start_dry = current_temp >= dry_min_temperature
            can_continue_dry = continuing_dry and current_temp > dry_stop_temperature
            if dehumidification_enabled and can_dry and (can_start_dry or can_continue_dry):
                result.prevention_strategy = "dry"
                result.prevention_delta = 0.0
            elif reheat_allowed and current_temp >= MOLD_PREVENTION_HEAT_BELOW_TEMPERATURE:
                # Heat pump back up to the DRY start temperature (1 °C band
                # above the stop point), then the next tick resumes DRY.
                # ponytail: no coil-drain pause before HEAT; part of the
                # condensate film re-evaporates. Add a short off phase if
                # humidity rebounds after each switch.
                result.prevention_strategy = "reheat"
                result.prevention_delta = 0.0
            elif (
                surface_risky
                and not can_dry
                and outdoor_temp is not None
                and outdoor_temp < float(settings.get("outdoor_heating_max", DEFAULT_OUTDOOR_HEATING_MAX))
                and current_temp < MOLD_PREVENTION_NO_DRY_HEAT_TARGETS.get(intensity, 21.5)
            ):
                # No DRY available (radiators only, e.g. a bathroom): in the
                # heating season warmer walls are the only way to stop
                # condensation, so allow a slightly higher target.
                result.prevention_strategy = "heat"
                result.prevention_delta = mold_prevention_delta(intensity)
                result.heat_target = MOLD_PREVENTION_NO_DRY_HEAT_TARGETS.get(intensity, 21.5)
            elif surface_risky and current_temp < MOLD_PREVENTION_HEAT_BELOW_TEMPERATURE:
                # Heating only makes sense for genuinely cold rooms; cooling
                # mode is NOT a substitute for dry on an unregulated AC.
                result.prevention_strategy = "heat"
                result.prevention_delta = mold_prevention_delta(intensity)
                result.heat_target = MOLD_PREVENTION_HEAT_TARGETS.get(intensity, 20.5)

            if result.prevention_strategy is None:
                should_prevent = False

        if should_prevent:
            if not activated:
                self._prevention_active[area_id] = True
                self._prevention_started[area_id] = now
                # Sessions can restart often (window, night, DRY/HEAT limits):
                # announce at most once per notification cooldown.
                if (
                    settings.get("mold_prevention_notify_enabled")
                    and settings.get("mold_notifications_enabled", True)
                    and celsius_delta_to_ha_fn is not None
                    and ha_temp_unit_str_fn is not None
                    and self._throttler.should_send(
                        f"prevent_{area_id}",
                        settings.get("mold_notification_cooldown", DEFAULT_MOLD_COOLDOWN_MINUTES) * 60,
                    )
                ):
                    prev_targets = settings.get(
                        "mold_prevention_notify_targets",
                        [],
                    )
                    text = self._texts()
                    await async_send_mold_notification(
                        self.hass,
                        area_id,
                        area_name,
                        prev_targets,
                        message=text[f"prevention_{result.prevention_strategy}"].format(srh=f"{surface_rh:.0f}"),
                        title=text["prevention_title"].format(room=area_name),
                        tag_suffix="prevention",
                    )
                    self._throttler.record_sent(
                        f"prevent_{area_id}",
                    )
            self._prevention_strategy[area_id] = result.prevention_strategy
            result.prevention_active = True
        elif activated:
            self._prevention_active.pop(area_id, None)
            self._prevention_started.pop(area_id, None)
            self._prevention_strategy.pop(area_id, None)
            dismiss_mold_notification(self.hass, area_id, "prevention")

        if not is_risky and surface_rh < MOLD_SURFACE_RH_WARNING - MOLD_HYSTERESIS:
            dismiss_mold_notification(self.hass, area_id, "risk")

        return result

    def _texts(self) -> dict[str, str]:
        language = getattr(self.hass.config, "language", None)
        return _TEXTS["it"] if isinstance(language, str) and language.startswith("it") else _TEXTS["en"]

    def remove_room(self, area_id: str) -> None:
        """Clean up state for a removed room."""
        self._risk_since.pop(area_id, None)
        self._prevention_active.pop(area_id, None)
        self._surface_risk_since.pop(area_id, None)
        self._early_risk_since.pop(area_id, None)
        self._critical_risk_since.pop(area_id, None)
        self._prevention_started.pop(area_id, None)
        self._prevention_cooldown_until.pop(area_id, None)
        self._prevention_strategy.pop(area_id, None)
        self._throttler.clear(f"detect_{area_id}")
        self._throttler.clear(f"prevent_{area_id}")

    def bootstrap(
        self,
        area_id: str,
        rows: list[dict],
        settings: dict,
        now: float | None = None,
        f_rsi: float = DEFAULT_MOLD_F_RSI,
    ) -> None:
        """Rebuild risk timers from persisted history after a restart.

        Without this, every Home Assistant restart would restart the 1–2 hour
        persistence windows even though the room has been humid all along.
        Only the latest uninterrupted run that reaches (almost) now counts.
        """
        now = time.time() if now is None else now
        threshold = settings.get("mold_humidity_threshold", DEFAULT_MOLD_HUMIDITY_THRESHOLD)
        samples = sorted(
            (ts, t, rh, _as_float(row.get("outdoor_temp")))
            for row in rows
            if (ts := _as_float(row.get("timestamp"))) is not None
            and (t := _as_float(row.get("room_temp"))) is not None
            and (rh := _as_float(row.get("current_humidity"))) is not None
        )
        if not samples or now - samples[-1][0] > MOLD_BOOTSTRAP_MAX_GAP_SECONDS:
            return
        since: dict[str, float] = {}
        previous_ts: float | None = None
        for ts, t, rh, t_out in samples:
            if previous_ts is not None and ts - previous_ts > MOLD_BOOTSTRAP_MAX_GAP_SECONDS:
                since.clear()
            previous_ts = ts
            for name, active in _risk_flags(t, rh, t_out, threshold, f_rsi)[2].items():
                if active:
                    since.setdefault(name, ts)
                else:
                    since.pop(name, None)
        timers = {
            "risk": self._risk_since,
            "early_risk": self._early_risk_since,
            "surface_risk": self._surface_risk_since,
            "critical_risk": self._critical_risk_since,
        }
        for name, started in since.items():
            timers[name].setdefault(area_id, started)
        if "risk" in since:
            # A sustained risk was already announced before the restart.
            self._throttler.record_sent(f"detect_{area_id}")

    def dry_retry_blocked(self, area_id: str) -> bool:
        """Share the anti-mold cooldown with the independent humidity-control path."""
        return time.time() < self._prevention_cooldown_until.get(area_id, 0)
