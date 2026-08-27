"""Logical room-climate capabilities and AC-only auxiliary routing."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.core import HomeAssistant

from ..const import make_roommind_context
from ..utils.device_utils import get_ac_eids, get_trv_eids


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


async def async_apply_ac_auxiliary_mode(
    hass: HomeAssistant,
    room: dict,
    *,
    window_open: bool = False,
) -> None:
    """Apply an automatic AC-only auxiliary mode after normal device idling."""
    acs = get_ac_eids(room.get("devices", []))
    if not acs:
        return
    entity_id = acs[0]
    mode = room.get("room_hvac_mode")
    keep_fan_on_window_open = room.get("keep_fan_only_on_window_open", True)

    if mode == "dry" and window_open:
        return
    if mode == "fan_only" and window_open and not keep_fan_on_window_open:
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

