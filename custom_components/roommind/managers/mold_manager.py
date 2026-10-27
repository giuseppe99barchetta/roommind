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
    MOLD_DEHUMIDIFY_MIN_RH,
    MOLD_DRY_MIN_EFFECT_RH,
    MOLD_EXPOSURE_HIGH_HOURS,
    MOLD_HYSTERESIS,
    MOLD_PREVENTION_CRITICAL_SUSTAINED_MINUTES,
    MOLD_PREVENTION_DRY_STOP_TEMPERATURE,
    MOLD_PREVENTION_INEFFECTIVE_RETRY_MINUTES,
    MOLD_PREVENTION_MAX_RUN_MINUTES,
    MOLD_PREVENTION_MIN_RUN_MINUTES,
    MOLD_PREVENTION_RETRY_MINUTES,
    MOLD_RISK_CRITICAL,
    MOLD_RISK_OK,
    MOLD_RISK_WARNING,
    MOLD_SURFACE_RH_EARLY,
    MOLD_SURFACE_RH_WARNING,
)
from ..utils.mold_utils import (
    air_rh_for_surface,
    airing_recommended,
    calculate_mold_risk,
    dry_start_temperature,
    estimate_surface_temp,
    smooth_outdoor,
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
            # Only a dedicated dehumidifier acts this early (no thermal side effect).
            "early_risk": surface_rh >= MOLD_SURFACE_RH_EARLY,
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
        "advice_dehumidifier": "Se il rischio continua il deumidificatore partirà in automatico.",
        "advice_no_dry": "Tieni chiusa la porta, asciuga le superfici bagnate ed evita panni stesi in casa.",
        "exposure": "Ultimi 7 giorni: {hours} h con la parete all'80% o più.",
        "prevention_title": "RoomMind: prevenzione muffa – {room}",
        "prevention_dehumidifier": "Richiesta deumidificazione dedicata (parete al {srh}%).",
        "prevention_dry": "Avviato il DRY del condizionatore (parete al {srh}%).",
    },
    "en": {
        "risk_title": "RoomMind: Mold Risk Warning",
        "risk_body": "Coldest wall estimated at {srh}% humidity (air {rh}%).",
        "advice_airing": "Open the windows for 5–10 minutes: the outdoor air is drier.",
        "advice_dry": "If the risk persists the AC will dehumidify automatically.",
        "advice_dehumidifier": "If the risk persists the dehumidifier will start automatically.",
        "advice_no_dry": "Keep the door closed, wipe wet surfaces and avoid drying laundry indoors.",
        "exposure": "Last 7 days: {hours} h with the wall at 80% or more.",
        "prevention_title": "RoomMind: Mold Prevention",
        "prevention_dehumidifier": "Dedicated dehumidification requested (wall at {srh}%).",
        "prevention_dry": "AC dry mode started (wall at {srh}%).",
    },
}


@dataclass
class MoldResult:
    """Result of mold risk evaluation for a room."""

    risk_level: str = MOLD_RISK_OK
    surface_rh: float | None = None
    prevention_active: bool = False
    prevention_strategy: str | None = None
    # Air RH a dedicated dehumidifier must reach to dry the wall (mold runs).
    dehumidify_target: float | None = None


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
        self._dry_start_rh: dict[str, float] = {}
        # Smoothed outdoor temperature shared by all rooms: (value, timestamp).
        self._outdoor_ema: tuple[float | None, float | None] = (None, None)
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
        night_phase: str | None = None,
        window_open: bool = False,
        f_rsi: float = DEFAULT_MOLD_F_RSI,
        exposure_hours: float | None = None,
        outdoor_humidity: float | None = None,
        automation_enabled: bool = True,
        celsius_delta_to_ha_fn: Callable[[float], float] | None = None,
        ha_temp_unit_str_fn: Callable[[], str] | None = None,
        can_dehumidifier: bool = False,
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
        now = time.time()
        if outdoor_temp is not None:
            self._outdoor_ema = (smooth_outdoor(*self._outdoor_ema, outdoor_temp, now), now)
        risk_level, surface_rh, flags = _risk_flags(
            current_temp, current_humidity, self._outdoor_ema[0], threshold, f_rsi
        )
        result.risk_level = risk_level
        result.surface_rh = surface_rh

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
                    prevention_on = settings.get("mold_prevention_enabled") and settings.get(
                        "mold_prevention_dehumidification_enabled", True
                    )
                    if airing_recommended(current_temp, current_humidity, outdoor_temp, outdoor_humidity, surface_rh):
                        advice = text["advice_airing"]
                    elif prevention_on and can_dehumidifier:
                        advice = text["advice_dehumidifier"]
                    elif prevention_on and can_dry and current_temp >= dry_start_temperature(settings):
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

        surface_risky = flags["surface_risk"]
        if surface_risky:
            self._surface_risk_since.setdefault(area_id, now)
        else:
            self._surface_risk_since.pop(area_id, None)
        if risk_level == MOLD_RISK_CRITICAL:
            self._critical_risk_since.setdefault(area_id, now)
        else:
            self._critical_risk_since.pop(area_id, None)
        if flags["early_risk"]:
            self._early_risk_since.setdefault(area_id, now)
        else:
            self._early_risk_since.pop(area_id, None)

        activated = self._prevention_active.get(area_id, False)
        dehumidification_enabled = settings.get("mold_prevention_dehumidification_enabled", True)
        use_dehumidifier = bool(dehumidification_enabled and can_dehumidifier)
        sustained = (
            max(
                0.0,
                float(settings.get("mold_prevention_sustained_minutes", DEFAULT_MOLD_PREVENTION_SUSTAINED_MINUTES)),
            )
            * 60
        )
        critical_sustained = min(sustained, MOLD_PREVENTION_CRITICAL_SUSTAINED_MINUTES * 60)
        ready = (
            surface_risky
            and (
                now - self._surface_risk_since[area_id] >= sustained
                or (risk_level == MOLD_RISK_CRITICAL and now - self._critical_risk_since[area_id] >= critical_sustained)
            )
        ) or (use_dehumidifier and flags["early_risk"] and now - self._early_risk_since[area_id] >= sustained)
        # Once active, hold for at least ten minutes (unless the room gets
        # too cold); later stop when the surface is clearly below the start zone.
        start_zone = MOLD_SURFACE_RH_EARLY if use_dehumidifier else MOLD_SURFACE_RH_WARNING
        held = activated and (
            surface_rh >= start_zone - MOLD_HYSTERESIS
            or now - self._prevention_started.get(area_id, now) < MOLD_PREVENTION_MIN_RUN_MINUTES * 60
        )
        # Earlier RoomMind settings allowed DRY as low as 20°C. Respect any
        # *higher* user threshold, but enforce the new 22°C safety minimum.
        dry_min_temperature = dry_start_temperature(settings)
        dry_stop_temperature = max(MOLD_PREVENTION_DRY_STOP_TEMPERATURE, dry_min_temperature - 1.0)
        cooling_down = now < self._prevention_cooldown_until.get(area_id, 0)
        timed_out = (
            activated
            and not can_dehumidifier
            and now - self._prevention_started.get(area_id, now) >= MOLD_PREVENTION_MAX_RUN_MINUTES * 60
        )
        dry_too_cold = activated and not can_dehumidifier and current_temp <= dry_stop_temperature
        if timed_out or dry_too_cold:
            retry = MOLD_PREVENTION_RETRY_MINUTES
            start_rh = self._dry_start_rh.get(area_id)
            # A full DRY run that barely moved the air RH means the air is
            # already dry: repeating it every hour only cools the room.
            if timed_out and start_rh is not None and current_humidity > start_rh - MOLD_DRY_MIN_EFFECT_RH:
                retry = MOLD_PREVENTION_INEFFECTIVE_RETRY_MINUTES
            self._prevention_cooldown_until[area_id] = now + retry * 60
        # At night the AC compressor only runs for a serious risk: a critical
        # wall or one that spent many hours near condensation this week.
        # (A dedicated dehumidifier gets no night_phase and may run anyway.)
        serious = risk_level == MOLD_RISK_CRITICAL or (exposure_hours or 0.0) >= MOLD_EXPOSURE_HIGH_HOURS
        quiet_night = night_phase == "night" and not serious
        # An open window ends the session without a retry pause: nothing can
        # be dried meanwhile, so it must not burn the session's runtime cap.
        # Risk timers keep running and prevention resumes once it closes.
        should_prevent = bool(
            settings.get("mold_prevention_enabled")
            and automation_enabled
            and (ready or held)
            and not ((cooling_down and not can_dehumidifier) or timed_out or dry_too_cold or quiet_night or window_open)
        )
        if should_prevent:
            # Prevention only removes water: it never heats (no heat pump, no
            # boiler).  Without a dehumidifier or a warm-enough room for DRY,
            # the risk notification with its advice is all that happens.
            continuing_dry = activated and self._prevention_strategy.get(area_id) == "dry"
            if use_dehumidifier:
                result.prevention_strategy = "dehumidifier"
                if self._outdoor_ema[0] is not None:
                    # Aim the device's own humidistat at what the wall needs,
                    # not at the comfort target (it would stop too early).
                    wall = estimate_surface_temp(current_temp, self._outdoor_ema[0], f_rsi)
                    needed = air_rh_for_surface(current_temp, wall, MOLD_SURFACE_RH_EARLY - MOLD_HYSTERESIS)
                    result.dehumidify_target = round(max(MOLD_DEHUMIDIFY_MIN_RH, needed))
            elif (
                dehumidification_enabled
                and can_dry
                and (current_temp >= dry_min_temperature or (continuing_dry and current_temp > dry_stop_temperature))
            ):
                result.prevention_strategy = "dry"
            else:
                should_prevent = False

        if should_prevent:
            if not activated:
                self._prevention_active[area_id] = True
                self._prevention_started[area_id] = now
                self._dry_start_rh[area_id] = current_humidity
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
            self._dry_start_rh.pop(area_id, None)
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
        self._dry_start_rh.pop(area_id, None)
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
        smoothed: float | None = None
        smoothed_ts: float | None = None
        for ts, t, rh, t_out in samples:
            if previous_ts is not None and ts - previous_ts > MOLD_BOOTSTRAP_MAX_GAP_SECONDS:
                since.clear()
            previous_ts = ts
            if t_out is not None:
                smoothed, smoothed_ts = smooth_outdoor(smoothed, smoothed_ts, t_out, ts), ts
            for name, active in _risk_flags(t, rh, smoothed, threshold, f_rsi)[2].items():
                if active:
                    since.setdefault(name, ts)
                else:
                    since.pop(name, None)
        if smoothed_ts is not None and (self._outdoor_ema[1] is None or smoothed_ts > self._outdoor_ema[1]):
            self._outdoor_ema = (smoothed, smoothed_ts)
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
