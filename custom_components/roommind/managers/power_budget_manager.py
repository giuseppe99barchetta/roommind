"""Deterministic, cycle-scoped electrical budget allocation for heat pumps."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.core import HomeAssistant

from ..utils.sensor_utils import read_sensor_value


@dataclass(frozen=True)
class PowerBudgetStatus:
    available_watts: float | None
    reserved_watts: float
    enabled: bool


class PowerBudgetManager:
    """Reserve heat-pump start load once, in stable room-id order.

    The coordinator owns one instance.  A cycle begins with already-running
    RoomMind heat pumps reserved, then each new request is atomically granted
    or denied.  This is deliberately synchronous: all room decisions execute
    in the single HA coordinator task, so two rooms cannot consume a snapshot
    concurrently.
    """

    def __init__(self) -> None:
        self._available: float | None = None
        self._reserved: dict[str, float] = {}
        self._enabled = False
        self._conservative = True

    def begin_cycle(self, hass: HomeAssistant, settings: dict, running_loads: dict[str, float]) -> None:
        self._enabled = bool(settings.get("power_budget_enabled", False))
        self._conservative = settings.get("power_budget_unavailable_behavior", "boiler") == "boiler"
        self._reserved = {room: max(0.0, load) for room, load in running_loads.items()}
        if not self._enabled:
            self._available = None
            return
        sensor = settings.get("power_sensor")
        raw = read_sensor_value(hass, sensor, "global", "available power")
        try:
            value = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            value = None
        if value is None:
            self._available = None
            return
        max_power = float(settings.get("power_budget_max_watts", 0) or 0)
        reserve = float(settings.get("power_budget_reserve_watts", 0) or 0)
        self._available = max(
            0.0, (max_power - value if settings.get("power_sensor_mode") == "consumption" else value) - reserve
        )

    def request_heat_pump(self, room_id: str, watts: float, already_running: bool) -> bool:
        """Grant a requested heat-pump allocation, without charging it twice."""
        if not self._enabled or already_running:
            return True
        watts = max(0.0, watts)
        if self._available is None:
            return not self._conservative
        if room_id in self._reserved:
            return True
        if self._available - sum(self._reserved.values()) < watts:
            return False
        self._reserved[room_id] = watts
        return True

    def status(self) -> PowerBudgetStatus:
        return PowerBudgetStatus(self._available, sum(self._reserved.values()), self._enabled)
