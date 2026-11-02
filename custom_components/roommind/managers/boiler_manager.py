"""Central boiler control with a fail-closed hydraulic safety state machine."""

from __future__ import annotations

import logging
from enum import StrEnum
from time import monotonic

from homeassistant.core import HomeAssistant

from ..const import make_roommind_context

_LOGGER = logging.getLogger(__name__)

FAULT_NOTIFICATION_ID = "roommind_boiler_fault"

# Defaults for the settings below. Minimum demand 1 keeps the historic
# behaviour; the run/off guards prevent the 30-second boiler cycles that a
# single noisy room (or a lost bypass) could otherwise cause.
DEFAULT_BOILER_MIN_DEMAND_ROOMS = 1
DEFAULT_BOILER_MIN_RUN_MINUTES = 5.0
DEFAULT_BOILER_MIN_OFF_MINUTES = 3.0
DEFAULT_BOILER_FAULT_RETRY_MINUTES = 5.0


class BoilerState(StrEnum):
    OFF = "off"
    PREOPENING = "preopening"
    ON = "on"
    POSTSTOP = "poststop"
    FAULT = "fault"


def bypass_entities(settings: dict) -> set[str]:
    """Bypass TRVs owned exclusively by the boiler manager (empty without a boiler)."""
    if not settings.get("boiler_entity"):
        return set()
    return {e for e in settings.get("hydraulic_bypass_entities", []) if e}


class BoilerManager:
    """Enforce: an enabled boiler always has a verified hydraulic path.

    Delays are state timestamps rather than sleeps, keeping the HA event loop
    responsive and making restart recovery conservative.

    The boiler starts only when at least ``boiler_min_demand_rooms`` rooms ask
    for radiator heat; once running it keeps going while any room still asks
    (start quorum, continue on any demand). The bypass valves belong to this
    manager alone: room control never writes them while a boiler is configured.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.state = BoilerState.OFF
        self._state_since = monotonic()
        self._on_since: float | None = None
        self._off_since: float | None = None
        self.demand_rooms: set[str] = set()
        self.path_safe = False
        self.fault_reason: str | None = None
        self._last_bypass_command: dict[str, float] = {}
        self._last_lock_command: dict[str, float] = {}
        # After start-up or a fault the bypass may have been left open by
        # whoever controlled it before. Release it once when idle.
        self._bypass_released = False

    @property
    def heat_available(self) -> bool:
        """True while radiators can actually receive hot water (or are about to)."""
        return self.state in (BoilerState.PREOPENING, BoilerState.ON)

    def _bypass_confirmed(self, entity_id: str, target: float) -> bool:
        """Check HA's *reported* heat mode and setpoint, not command success.

        A climate TRV does not expose physical valve travel. This is an
        acknowledgement interlock, not proof of the hydraulic opening.
        """
        state = self.hass.states.get(entity_id)
        if not state or state.state != "heat":
            return False
        try:
            return abs(float(state.attributes.get("temperature")) - target) <= 0.5
        except (TypeError, ValueError, AttributeError):
            return False

    @staticmethod
    def _available(hass: HomeAssistant, entity_id: str) -> bool:
        st = hass.states.get(entity_id)
        return bool(st and st.state not in ("unknown", "unavailable"))

    def _child_lock_switches(self, entity_id: str) -> list[str]:
        """Child-lock switches exposed by the bypass TRV's device, if any."""
        try:
            from homeassistant.helpers import entity_registry as er

            registry = er.async_get(self.hass)
            entry = registry.async_get(entity_id)
            if entry is None or not entry.device_id:
                return []
            return [
                e.entity_id
                for e in er.async_entries_for_device(registry, entry.device_id)
                if e.domain == "switch" and "child_lock" in (e.translation_key or e.entity_id)
            ]
        except Exception:  # noqa: BLE001 - registry unavailable (tests, early startup)
            return []

    async def _lock_bypass(self, settings: dict, entity_id: str) -> None:
        """Keep physical buttons from taking the bypass out of forced heat.

        A press on the valve (or its vendor app) switches it to its own
        schedule mode, which drops the readback and trips the interlock.
        """
        if not settings.get("hydraulic_bypass_child_lock", True):
            return
        for lock_eid in self._child_lock_switches(entity_id):
            state = self.hass.states.get(lock_eid)
            if state is None or state.state != "off":
                continue
            if monotonic() - self._last_lock_command.get(lock_eid, float("-inf")) < 60:
                continue
            self._last_lock_command[lock_eid] = monotonic()
            try:
                await self.hass.services.async_call(
                    "switch",
                    "turn_on",
                    {"entity_id": lock_eid},
                    blocking=True,
                    context=make_roommind_context(),
                )
            except Exception:  # noqa: BLE001
                _LOGGER.warning("Unable to enable child lock '%s'", lock_eid, exc_info=True)

    async def _set_bypass(self, settings: dict, open_: bool) -> bool:
        bypasses = [e for e in settings.get("hydraulic_bypass_entities", []) if e]
        if not bypasses:
            return False
        if not open_:
            # Releasing control is intentionally conservative: RoomMind idles
            # the bypasses only after the boiler has been stopped and held.
            for entity_id in bypasses:
                if not self._available(self.hass, entity_id):
                    continue
                try:
                    await self.hass.services.async_call(
                        "climate",
                        "set_hvac_mode",
                        {"entity_id": entity_id, "hvac_mode": "off"},
                        blocking=True,
                        context=make_roommind_context(),
                    )
                except Exception:  # noqa: BLE001
                    _LOGGER.warning("Unable to release boiler bypass '%s'", entity_id, exc_info=True)
            self._bypass_released = True
            return True
        self._bypass_released = False
        target = float(settings.get("hydraulic_bypass_open_temperature", 28.0))
        confirmed = False
        for entity_id in bypasses:
            if not self._available(self.hass, entity_id):
                continue
            await self._lock_bypass(settings, entity_id)
            if self._bypass_confirmed(entity_id, target):
                confirmed = True
                continue
            # Zigbee TRVs can take a full reporting cycle to acknowledge a
            # command. Retry, but do not flood the network every 30 seconds.
            if monotonic() - self._last_bypass_command.get(entity_id, float("-inf")) < 60:
                continue
            try:
                self._last_bypass_command[entity_id] = monotonic()
                await self.hass.services.async_call(
                    "climate",
                    "set_hvac_mode",
                    {"entity_id": entity_id, "hvac_mode": "heat"},
                    blocking=True,
                    context=make_roommind_context(),
                )
                await self.hass.services.async_call(
                    "climate",
                    "set_temperature",
                    {"entity_id": entity_id, "temperature": target},
                    blocking=True,
                    context=make_roommind_context(),
                )
                confirmed = confirmed or self._bypass_confirmed(entity_id, target)
            except Exception:  # noqa: BLE001
                _LOGGER.warning("Unable to open boiler bypass '%s'", entity_id, exc_info=True)
        return confirmed

    async def _set_boiler(self, settings: dict, on: bool) -> bool:
        entity_id = settings.get("boiler_entity", "")
        if not self._available(self.hass, entity_id):
            return False
        control_type = settings.get("boiler_control_type", "climate")
        domain = "switch" if control_type == "switch" else "climate"
        service = (
            "turn_on" if on and domain == "switch" else "turn_off" if not on and domain == "switch" else "set_hvac_mode"
        )
        data = {"entity_id": entity_id}
        if service == "set_hvac_mode":
            data["hvac_mode"] = "heat" if on else "off"
        try:
            await self.hass.services.async_call(domain, service, data, blocking=True, context=make_roommind_context())
            return True
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Unable to change boiler '%s'", entity_id, exc_info=True)
            return False

    def _notify(self, message: str | None) -> None:
        """Raise (or clear) a persistent notification for boiler faults."""
        try:
            from homeassistant.components import persistent_notification

            if message is None:
                persistent_notification.async_dismiss(self.hass, FAULT_NOTIFICATION_ID)
            else:
                persistent_notification.async_create(
                    self.hass, message, title="RoomMind: caldaia in blocco", notification_id=FAULT_NOTIFICATION_ID
                )
        except Exception:  # noqa: BLE001 - notifications are best effort
            _LOGGER.debug("Boiler fault notification unavailable", exc_info=True)

    async def _enter_fault(self, settings: dict, reason: str, now: float) -> None:
        was_running = self.state == BoilerState.ON
        await self._set_boiler(settings, False)
        if was_running:
            self._off_since = now
        self.path_safe = False
        self.fault_reason = reason
        self.state, self._state_since = BoilerState.FAULT, now
        self._notify(
            f"{reason}. La caldaia è stata spenta per sicurezza; RoomMind riprova "
            "automaticamente finché le stanze chiedono calore."
        )

    def _off_long_enough(self, now: float, min_off: float) -> bool:
        return self._off_since is None or now - self._off_since >= min_off

    async def async_reconcile(self, settings: dict, demand_rooms: set[str]) -> None:
        """Advance one safe transition. Missing safety configuration disables boiler."""
        if not settings.get("climate_control_active", True):
            demand_rooms = set()
        self.demand_rooms = set(demand_rooms)
        if not settings.get("boiler_entity"):
            self.state = BoilerState.OFF
            self.path_safe = False
            return
        now = monotonic()
        demand = bool(demand_rooms)
        min_rooms = max(1, int(settings.get("boiler_min_demand_rooms", DEFAULT_BOILER_MIN_DEMAND_ROOMS)))
        quorum = len(demand_rooms) >= min_rooms
        pre_delay = float(settings.get("boiler_startup_delay_seconds", 30))
        post_delay = float(settings.get("boiler_shutdown_delay_seconds", 60))
        min_run = float(settings.get("boiler_min_run_minutes", DEFAULT_BOILER_MIN_RUN_MINUTES)) * 60
        min_off = float(settings.get("boiler_min_off_minutes", DEFAULT_BOILER_MIN_OFF_MINUTES)) * 60
        fault_retry = float(settings.get("boiler_fault_retry_minutes", DEFAULT_BOILER_FAULT_RETRY_MINUTES)) * 60

        if self.state == BoilerState.OFF:
            if quorum and self._off_long_enough(now, min_off):
                if not settings.get("hydraulic_bypass_entities"):
                    await self._enter_fault(settings, "Nessuna valvola di bypass configurata", now)
                    return
                self.path_safe = await self._set_bypass(settings, True)
                # Allow state-report propagation during PREOPENING; never turn the
                # boiler on before HA confirms the bypass mode and setpoint.
                self.state, self._state_since = BoilerState.PREOPENING, now
                _LOGGER.info("Boiler demand %d/%d: opening hydraulic bypass", len(demand_rooms), min_rooms)
            elif not self._bypass_released:
                await self._set_bypass(settings, False)
                self.path_safe = False
        elif self.state == BoilerState.PREOPENING:
            if not quorum:
                # Demand fell below the start quorum before the burner fired.
                await self._set_bypass(settings, False)
                self.path_safe = False
                self.state, self._state_since = BoilerState.OFF, now
                return
            self.path_safe = await self._set_bypass(settings, True)
            if not self.path_safe:
                if now - self._state_since >= max(90.0, pre_delay * 2):
                    _LOGGER.error("Boiler bypass never acknowledged; refusing to start boiler")
                    await self._enter_fault(settings, "Il bypass idraulico non ha confermato l'apertura", now)
            elif now - self._state_since >= pre_delay:
                if await self._set_boiler(settings, True):
                    self.state, self._state_since = BoilerState.ON, now
                    self._on_since = now
                    self.fault_reason = None
                    self._notify(None)
                    _LOGGER.info("Boiler hydraulic path verified; starting boiler")
                else:
                    await self._enter_fault(settings, "Impossibile accendere la caldaia", now)
        elif self.state == BoilerState.ON:
            self.path_safe = await self._set_bypass(settings, True)
            if not self.path_safe:
                # Safety beats the minimum run time.
                _LOGGER.error("Hydraulic path lost while boiler active; shutting boiler down")
                await self._enter_fault(settings, "Il bypass idraulico ha perso la posizione aperta", now)
            elif not demand and (self._on_since is None or now - self._on_since >= min_run):
                await self._set_boiler(settings, False)
                self._off_since = now
                self.state, self._state_since = BoilerState.POSTSTOP, now
        elif self.state == BoilerState.POSTSTOP:
            if quorum and self._off_long_enough(now, min_off):
                self.path_safe = await self._set_bypass(settings, True)
                self.state, self._state_since = BoilerState.PREOPENING, now
            elif now - self._state_since >= post_delay:
                await self._set_bypass(settings, False)
                self.path_safe = False
                self.state, self._state_since = BoilerState.OFF, now
        elif self.state == BoilerState.FAULT:
            # The boiler was switched off on entry; do not re-send OFF every tick.
            if not demand:
                await self._set_bypass(settings, False)
                self.path_safe = False
                self.fault_reason = None
                self._notify(None)
                self.state, self._state_since = BoilerState.OFF, now
            elif now - self._state_since >= fault_retry:
                _LOGGER.warning("Boiler fault (%s): retrying", self.fault_reason)
                self.state, self._state_since = BoilerState.OFF, now
