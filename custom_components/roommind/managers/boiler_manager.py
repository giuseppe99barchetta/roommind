"""Central boiler control with a fail-closed hydraulic safety state machine."""

from __future__ import annotations

import logging
from enum import StrEnum
from time import monotonic

from homeassistant.core import HomeAssistant

from ..const import make_roommind_context

_LOGGER = logging.getLogger(__name__)


class BoilerState(StrEnum):
    OFF = "off"
    PREOPENING = "preopening"
    ON = "on"
    POSTSTOP = "poststop"
    FAULT = "fault"


class BoilerManager:
    """Enforce: an enabled boiler always has a verified hydraulic path.

    Delays are state timestamps rather than sleeps, keeping the HA event loop
    responsive and making restart recovery conservative.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.state = BoilerState.OFF
        self._state_since = monotonic()
        self.demand_rooms: set[str] = set()
        self.path_safe = False

    @staticmethod
    def _available(hass: HomeAssistant, entity_id: str) -> bool:
        st = hass.states.get(entity_id)
        return bool(st and st.state not in ("unknown", "unavailable"))

    async def _set_bypass(self, settings: dict, open_: bool) -> bool:
        bypasses = [e for e in settings.get("hydraulic_bypass_entities", []) if e]
        if not bypasses:
            return False
        if not open_:
            # Releasing control is intentionally conservative: RoomMind idles
            # the bypasses only after the boiler has been stopped and held.
            for entity_id in bypasses:
                try:
                    await self.hass.services.async_call("climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": "off"}, blocking=True, context=make_roommind_context())
                except Exception:  # noqa: BLE001
                    _LOGGER.warning("Unable to release boiler bypass '%s'", entity_id, exc_info=True)
            return True
        target = float(settings.get("hydraulic_bypass_open_temperature", 28.0))
        verified = False
        for entity_id in bypasses:
            if not self._available(self.hass, entity_id):
                continue
            try:
                await self.hass.services.async_call("climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": "heat"}, blocking=True, context=make_roommind_context())
                await self.hass.services.async_call("climate", "set_temperature", {"entity_id": entity_id, "temperature": target}, blocking=True, context=make_roommind_context())
                verified = True
            except Exception:  # noqa: BLE001
                _LOGGER.warning("Unable to open boiler bypass '%s'", entity_id, exc_info=True)
        return verified

    async def _set_boiler(self, settings: dict, on: bool) -> bool:
        entity_id = settings.get("boiler_entity", "")
        if not self._available(self.hass, entity_id):
            return False
        control_type = settings.get("boiler_control_type", "climate")
        domain = "switch" if control_type == "switch" else "climate"
        service = "turn_on" if on and domain == "switch" else "turn_off" if not on and domain == "switch" else "set_hvac_mode"
        data = {"entity_id": entity_id}
        if service == "set_hvac_mode":
            data["hvac_mode"] = "heat" if on else "off"
        try:
            await self.hass.services.async_call(domain, service, data, blocking=True, context=make_roommind_context())
            return True
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Unable to change boiler '%s'", entity_id, exc_info=True)
            return False

    async def async_reconcile(self, settings: dict, demand_rooms: set[str]) -> None:
        """Advance one safe transition. Missing safety configuration disables boiler."""
        self.demand_rooms = set(demand_rooms)
        if not settings.get("boiler_entity"):
            self.state = BoilerState.OFF
            self.path_safe = False
            return
        now = monotonic()
        demand = bool(demand_rooms)
        pre_delay = float(settings.get("boiler_startup_delay_seconds", 30))
        post_delay = float(settings.get("boiler_shutdown_delay_seconds", 60))
        if self.state == BoilerState.OFF and demand:
            self.path_safe = await self._set_bypass(settings, True)
            if not self.path_safe:
                self.state = BoilerState.FAULT
                await self._set_boiler(settings, False)
                return
            self.state, self._state_since = BoilerState.PREOPENING, now
            _LOGGER.info("Boiler demand %d: opening hydraulic bypass", len(demand_rooms))
        elif self.state == BoilerState.PREOPENING:
            self.path_safe = await self._set_bypass(settings, True)
            if not demand:
                self.state, self._state_since = BoilerState.OFF, now
            elif not self.path_safe:
                self.state = BoilerState.FAULT
                await self._set_boiler(settings, False)
            elif now - self._state_since >= pre_delay:
                if await self._set_boiler(settings, True):
                    self.state, self._state_since = BoilerState.ON, now
                    _LOGGER.info("Boiler hydraulic path verified; starting boiler")
                else:
                    self.state = BoilerState.FAULT
        elif self.state == BoilerState.ON:
            self.path_safe = await self._set_bypass(settings, True)
            if not self.path_safe:
                _LOGGER.error("Hydraulic path lost while boiler active; shutting boiler down")
                await self._set_boiler(settings, False)
                self.state, self._state_since = BoilerState.FAULT, now
            elif not demand:
                await self._set_boiler(settings, False)
                self.state, self._state_since = BoilerState.POSTSTOP, now
        elif self.state == BoilerState.POSTSTOP:
            if demand:
                self.path_safe = await self._set_bypass(settings, True)
                self.state, self._state_since = BoilerState.PREOPENING, now
            elif now - self._state_since >= post_delay:
                await self._set_bypass(settings, False)
                self.path_safe = False
                self.state, self._state_since = BoilerState.OFF, now
        elif self.state == BoilerState.FAULT:
            await self._set_boiler(settings, False)
            if not demand:
                self.path_safe = False
                self.state, self._state_since = BoilerState.OFF, now
