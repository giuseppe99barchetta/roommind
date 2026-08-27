"""Logical room-climate capabilities and AC-only auxiliary routing."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.core import HomeAssistant

from ..const import DOMAIN, make_roommind_context
from ..control.mpc_controller import MPCController
from ..utils.device_utils import get_ac_eids, get_trv_eids


# The coordinator intentionally keeps dry/fan_only thermally idle.  Without a
# dedicated routing guard, MPCController would idle the AC first (usually
# hvac_mode=off) and only then room_climate would send the auxiliary mode.  Some
# integrations/devices process that off asynchronously, so the later fan_only
# command can be lost and the AC ends up off.  Keep the AC out of the normal
# idle pass whenever the selected auxiliary mode is allowed, while still letting
# the controller idle TRVs/other heat sources with its existing force_off rules.
_auxiliary_allowed_by_area: dict[str, bool] = {}
_original_mpc_async_apply = MPCController.async_apply


async def _async_apply_with_auxiliary_routing(self: MPCController, *args, **kwargs) -> None:
    requested_mode = self.room_config.get("room_hvac_mode")
    window_open = bool(kwargs.get("window_open", False))
    keep_fan_on_window_open = self.room_config.get("keep_fan_only_on_window_open", True)

    auxiliary_allowed = (requested_mode == "dry" and not window_open) or (
        requested_mode == "fan_only" and (not window_open or keep_fan_on_window_open)
    )
    _auxiliary_allowed_by_area[self._area_id] = auxiliary_allowed

    if not auxiliary_allowed or not self.acs:
        await _original_mpc_async_apply(self, *args, **kwargs)
        return

    # The coordinator has already forced MODE_IDLE for auxiliary modes.  Hide
    # ACs from the controller for this apply only so they never receive the
    # intermediate OFF command.  TRVs and other devices are still idled using
    # the original force_off semantics.
    original_acs = self.acs
    self.acs = []
    try:
        await _original_mpc_async_apply(self, *args, **kwargs)
    finally:
        self.acs = original_acs


# Patch the class once at module import. coordinator.py imports MPCController
# before this module, so both references point to the same class object.
if MPCController.async_apply is not _async_apply_with_auxiliary_routing:
    MPCController.async_apply = _async_apply_with_auxiliary_routing


@dataclass(frozen=True)
class RoomClimateCapabilities:
    """Capabilities RoomMind can provide, independent of physical targets."""

    hvac_modes: tuple[str, ...]
    fan_modes: tuple[str, ...]
    swing_modes: tuple[str, ...]
    swing_horizontal_modes: tuple[str, ...]


def room_capabilities(hass: HomeAssistant, room: dict) -> RoomClimateCapabilities:
    """Build a logical capability model; TRVs never contribute AC-only modes."""
    trvs = get_trv_eids(room.get("devices", []))
    acs = get_ac_eids(room.get("devices", []))
    ac_state = hass.states.get(acs[0]) if acs else None
    ac_modes = set(ac_state.attributes.get("hvac_modes", []) if ac_state else [])
    can_heat = bool(trvs) or bool(ac_modes & {"heat", "heat_cool", "auto"})
    can_cool = bool(acs and ac_modes & {"cool", "heat_cool", "auto"})
    modes = ["off"]
    if can_heat:
        modes.append("heat")
    if can_cool:
        modes.append("cool")
    if can_heat and can_cool:
        modes.append("heat_cool")
    if "auto" in ac_modes:
        modes.append("auto")
    if "dry" in ac_modes:
        modes.append("dry")
    if "fan_only" in ac_modes:
        modes.append("fan_only")
    return RoomClimateCapabilities(
        tuple(modes),
        tuple(ac_state.attributes.get("fan_modes", []) if ac_state else []),
        tuple(ac_state.attributes.get("swing_modes", []) if ac_state else []),
        tuple(ac_state.attributes.get("swing_horizontal_modes", []) if ac_state else []),
    )


async def async_apply_ac_auxiliary_mode(hass: HomeAssistant, room: dict) -> None:
    """Route dry/fan-only and optional AC controls only to the configured AC."""
    store = hass.data.get(DOMAIN, {}).get("store")
    if store is not None:
        settings = store.get_settings()
        if not settings.get("climate_control_active", True) or not room.get("climate_control_enabled", True):
            return

    acs = get_ac_eids(room.get("devices", []))
    if not acs:
        return
    entity_id = acs[0]
    mode = room.get("room_hvac_mode")

    # Use the same debounced window decision computed by the controller wrapper.
    # Default to allowed for direct/legacy callers that did not pass through the
    # coordinator first.
    area_id = room.get("area_id", "unknown")
    auxiliary_allowed = _auxiliary_allowed_by_area.pop(area_id, True)
    if mode in ("dry", "fan_only") and not auxiliary_allowed:
        return

    if mode in ("dry", "fan_only"):
        await hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": entity_id, "hvac_mode": mode},
            blocking=True,
            context=make_roommind_context(),
        )
    for service, key in (
        ("set_fan_mode", "room_fan_mode"),
        ("set_swing_mode", "room_swing_mode"),
        ("set_swing_horizontal_mode", "room_swing_horizontal_mode"),
    ):
        if room.get(key):
            await hass.services.async_call(
                "climate",
                service,
                {"entity_id": entity_id, service.removeprefix("set_"): room[key]},
                blocking=True,
                context=make_roommind_context(),
            )
