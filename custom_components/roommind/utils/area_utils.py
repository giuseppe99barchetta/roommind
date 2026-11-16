"""Rooms whose Home Assistant area was deleted rest (#494).

A resting room keeps its configuration, learned model and history but has no entities and
drives no device; it runs again once its area is back. "Resting" is not stored: it is "stored,
but its area is missing from the area registry". ``rest_switched_off`` marks a resting room whose
shutdown is complete (every device it drove has an outcome, see ``PendingShutdowns``).
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar

REST_SWITCHED_OFF = "rest_switched_off"
REST_SHUTDOWN_EXPIRED = "rest_shutdown_expired"


def has_area(hass: HomeAssistant, area_id: str) -> bool:
    """True while *area_id* exists in the area registry (always True without a loaded registry)."""
    registry = hass.data.get(ar.DATA_REGISTRY) if isinstance(getattr(hass, "data", None), dict) else None
    # Not loaded yet (no `areas` before async_load): every room runs
    areas = getattr(registry, "areas", None) if registry is not None else None
    if areas is None:
        return True
    return area_id in areas


def rooms_with_area(hass: HomeAssistant, rooms: dict[str, dict]) -> dict[str, dict]:
    """The running rooms of *rooms*."""
    return {area_id: room for area_id, room in rooms.items() if has_area(hass, area_id)}


def rooms_without_area(hass: HomeAssistant, rooms: dict[str, dict]) -> dict[str, dict]:
    """The resting rooms of *rooms*."""
    return {area_id: room for area_id, room in rooms.items() if not has_area(hass, area_id)}
