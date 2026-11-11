"""One control owner for local and shared physical dehumidifiers."""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
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


class DehumidifierManager:
    """Collect requests first, allocate once, then command each physical device."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.lock = asyncio.Lock()
        self.devices: dict[str, dict] = {}
        self.runtime: dict[str, DeviceRuntime] = {}
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
            runtime = self.runtime.setdefault(eid, DeviceRuntime(on, now, now, available=available))
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
            {k: v for k, v in d.items() if k not in ("config", "night")}
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
