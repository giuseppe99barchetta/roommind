"""One control owner for local and shared physical dehumidifiers."""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, field
from time import monotonic, time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from ..const import (
    DEHUMIDIFIER_USER_OFF_MINUTES,
    MOLD_RISK_CRITICAL,
    MOLD_RISK_WARNING,
    MOLD_SURFACE_RH_EARLY,
    make_roommind_context,
)
from ..utils.dehumidifier_forecast import DEFAULT_K, K_MAX, heat_gain_c, minutes_to_target, observed_k
from ..utils.humidity_targets import current_season, room_humidity_target
from ..utils.night_mode import night_phase
from .power_budget_manager import PowerBudgetManager
from .window_manager import WindowManager

_LOGGER = logging.getLogger(__name__)

FAN_NIGHT = "low"
# Day fan speed from how far the air is above its target (RH points) and from wall risk.
FAN_LEVELS = ("low", "medium", "high")
FAN_STEPS = (4.0, 9.0)  # gap that raises the level to medium / high
FAN_HYSTERESIS = 2.0  # points the gap must fall below a step before the level drops
MOLD_OVERDRY_MARGIN = 5.0  # RH points below comfort target where mold drying stops
LEARN_WINDOW_S = 600.0  # measure the drying rate over at least 10 min (sensors are 1% coarse)
LEARN_ALPHA = 0.3  # weight of a new observation in the learned rate
SERVED_FACTOR = 0.5  # a served room dries slower than the host until its own rate is learned
LATENT_HEAT_RATIO = 0.8  # condensing water returns ~0.7-1.4 kWh per kWh drawn; a cautious mid-low value
COMFORT_STOP_MARGIN = 2.0  # comfort demand clears this many RH points above target
RUN_HISTORY = 10  # completed runs kept for the predicted-vs-actual readout


def served_areas(owner: str, config: dict) -> set[str]:
    """The device always serves its host, in addition to selected rooms."""
    return {owner, *config.get("served_area_ids", [])}


def humidity_target(room: dict, season: str | None = None) -> float | None:
    """Use the same opt-in, profile and seasonal targets as AC humidity comfort."""
    return room_humidity_target(room, season)


def fan_level(gap: float, previous: int) -> int:
    """Step up at once, step down only once the gap is clearly below the step."""
    level = sum(gap >= step for step in FAN_STEPS)
    return level if level > previous else min(previous, sum(gap >= step - FAN_HYSTERESIS for step in FAN_STEPS))


def valid_humidity(value: Any) -> float | None:
    """Reject missing, non-finite and impossible humidity readings."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and 0 <= number <= 100 else None


def _new_learning() -> dict:
    return {"k": list(DEFAULT_K), "k_n": [0] * len(DEFAULT_K), "areas": {}, "runs": []}


@dataclass
class DeviceRuntime:
    observed_on: bool
    on_since: float
    off_since: float
    floor_paused: bool = False
    command: bool | None = None
    command_at: float = -math.inf
    target: float | None = None
    target_at: float = -math.inf
    available: bool = True
    owned_on: bool = False
    user_off_until: float = -math.inf
    fan_at: float = -math.inf
    fan_sent: tuple[str, str] | None = None  # (option sent, state read back right after)
    fan_level: int = 1
    k: list[float] = field(default_factory=lambda: list(DEFAULT_K))  # learned drying rate per fan level
    k_n: list[int] = field(default_factory=lambda: [0, 0, 0])
    anchors: dict[str, tuple[float, float, int]] = field(default_factory=dict)  # area -> (RH, time, level)
    run: dict | None = None  # drying run being timed: area, target, start, predicted


class DehumidifierManager:
    """Collect requests first, allocate once, then command each physical device."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.lock = asyncio.Lock()
        self.devices: dict[str, dict] = {}
        self.runtime: dict[str, DeviceRuntime] = {}
        # Learned drying rates per entity; outlives runtime resets and is persisted by the store.
        self.learned: dict[str, dict] = {}
        self.dirty = False  # learning changed since the coordinator last persisted it
        self.assignments: dict[str, str] = {}
        self.requests: dict[str, str] = {}
        self._comfort: set[str] = set()
        self._mold_dry: set[str] = set()
        self._windows = WindowManager()
        self._previous_requests: dict[str, list[str]] = {}

    def room_humidity(self, room: dict, measured: float | None) -> float | None:
        """Only a host without a configured external sensor may use its device."""
        if room.get("humidity_sensor"):
            return valid_humidity(measured)
        config = room.get("dehumidifier") or {}
        eid = config.get("entity_id", "")
        state = self.hass.states.get(eid) if eid.startswith("humidifier.") else None
        if state is not None and state.state not in ("unknown", "unavailable"):
            return valid_humidity(state.attributes.get("current_humidity"))
        return valid_humidity(measured)

    def load_learned(self, data: dict) -> None:
        """Restore persisted drying rates, ignoring anything malformed."""
        size = len(DEFAULT_K)

        def rates(raw: Any) -> dict | None:
            try:
                k = [float(v) for v in raw["k"]]
                k_n = [int(v) for v in raw["k_n"]]
            except (KeyError, TypeError, ValueError, OverflowError):
                return None
            ok = len(k) == len(k_n) == size and all(0 < v <= K_MAX for v in k) and all(n >= 0 for n in k_n)
            return {"k": k, "k_n": k_n} if ok else None

        def number(value: Any) -> bool:
            return isinstance(value, (int, float)) and math.isfinite(value)

        if not isinstance(data, dict):
            return
        for eid, entry in data.items():
            own = rates(entry) if isinstance(entry, dict) else None
            if own is None:
                continue
            areas = {
                a: r
                for a, raw in (entry["areas"] if isinstance(entry.get("areas"), dict) else {}).items()
                if (r := rates(raw)) is not None
            }
            runs = [
                {"predicted": float(r["predicted"]), "actual": float(r["actual"])}
                for r in (entry["runs"] if isinstance(entry.get("runs"), list) else [])
                if isinstance(r, dict) and number(r.get("predicted")) and number(r.get("actual"))
            ][-RUN_HISTORY:]
            self.learned[eid] = {**own, "areas": areas, "runs": runs}
            if eid in self.runtime:
                self.runtime[eid].k, self.runtime[eid].k_n = own["k"], own["k_n"]

    def prepare(self, rooms: dict, settings: dict, humidities: dict, raw_windows: dict) -> None:
        """Snapshot availability and host constraints before evaluating any room."""
        self._previous_requests = {eid: d["requesting_rooms"] for eid, d in self.devices.items()}
        previous_owners = {d["owner_area_id"] for d in self.devices.values()}
        self.devices = {}
        self.assignments = {}
        self.requests = {}
        now = monotonic()
        for owner, room in sorted(rooms.items()):
            config = room.get("dehumidifier")
            if not config:
                continue
            eid = config["entity_id"]
            state = self.hass.states.get(eid)
            available = (
                state is not None
                and state.state in ("on", "off")
                and (not eid.startswith("humidifier.") or state.attributes.get("device_class") == "dehumidifier")
            )
            on = available and state.state == "on"
            learned = self.learned.setdefault(eid, _new_learning())
            runtime = self.runtime.setdefault(
                eid, DeviceRuntime(on, now, now, available=available, k=learned["k"], k_n=learned["k_n"])
            )
            if available and not runtime.available and not on:
                runtime.off_since = now
            was_available, runtime.available = runtime.available, available
            tank = self.hass.states.get(config.get("tank_full_entity") or "")
            tank_full = tank is not None and tank.state == "on"
            if available and on != runtime.observed_on:
                runtime.observed_on = on
                # The user stopping our run: respect it for a while. Ending their
                # own manual run hands control straight back; a full tank or a
                # device returning from unavailable is not the user.
                stopped_ours = (
                    not on and was_available and not tank_full and runtime.owned_on and runtime.command is not False
                )
                runtime.user_off_until = now + DEHUMIDIFIER_USER_OFF_MINUTES * 60 if stopped_ours else -math.inf
                # A physical OFF ends our run. A later manual ON must not
                # inherit ownership or a still-pending OFF command.
                if not on or runtime.command is not True:
                    runtime.owned_on = False
                    runtime.command = None
                    runtime.command_at = -math.inf
                if on:
                    runtime.on_since = now
                else:
                    runtime.off_since = now
            if tank_full:
                # The tank sensor may report after the OFF: it was not the user.
                runtime.user_off_until = -math.inf
            effective_on = runtime.command if now - runtime.command_at < 60 else on
            paused = self._windows.update(
                owner,
                raw_windows.get(owner, False),
                room.get("window_open_delay", 0),
                room.get("window_close_delay", 0),
            )
            areas = served_areas(owner, config) & rooms.keys()
            humidity = humidities.get(owner)
            target = self._native_target(eid, 45.0) if len(areas) > 1 else None
            floor = max(45.0, target or 45.0)
            if len(areas) > 1 and humidity is not None:
                if humidity <= floor:
                    runtime.floor_paused = True
                elif humidity >= floor + 5:
                    runtime.floor_paused = False
            elif len(areas) <= 1:
                runtime.floor_paused = False
            reason = None
            if config.get("mode", "auto") == "manual":
                runtime.owned_on = False
                runtime.command = None
                runtime.command_at = -math.inf
                reason = "manual"
            elif on and not runtime.owned_on:
                reason = "manual"
            elif (
                not settings.get("climate_control_active", True)
                or not room.get("climate_control_enabled", True)
                or room.get("is_outdoor", False)
            ):
                reason = "disabled"
            elif not available:
                reason = "unavailable"
            elif tank_full:
                reason = "tank_full"
            elif now < runtime.user_off_until:
                reason = "user_off"
            elif humidity is None:
                reason = "sensor"
            elif paused:
                reason = "window"
            elif runtime.floor_paused:
                reason = "humidity_floor"
            elif not effective_on and now - runtime.off_since < config.get("min_off_minutes", 5) * 60:
                reason = "min_off"
            self.devices[eid] = {
                "entity_id": eid,
                "owner_area_id": owner,
                "served_area_ids": sorted(areas),
                "mode": config.get("mode", "auto"),
                "available": available,
                "state": state.state if state else "unavailable",
                "action": state.attributes.get("action") if available else None,
                "reason": reason,
                "requesting_rooms": [],
                "requested": False,
                "commanded": None,
                "target_humidity": target,
                "humidity_floor": floor if len(areas) > 1 else None,
                "user_off_until": time() + runtime.user_off_until - now if reason == "user_off" else None,
                "night": night_phase(room, dt_util.now(), 0) == "night",
                "fan_speed": self._fan_speed(config),
                "config": config,
            }
        self._comfort.intersection_update(rooms)
        self._mold_dry.intersection_update(rooms)
        for owner in previous_owners - {d["owner_area_id"] for d in self.devices.values()}:
            self._windows.remove_room(owner)
        for eid in set(self.runtime) - self.devices.keys():
            self.runtime.pop(eid)
        for eid in set(self.learned) - self.devices.keys():
            self.learned.pop(eid)  # device no longer configured anywhere
            self.dirty = True

    def suppress_ac_dry(self, area_id: str) -> bool:
        """Only physical unavailability of every associated device permits fallback."""
        return any(
            area_id in d["served_area_ids"] and (d["available"] or d["reason"] in ("manual", "disabled"))
            for d in self.devices.values()
        )

    def collect(self, rooms: dict, humidities: dict, molds: dict) -> None:
        """Allocate each demand once; stable ordering makes overlaps deterministic."""
        season = current_season(self.hass)
        for area_id, room in sorted(rooms.items()):
            if room.get("is_outdoor") or not room.get("climate_control_enabled", True):
                self._comfort.discard(area_id)
                continue
            humidity = humidities.get(area_id)
            target = humidity_target(room, season)
            if humidity is None:
                self._comfort.discard(area_id)
                continue
            multiplier = {"comfort": 0.5, "balanced": 1.0, "energy": 1.5}.get(
                room.get("humidity_priority", "balanced"), 1.0
            )
            threshold = max(3.0, float(room.get("humidity_tolerance", 5) or 0) * multiplier)
            if target is None or humidity <= target + 2:
                self._comfort.discard(area_id)
            elif humidity >= target + threshold:
                self._comfort.add(area_id)
            mold = molds.get(area_id)
            mold_request = bool(mold and mold[2] and mold[3] == "dehumidifier")
            # Air already well below comfort: a still-humid wall must not over-dry the room.
            # Hysteresis (stop at -5, resume above -3) avoids on/off chatter.
            if mold_request and target is not None:
                if humidity <= target - MOLD_OVERDRY_MARGIN:
                    self._mold_dry.add(area_id)
                elif humidity > target - MOLD_OVERDRY_MARGIN + 2:
                    self._mold_dry.discard(area_id)
                mold_request = area_id not in self._mold_dry
            else:
                self._mold_dry.discard(area_id)
            demand = "mold" if mold_request else "comfort" if area_id in self._comfort else None
            if demand is None:
                continue
            self.requests[area_id] = demand
            # Quiet hours pause comfort only: the mold manager already decided
            # this wall needs drying, and a dehumidifier may run at night.
            candidates = [
                d
                for d in self.devices.values()
                if area_id in d["served_area_ids"] and d["reason"] is None and (not d["night"] or demand == "mold")
            ]
            candidates.sort(key=lambda d: (d["owner_area_id"] != area_id, d["state"] != "on", d["entity_id"]))
            if candidates:
                chosen = candidates[0]
                self.assignments[area_id] = chosen["entity_id"]
                chosen["requesting_rooms"].append(area_id)
                chosen["requested"] = True
        for d in self.devices.values():
            if d["reason"] == "user_off" and not any(
                a in self.requests or humidities.get(a) is None for a in d["served_area_ids"]
            ):
                # The demand the user switched off is over (a missing reading proves nothing):
                # resume automatic control next cycle.
                self.runtime[d["entity_id"]].user_off_until = -math.inf
            if (
                not d["requested"]
                and d["reason"] is None
                and any(humidities.get(a) is None for a in self._previous_requests.get(d["entity_id"], []))
            ):
                d["reason"] = "sensor"
            if d["requested"]:
                level = 0
                for area in d["requesting_rooms"]:
                    mold = molds.get(area) or (None,) * 5
                    target = humidity_target(rooms[area], season) or 55.0
                    if self.requests[area] == "mold" and mold[4] is not None:
                        target = min(target, mold[4])
                    wall = (
                        2
                        if mold[0] == MOLD_RISK_CRITICAL
                        else int(mold[0] == MOLD_RISK_WARNING or (mold[1] or 0) >= MOLD_SURFACE_RH_EARLY)
                    )
                    level = max(
                        level, wall, fan_level(humidities[area] - target, self.runtime[d["entity_id"]].fan_level)
                    )
                self.runtime[d["entity_id"]].fan_level = level
            self._learn_and_forecast(d, rooms, humidities, molds, season)
            if d["night"] and not d["requested"] and d["reason"] is None:
                d["reason"] = "night"
            if len(d["served_area_ids"]) == 1:
                owner = d["owner_area_id"]
                target = humidity_target(rooms[owner], season) or 55.0
                mold = molds.get(owner)
                if self.requests.get(owner) == "mold" and mold and mold[4] is not None:
                    # The wall needs drier air than comfort asks for.
                    target = min(target, mold[4])
                d["target_humidity"] = self._native_target(d["entity_id"], target)

    def _area_target(self, area: str, rooms: dict, molds: dict, season: str | None) -> float:
        target = humidity_target(rooms[area], season) or 55.0
        mold = molds.get(area)
        if self.requests.get(area) == "mold" and mold and mold[4] is not None:
            target = min(target, mold[4])  # the wall needs drier air than comfort asks for
        return target

    def _area_goal(self, area: str, rooms: dict, molds: dict, season: str | None) -> float:
        """Humidity at which the run is expected to end: comfort demand stops 2 points above its target."""
        target = self._area_target(area, rooms, molds, season)
        return target if self.requests.get(area) == "mold" else target + COMFORT_STOP_MARGIN

    def _rate(self, d: dict, runtime: DeviceRuntime, area: str, level: int) -> tuple[float, bool]:
        """Drying rate of one served room: its own once learned, else a damped host rate."""
        if area == d["owner_area_id"]:
            return runtime.k[level], runtime.k_n[level] > 0
        own = self.learned[d["entity_id"]]["areas"].get(area)
        if own and own["k_n"][level] > 0:
            return own["k"][level], True
        return runtime.k[level] * SERVED_FACTOR, False

    def _learn(self, d: dict, runtime: DeviceRuntime, area: str, level: int, k: float) -> None:
        if area == d["owner_area_id"]:
            entry: dict[str, list] = {"k": runtime.k, "k_n": runtime.k_n}
        else:
            areas = self.learned[d["entity_id"]]["areas"]
            entry = areas.setdefault(area, {"k": [v * SERVED_FACTOR for v in runtime.k], "k_n": [0] * len(DEFAULT_K)})
        entry["k"][level] = k if entry["k_n"][level] == 0 else (1 - LEARN_ALPHA) * entry["k"][level] + LEARN_ALPHA * k
        entry["k_n"][level] += 1
        # Persist the first observation at once; later refinements ride the periodic save.
        self.dirty = self.dirty or entry["k_n"][level] == 1

    def _power_w(self, config: dict) -> float | None:
        """Measured draw from the optional power sensor, in W."""
        state = self.hass.states.get(str(config.get("power_entity") or ""))
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            watts = float(state.state)
        except ValueError:
            return None
        unit = state.attributes.get("unit_of_measurement")
        if unit not in ("W", "kW"):
            return None  # an energy (kWh) or unrelated sensor would make the forecast nonsense
        if unit == "kW":
            watts *= 1000
        return watts if math.isfinite(watts) and watts >= 0 else None

    def _learn_and_forecast(self, d: dict, rooms: dict, humidities: dict, molds: dict, season: str | None) -> None:
        """Learn each room's drying rate at the fan level in use, then predict time to target."""
        runtime = self.runtime[d["entity_id"]]
        entry = self.learned[d["entity_id"]]
        d.update(
            forecast_minutes=None,
            forecast_power_w=None,
            forecast_heat_c=None,
            forecast_learned=False,
            forecast_unreachable=False,
            measured_power_w=self._power_w(d["config"]),
        )
        speed = d["fan_speed"]
        if not d["config"].get("fan_entity"):
            level = 0  # one speed: a single bucket, not three that never get told apart
        else:
            level = FAN_LEVELS.index(speed) if speed in FAN_LEVELS else 0 if d["night"] else runtime.fan_level
        d["learn_level"] = level
        # Forecast at the speed the unit is about to run at, not the one it still reads back.
        plan_level = 0 if not d["config"].get("fan_entity") or d["night"] else runtime.fan_level
        now = monotonic()
        running = d["state"] == "on" and d["reason"] is None and d["requested"]
        for area in d["served_area_ids"]:
            rh = humidities.get(area)
            if not running or rh is None or not (area == d["owner_area_id"] or area in d["requesting_rooms"]):
                runtime.anchors.pop(area, None)
                continue
            anchor = runtime.anchors.get(area)
            if anchor is None or anchor[2] != level:
                runtime.anchors[area] = (rh, now, level)
            elif now - anchor[1] >= LEARN_WINDOW_S:
                k = observed_k(anchor[0], rh, (now - anchor[1]) / 3600)
                if k is not None:
                    self._learn(d, runtime, area, level, k)
                # No drop yet (1% sensor): let the window grow instead of biasing k upward.
                if k is not None or rh > anchor[0] or now - anchor[1] >= 6 * LEARN_WINDOW_S:
                    runtime.anchors[area] = (rh, now, level)
        self._track_run(d, runtime, entry, rooms, humidities, molds, season, plan_level, running, now)
        d["last_run"] = entry["runs"][-1] if entry["runs"] else None
        if d["reason"] is not None or not (d["requested"] or d["state"] == "on"):
            return
        minutes: dict[str, float | None] = {}
        learned = True
        for area in d["served_area_ids"]:
            rh = humidities.get(area)
            if rh is None or area not in rooms:
                continue
            k, known = self._rate(d, runtime, area, plan_level)
            learned &= known
            minutes[area] = minutes_to_target(rh, self._area_goal(area, rooms, molds, season), k)
        power = float(d["config"].get("power_watts", 0) or 0)
        if d["state"] == "on" and d["measured_power_w"] is not None:
            power = d["measured_power_w"]
        own = minutes.get(d["owner_area_id"], 0.0)
        d.update(
            forecast_minutes=minutes,
            forecast_power_w=round(power) or None,
            # Drying releases the water's latent heat too; with no finite ETA show the steady state.
            forecast_heat_c=heat_gain_c(power * (1 + LATENT_HEAT_RATIO), own) if power and own != 0 else None,
            forecast_learned=learned and bool(minutes),
            forecast_unreachable=d["requested"] and any(minutes.get(a, 0.0) is None for a in d["requesting_rooms"]),
        )

    def _track_run(
        self,
        d: dict,
        runtime: DeviceRuntime,
        entry: dict,
        rooms: dict,
        humidities: dict,
        molds: dict,
        season: str | None,
        plan_level: int,
        running: bool,
        now: float,
    ) -> None:
        """Keep predicted-vs-actual minutes of the last completed drying run."""
        run = runtime.run
        if run is not None and (not running or run["area"] not in d["requesting_rooms"]):
            rh = humidities.get(run["area"])
            # Only a run whose own demand ended normally counts: a window, user-off or tank stop does not.
            if d["reason"] is None and rh is not None and rh <= run["target"] + 2.0:  # comfort stops 2 above target
                done = {"predicted": run["predicted"], "actual": round((now - run["start"]) / 60)}
                entry["runs"] = [*entry["runs"], done][-RUN_HISTORY:]
                self.dirty = True
            runtime.run = None
        if running and runtime.run is None:
            for area in sorted(d["requesting_rooms"]):
                rh = humidities.get(area)
                if rh is None or area not in rooms:
                    continue
                target = self._area_target(area, rooms, molds, season)
                goal = self._area_goal(area, rooms, molds, season)
                predicted = minutes_to_target(rh, goal, self._rate(d, runtime, area, plan_level)[0])
                if predicted:
                    runtime.run = {"area": area, "target": target, "start": now, "predicted": predicted}
                    break

    def history_sample(self, area_id: str) -> dict:
        """Dehumidifier columns for the room history row; empty when the room has no unit."""
        for d in self.devices.values():
            if area_id in d["served_area_ids"]:
                return {
                    "dehumidifier_on": d["state"] == "on",
                    "dehumidifier_fan": d.get("learn_level") if d["state"] == "on" else None,
                    "dehumidifier_power_w": d.get("measured_power_w"),
                }
        return {}

    def _native_target(self, eid: str, target: float) -> float:
        state = self.hass.states.get(eid)
        if not eid.startswith("humidifier.") or state is None:
            return target
        minimum = valid_humidity(state.attributes.get("min_humidity")) or 0.0
        maximum = valid_humidity(state.attributes.get("max_humidity")) or 100.0
        configured_step = valid_humidity(state.attributes.get("target_humidity_step"))
        step = configured_step or 1.0
        if not configured_step and hasattr(self.hass, "data"):
            # HA's Midea integration does not expose the physical 5% setpoint step.
            # Sending 51% is acknowledged as 50%, causing a command every minute.
            entry = er.async_get(self.hass).async_get(eid)
            if entry is not None and entry.platform == "midea":
                # Round DOWN: mold prevention must not get a wetter target.
                step = 5.0
                return min(maximum, max(minimum, minimum + math.floor((target - minimum) / step) * step))
        return min(maximum, max(minimum, minimum + math.ceil((target - minimum) / step) * step))

    async def apply(self, budget: PowerBudgetManager) -> None:
        """Prioritize mold starts and isolate service failures per device."""
        ordered = sorted(
            self.devices.values(),
            key=lambda d: (not any(self.requests.get(a) == "mold" for a in d["requesting_rooms"]), d["entity_id"]),
        )
        for device in ordered:
            try:
                await self._apply_device(device, budget)
            except Exception:
                device["reason"] = "error"
                _LOGGER.exception("Dehumidifier '%s': command failed", device["entity_id"])

    async def _apply_device(self, device: dict, budget: PowerBudgetManager) -> None:
        reason = device["reason"]
        if reason in ("manual", "disabled", "unavailable", "tank_full", "user_off"):
            return
        eid = device["entity_id"]
        runtime = self.runtime[eid]
        now = monotonic()
        desired = device["requested"]
        pending = now - runtime.command_at < 60
        on = runtime.command if pending else device["state"] == "on"
        if (
            not desired
            and on
            and reason is None
            and now - runtime.on_since < device["config"].get("min_run_minutes", 5) * 60
        ):
            desired = True
            device["reason"] = "min_run"
        if desired and not budget.request_heat_pump(
            f"dehumidifier:{eid}", float(device["config"].get("power_watts", 0)), bool(on)
        ):
            device["reason"] = "power_budget"
            desired = False
        domain = eid.split(".", 1)[0]
        if desired and domain == "humidifier":
            target = device["target_humidity"]
            state = self.hass.states.get(eid)
            if (
                target is not None
                and state is not None
                and valid_humidity(state.attributes.get("humidity")) != target
                and (runtime.target != target or now - runtime.target_at >= 60)
            ):
                await self.hass.services.async_call(
                    domain,
                    "set_humidity",
                    {"entity_id": eid, "humidity": target},
                    blocking=True,
                    context=make_roommind_context(),
                )
                runtime.target = target
                runtime.target_at = now
        if desired != on:
            await self.hass.services.async_call(
                domain,
                "turn_on" if desired else "turn_off",
                {"entity_id": eid},
                blocking=True,
                context=make_roommind_context(),
            )
            runtime.command = desired
            runtime.command_at = now
            if desired:
                runtime.owned_on = True
                runtime.fan_sent = None
                runtime.on_since = now
                await self._apply_start_mode(device)
            else:
                runtime.off_since = now
        # Only once the unit reports "on": Midea's fan write sends the whole cached
        # state, so right after turn_on it would switch the unit straight back off.
        if desired and device["state"] == "on":
            await self._apply_fan(device, runtime, now)
        device["commanded"] = desired

    def _fan_speed(self, config: dict) -> str | None:
        fan = str(config.get("fan_entity") or "")
        state = self.hass.states.get(fan) if fan.startswith("select.") else None
        return state.state if state is not None and state.state not in ("unknown", "unavailable") else None

    def adopt(self, entity_id: str) -> bool:
        """Hand a device the user switched on over to RoomMind's automatic control."""
        device = self.devices.get(entity_id)
        runtime = self.runtime.get(entity_id)
        if device is None or runtime is None or device["reason"] != "manual" or device["mode"] == "manual":
            return False
        runtime.owned_on = True
        return True

    async def _apply_fan(self, device: dict, runtime: DeviceRuntime, now: float) -> None:
        """Quiet fan at night, by day sized to the humidity gap and wall risk, via the fan select."""
        fan = str(device["config"].get("fan_entity") or "")
        state = self.hass.states.get(fan) if fan.startswith("select.") else None
        speed = FAN_NIGHT if device["night"] else FAN_LEVELS[runtime.fan_level]
        if (
            state is None
            or state.state == speed
            or speed not in (state.attributes.get("options") or [])
            or now - runtime.fan_at < 60
            # Midea reads "auto" back as "high": don't resend while the readback is what we got last time.
            or runtime.fan_sent == (speed, state.state)
        ):
            return
        runtime.fan_at = now
        await self.hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": fan, "option": speed},
            blocking=True,
            context=make_roommind_context(),
        )
        after = self.hass.states.get(fan)
        runtime.fan_sent = (speed, after.state if after is not None else state.state)

    async def _apply_start_mode(self, device: dict) -> None:
        """Switch to the configured mode when RoomMind itself starts the device.

        Only on our own start: a run the user started by hand keeps its mode
        (e.g. a laundry program), and an unsupported mode is ignored.
        """
        mode = str(device["config"].get("start_mode") or "")
        eid = device["entity_id"]
        state = self.hass.states.get(eid)
        if not mode or not eid.startswith("humidifier.") or state is None:
            return
        if mode not in (state.attributes.get("available_modes") or []) or state.attributes.get("mode") == mode:
            return
        await self.hass.services.async_call(
            "humidifier",
            "set_mode",
            {"entity_id": eid, "mode": mode},
            blocking=True,
            context=make_roommind_context(),
        )

    def room_status(self, area_id: str) -> dict:
        """Public data never confuses a command with an observed action."""
        devices = [
            {k: v for k, v in d.items() if k not in ("config", "night", "learn_level")}
            for d in self.devices.values()
            if area_id in d["served_area_ids"]
        ]
        for device in devices:
            device["pending_rooms"] = sorted(a for a in self.requests if a in device["served_area_ids"])
        return {
            "devices": devices,
            "request": self.requests.get(area_id),
            "assigned_entity_id": self.assignments.get(area_id),
        }

    async def release(self, old: dict | None, new: dict | None, enabled: bool) -> None:
        """Stop only our own run before a registration is removed/replaced."""
        if old and new and old["entity_id"] == new["entity_id"] and new.get("mode", "auto") == "manual":
            self.runtime.pop(old["entity_id"], None)
        if (
            not old
            or not enabled
            or old.get("mode", "auto") == "manual"
            or old.get("entity_id") == (new or {}).get("entity_id")
        ):
            return
        eid = old["entity_id"]
        state = self.hass.states.get(eid)
        runtime = self.runtime.get(eid)
        if (
            runtime is not None
            and runtime.owned_on
            and (state is not None and state.state == "on" or runtime.command is True)
        ):
            await self.hass.services.async_call(
                eid.split(".")[0], "turn_off", {"entity_id": eid}, blocking=True, context=make_roommind_context()
            )
        self.runtime.pop(eid, None)
        self.learned.pop(eid, None)
