"""Logical room-climate capabilities and AC-only auxiliary routing."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.core import HomeAssistant

from ..const import make_roommind_context
from ..utils.device_utils import get_ac_eids, get_trv_eids

_INVERTED_ULTRA_FAN_MODES = {"ultra_high": "quiet", "ultra_low": "turbo"}
_FAN_MODE_ORDER = ("auto", "quiet", "low", "medium", "high", "turbo", "on", "off")


@dataclass(frozen=True)
class RoomClimateCapabilities:
    """Capabilities RoomMind can provide, independent of physical targets."""

    hvac_modes: tuple[str, ...]
    fan_modes: tuple[str, ...]
    swing_modes: tuple[str, ...]
    swing_horizontal_modes: tuple[str, ...]


def _shared_ac_modes(hass: HomeAssistant, room: dict, attribute: str) -> tuple[str, ...]:
    """Return modes shared by every AC, preserving the first AC's order."""
    acs = get_ac_eids(room.get("devices", []))
    ac_states = [hass.states.get(entity_id) for entity_id in acs]
    ac_state = ac_states[0] if ac_states else None
    if not ac_state or any(state is None for state in ac_states):
        return ()
    shared = set(ac_state.attributes.get(attribute, []))
    for state in ac_states[1:]:
        shared &= set(state.attributes.get(attribute, []))
    return tuple(mode for mode in ac_state.attributes.get(attribute, []) if mode in shared)


def _has_inverted_ultra_fan_modes(modes: tuple[str, ...]) -> bool:
    return set(_INVERTED_ULTRA_FAN_MODES).issubset(mode.lower() for mode in modes)


def room_fan_modes(modes: tuple[str, ...]) -> tuple[str, ...]:
    """Return fan modes suitable for presentation to Home Assistant clients."""
    if not _has_inverted_ultra_fan_modes(modes):
        return modes
    exposed = [_INVERTED_ULTRA_FAN_MODES.get(mode.lower(), mode) for mode in modes]
    order = {mode: index for index, mode in enumerate(_FAN_MODE_ORDER)}
    return tuple(sorted(exposed, key=lambda mode: order.get(mode.lower(), len(order))))


def fan_mode_to_physical(modes: tuple[str, ...], fan_mode: str) -> str:
    """Translate an exposed fan mode to the AC controller's value."""
    if not _has_inverted_ultra_fan_modes(modes):
        return fan_mode
    inverse = {exposed: raw for raw, exposed in _INVERTED_ULTRA_FAN_MODES.items()}
    raw_mode = inverse.get(fan_mode.lower())
    if raw_mode is None:
        return fan_mode
    return next(mode for mode in modes if mode.lower() == raw_mode)


def fan_mode_from_physical(modes: tuple[str, ...], fan_mode: str) -> str:
    """Translate an AC controller fan mode to the exposed value."""
    if not _has_inverted_ultra_fan_modes(modes):
        return fan_mode
    return _INVERTED_ULTRA_FAN_MODES.get(fan_mode.lower(), fan_mode)


def room_capabilities(hass: HomeAssistant, room: dict) -> RoomClimateCapabilities:
    """Build a logical capability model; TRVs never contribute AC-only modes."""
    trvs = get_trv_eids(room.get("devices", []))
    acs = get_ac_eids(room.get("devices", []))
    ac_states = [hass.states.get(entity_id) for entity_id in acs]
    ac_state = ac_states[0] if ac_states else None
    ac_modes = set(ac_state.attributes.get("hvac_modes", []) if ac_state else [])
    can_heat = bool(trvs) or bool(ac_modes & {"heat", "heat_cool", "auto"})
    can_cool = bool(acs and ac_modes & {"cool", "heat_cool", "auto"})
    modes = ["off"]
    if can_heat:
        modes.append("heat")
    if can_cool:
        modes.append("cool")
    if can_heat and can_cool:
        modes.append("auto")
    if "dry" in ac_modes:
        modes.append("dry")
    if "fan_only" in ac_modes:
        modes.append("fan_only")

    return RoomClimateCapabilities(
        tuple(modes),
        room_fan_modes(_shared_ac_modes(hass, room, "fan_modes")),
        _shared_ac_modes(hass, room, "swing_modes"),
        _shared_ac_modes(hass, room, "swing_horizontal_modes"),
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
        # Persisted RoomMind state is not an activation request. Auxiliary
        # modes are activated only by an explicit climate.roommind_* command.
        # The coordinator may preserve/configure them only while the physical
        # AC already reports the same mode. This prevents HA startup or a
        # periodic refresh from powering on an AC that the user left off.
        state = hass.states.get(entity_id)
        if state is None or state.state != mode:
            return
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
