"""Climate platform for RoomMind."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEFAULT_COMFORT_COOL,
    DEFAULT_COMFORT_HEAT,
    DOMAIN,
    OVERRIDE_CUSTOM,
    is_override_active,
)
from .control.mpc_controller import async_turn_off_climate, resolve_hvac_mode
from .coordinator import RoomMindCoordinator
from .managers.room_climate import RoomClimateCapabilities, room_capabilities
from .utils.device_utils import get_ac_eids, get_all_entity_ids, get_trv_eids
from .utils.temp_utils import celsius_to_ha_temp


def _create_room_climates(
    coordinator: RoomMindCoordinator,
    area_id: str,
) -> list[ClimateEntity]:
    """Create climate entities for a room."""
    # The canonical entity has a stable, concise entity ID.  The old override
    # endpoint remains disabled by default for existing automations.
    return [RoomMindClimate(coordinator, area_id), RoomMindOverrideClimate(coordinator, area_id)]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RoomMind climate entities from a config entry."""
    coordinator: RoomMindCoordinator = hass.data[DOMAIN][entry.entry_id]
    store = hass.data[DOMAIN]["store"]
    coordinator.async_add_climate_entities = async_add_entities
    rooms = store.get_rooms()
    entities: list[ClimateEntity] = []
    for area_id in rooms:
        entities.extend(_create_room_climates(coordinator, area_id))
        coordinator._climate_entity_areas.add(area_id)
    if entities:
        async_add_entities(entities)


class RoomMindOverrideClimate(CoordinatorEntity, ClimateEntity):
    """Climate entity for room override control."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:thermometer-alert"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 5.0
    _attr_max_temp = 35.0
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator)
        self._area_id = area_id
        self._attr_unique_id = f"{DOMAIN}_{area_id}_override"
        self._attr_name = f"{area_id} Override"
        self.entity_id = f"climate.{DOMAIN}_{area_id}_override"

    def _room(self) -> dict | None:
        store = self.coordinator.hass.data[DOMAIN]["store"]
        room: dict | None = store.get_room(self._area_id)
        return room

    def _climate_mode(self) -> str:
        room = self._room()
        return room.get("climate_mode", "auto") if room else "auto"

    def _is_override_active(self) -> bool:
        room = self._room()
        if room is None:
            return False
        return is_override_active(room)

    @property
    def supported_features(self) -> ClimateEntityFeature:
        base = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        if self._climate_mode() == "auto":
            return base | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        return base | ClimateEntityFeature.TARGET_TEMPERATURE

    @property
    def hvac_modes(self) -> list[HVACMode]:
        mode = self._climate_mode()
        if mode == "auto":
            return [HVACMode.OFF, HVACMode.HEAT_COOL]
        if mode == "cool_only":
            return [HVACMode.OFF, HVACMode.COOL]
        return [HVACMode.OFF, HVACMode.HEAT]

    @property
    def hvac_mode(self) -> HVACMode:
        if not self._is_override_active():
            return HVACMode.OFF
        mode = self._climate_mode()
        if mode == "auto":
            return HVACMode.HEAT_COOL
        if mode == "cool_only":
            return HVACMode.COOL
        return HVACMode.HEAT

    @property
    def target_temperature(self) -> float | None:
        if not self._is_override_active():
            return None
        room = self._room() or {}
        if self._climate_mode() == "cool_only":
            val = room.get("override_cool")
        else:
            val = room.get("override_heat")
        return float(val) if isinstance(val, (int, float)) else None

    @property
    def target_temperature_low(self) -> float | None:
        if not self._is_override_active():
            return None
        val = (self._room() or {}).get("override_heat")
        return float(val) if isinstance(val, (int, float)) else None

    @property
    def target_temperature_high(self) -> float | None:
        if not self._is_override_active():
            return None
        val = (self._room() or {}).get("override_cool")
        return float(val) if isinstance(val, (int, float)) else None

    @property
    def current_temperature(self) -> float | None:
        """Return the room's current temperature from coordinator data."""
        data = self.coordinator.data
        if not data:
            return None
        room_data = data.get("rooms", {}).get(self._area_id)
        if not room_data:
            return None
        val = room_data.get("current_temp")
        return float(val) if isinstance(val, (int, float)) else None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set override targets from range or single temperature."""
        store = self.coordinator.hass.data[DOMAIN]["store"]
        mode = self._climate_mode()
        low = kwargs.get(ATTR_TARGET_TEMP_LOW)
        high = kwargs.get(ATTR_TARGET_TEMP_HIGH)
        single = kwargs.get(ATTR_TEMPERATURE)
        if low is not None or high is not None:
            heat, cool = low, high
        elif single is not None:
            room = self._room() or {}
            if mode == "cool_only":
                heat, cool = None, single
            elif mode == "heat_only":
                heat, cool = single, None
            else:
                # Auto: a bare `temperature` (legacy/external automation) must NOT
                # collapse to a single point (that is the cycling bug). Derive a
                # dead-band identically to the store migration.
                heat = single
                cool = max(single, room.get("comfort_cool", DEFAULT_COMFORT_COOL))
        else:
            return
        await store.async_update_room(
            self._area_id,
            {
                "override_heat": heat,
                "override_cool": cool,
                "override_until": None,
                "override_type": OVERRIDE_CUSTOM,
            },
        )
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Legacy override endpoint behaviour retained for automations."""
        store = self.coordinator.hass.data[DOMAIN]["store"]
        updates: dict[str, Any] | None
        if hvac_mode == HVACMode.OFF:
            updates = {"override_heat": None, "override_cool": None, "override_until": None, "override_type": None}
        elif not self._is_override_active():
            room = self._room() or {}
            mode = self._climate_mode()
            updates = {
                "override_heat": room.get("comfort_heat", DEFAULT_COMFORT_HEAT) if mode != "cool_only" else None,
                "override_cool": room.get("comfort_cool", DEFAULT_COMFORT_COOL) if mode != "heat_only" else None,
                "override_until": None,
                "override_type": OVERRIDE_CUSTOM,
            }
        else:
            updates = None
        if updates is not None:
            await store.async_update_room(self._area_id, updates)
        await self.coordinator.async_request_refresh()


class RoomMindClimate(RoomMindOverrideClimate):
    """Canonical logical room climate; never aggregates physical target states."""

    _attr_entity_registry_enabled_default = True
    _attr_icon = "mdi:home-thermometer"

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        self._area_id = area_id
        self._attr_unique_id = f"{DOMAIN}_{area_id}"
        self._attr_name = area_id
        self.entity_id = f"climate.{DOMAIN}_{area_id}"

    def _capabilities(self) -> RoomClimateCapabilities:
        return room_capabilities(self.coordinator.hass, self._room() or {})

    def _logical_targets(self) -> tuple[float, float]:
        room = self._room() or {}
        return (
            float(room.get("logical_heat_target", room.get("comfort_heat", DEFAULT_COMFORT_HEAT))),
            float(room.get("logical_cool_target", room.get("comfort_cool", DEFAULT_COMFORT_COOL))),
        )

    @property
    def hvac_modes(self) -> list[HVACMode]:
        return [HVACMode(mode) for mode in self._capabilities().hvac_modes]

    @property
    def hvac_mode(self) -> HVACMode:
        room = self._room() or {}
        selected = room.get("room_hvac_mode")
        if selected in self._capabilities().hvac_modes:
            return HVACMode(selected)
        # Existing users retain automatic RoomMind control without needing a
        # migration write; capability rather than member state is authoritative.
        return HVACMode.HEAT_COOL if HVACMode.HEAT_COOL in self.hvac_modes else self.hvac_modes[0]

    @property
    def supported_features(self) -> ClimateEntityFeature:
        caps = self._capabilities()
        mode = self.hvac_mode
        features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF

        # Temperature controls must describe the currently selected operating
        # mode, not every capability the room happens to have. In particular,
        # OFF and FAN_ONLY have no meaningful temperature setpoint.
        if mode in (HVACMode.HEAT_COOL, HVACMode.AUTO, HVACMode.HEAT, HVACMode.COOL, HVACMode.DRY):
            features |= ClimateEntityFeature.TARGET_TEMPERATURE

        if caps.fan_modes:
            features |= ClimateEntityFeature.FAN_MODE
        if caps.swing_modes:
            features |= ClimateEntityFeature.SWING_MODE
        if caps.swing_horizontal_modes:
            features |= ClimateEntityFeature.SWING_HORIZONTAL_MODE
        return features

    @property
    def target_temperature(self) -> float | None:
        mode = self.hvac_mode
        if mode in (HVACMode.OFF, HVACMode.FAN_ONLY):
            return None
        heat, cool = self._logical_targets()
        if mode in (HVACMode.HEAT_COOL, HVACMode.AUTO):
            return (heat + cool) / 2.0
        return cool if mode in (HVACMode.COOL, HVACMode.DRY) else heat

    @property
    def target_temperature_low(self) -> float | None:
        return None

    @property
    def target_temperature_high(self) -> float | None:
        return None

    @property
    def hvac_action(self) -> Any:
        mode = self.hvac_mode
        if mode == HVACMode.OFF:
            return None
        if mode == HVACMode.DRY:
            from homeassistant.components.climate import HVACAction

            return HVACAction.DRYING
        if mode == HVACMode.FAN_ONLY:
            from homeassistant.components.climate import HVACAction

            return HVACAction.FAN
        live = (self.coordinator.data or {}).get("rooms", {}).get(self._area_id, {})
        from homeassistant.components.climate import HVACAction

        commanded = live.get("commanded_mode")
        if commanded == "heating":
            return HVACAction.HEATING
        if commanded == "cooling":
            return HVACAction.COOLING
        return HVACAction.IDLE

    @property
    def fan_modes(self) -> list[str] | None:
        return list(self._capabilities().fan_modes) or None

    @property
    def fan_mode(self) -> str | None:
        return (self._room() or {}).get("room_fan_mode") or None

    @property
    def swing_modes(self) -> list[str] | None:
        return list(self._capabilities().swing_modes) or None

    @property
    def swing_mode(self) -> str | None:
        return (self._room() or {}).get("room_swing_mode") or None

    @property
    def swing_horizontal_modes(self) -> list[str] | None:
        return list(self._capabilities().swing_horizontal_modes) or None

    @property
    def swing_horizontal_mode(self) -> str | None:
        return (self._room() or {}).get("room_swing_horizontal_mode") or None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        selected = self.hvac_mode
        if selected in (HVACMode.OFF, HVACMode.FAN_ONLY):
            raise ValueError(f"Temperature cannot be set while RoomMind is in {selected.value} mode")

        heat, cool = self._logical_targets()
        low, high, single = (
            kwargs.get(ATTR_TARGET_TEMP_LOW),
            kwargs.get(ATTR_TARGET_TEMP_HIGH),
            kwargs.get(ATTR_TEMPERATURE),
        )
        if selected in (HVACMode.HEAT_COOL, HVACMode.AUTO):
            if single is not None:
                center = float(single)
            elif low is not None or high is not None:
                effective_low = float(low if low is not None else heat)
                effective_high = float(high if high is not None else cool)
                if effective_high < effective_low:
                    raise ValueError("Cooling target must be >= heating target")
                center = (effective_low + effective_high) / 2.0
            else:
                return
            # The canonical RoomMind climate exposes one user-facing setpoint.
            # Internally keep a 2 °C neutral band to avoid heat/cool cycling.
            heat = center - 1.0
            cool = center + 1.0
        else:
            if single is None:
                single = high if selected in (HVACMode.COOL, HVACMode.DRY) else low
            if single is None:
                return
            if selected in (HVACMode.COOL, HVACMode.DRY):
                cool = float(single)
            else:
                heat = float(single)
        if cool < heat:
            raise ValueError("Cooling target must be >= heating target")
        store = self.coordinator.hass.data[DOMAIN]["store"]
        mode = selected.value if selected != HVACMode.OFF else "heat_cool"
        await store.async_update_room(
            self._area_id,
            {
                "logical_heat_target": heat,
                "logical_cool_target": cool,
                "room_hvac_mode": mode,
                "override_heat": heat if mode in ("heat", "heat_cool", "auto") else None,
                "override_cool": cool if mode in ("cool", "heat_cool", "auto") else None,
                "override_until": None,
                "override_type": OVERRIDE_CUSTOM,
            },
        )
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode not in self.hvac_modes:
            raise ValueError(f"Unsupported room HVAC mode: {hvac_mode}")
        heat, cool = self._logical_targets()
        mode = hvac_mode.value
        updates = {"room_hvac_mode": mode, "override_until": None, "override_type": OVERRIDE_CUSTOM}
        updates["override_heat"] = heat if mode in ("heat", "heat_cool", "auto") else None
        updates["override_cool"] = cool if mode in ("cool", "heat_cool", "auto") else None
        if mode == "off":
            updates.update({"override_heat": None, "override_cool": None, "override_type": None})
        await self.coordinator.hass.data[DOMAIN]["store"].async_update_room(self._area_id, updates)

        # This entity is also RoomMind's manual/HomeKit control surface.  Manual
        # commands must work even when global or per-room automatic climate
        # control is disabled; those switches govern autonomous RoomMind logic,
        # not explicit user intent.
        await self._async_apply_manual_hvac_mode(mode, heat, cool)
        await self.coordinator.async_request_refresh()

    async def _async_apply_manual_hvac_mode(self, mode: str, heat: float, cool: float) -> None:
        room = self._room() or {}
        devices = room.get("devices", [])
        hass = self.coordinator.hass
        acs = get_ac_eids(devices)
        trvs = get_trv_eids(devices)

        if mode == "off":
            for entity_id in get_all_entity_ids(devices):
                await async_turn_off_climate(hass, entity_id, area_id=self._area_id)
            return

        # TRVs only participate in heating-capable manual modes.
        if mode in ("heat", "heat_cool", "auto"):
            ha_heat = celsius_to_ha_temp(hass, heat)
            for entity_id in trvs:
                state = hass.states.get(entity_id)
                modes = state.attributes.get("hvac_modes", []) if state else []
                resolved = resolve_hvac_mode("heat", modes)
                if resolved is not None:
                    await hass.services.async_call(
                        "climate",
                        "set_hvac_mode",
                        {"entity_id": entity_id, "hvac_mode": resolved},
                        blocking=True,
                    )
                    await hass.services.async_call(
                        "climate",
                        "set_temperature",
                        {"entity_id": entity_id, "temperature": ha_heat},
                        blocking=True,
                    )
        else:
            for entity_id in trvs:
                await async_turn_off_climate(hass, entity_id, area_id=self._area_id)

        if not acs:
            return
        entity_id = acs[0]
        state = hass.states.get(entity_id)
        supported = state.attributes.get("hvac_modes", []) if state else []
        resolved = resolve_hvac_mode(mode, supported)
        if resolved is None:
            return
        await hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": entity_id, "hvac_mode": resolved},
            blocking=True,
        )
        if mode in ("cool", "heat", "heat_cool", "auto"):
            data: dict[str, Any] = {"entity_id": entity_id}
            if mode in ("heat_cool", "auto") and state and state.attributes.get("target_temp_low") is not None:
                data.update(
                    target_temp_low=celsius_to_ha_temp(hass, heat),
                    target_temp_high=celsius_to_ha_temp(hass, cool),
                )
            else:
                target = cool if mode == "cool" else heat
                data["temperature"] = celsius_to_ha_temp(hass, target)
            await hass.services.async_call("climate", "set_temperature", data, blocking=True)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        if fan_mode not in self._capabilities().fan_modes:
            raise ValueError(f"Unsupported fan mode: {fan_mode}")
        await self._set_ac_option("room_fan_mode", "set_fan_mode", "fan_mode", fan_mode)
        await self.coordinator.async_request_refresh()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        if swing_mode not in self._capabilities().swing_modes:
            raise ValueError(f"Unsupported swing mode: {swing_mode}")
        await self._set_ac_option("room_swing_mode", "set_swing_mode", "swing_mode", swing_mode)
        await self.coordinator.async_request_refresh()

    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode: str) -> None:
        if swing_horizontal_mode not in self._capabilities().swing_horizontal_modes:
            raise ValueError(f"Unsupported horizontal swing mode: {swing_horizontal_mode}")
        await self._set_ac_option(
            "room_swing_horizontal_mode", "set_swing_horizontal_mode", "swing_horizontal_mode", swing_horizontal_mode
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_turn_on(self, **kwargs: Any) -> None:
        fallback = HVACMode.HEAT_COOL if HVACMode.HEAT_COOL in self.hvac_modes else HVACMode.HEAT
        await self.async_set_hvac_mode(fallback)

    async def _set_ac_option(self, key: str, service: str, service_key: str, value: str) -> None:
        acs = get_ac_eids((self._room() or {}).get("devices", []))
        if not acs:
            raise ValueError("Room has no AC device")
        store = self.coordinator.hass.data[DOMAIN]["store"]
        await store.async_update_room(self._area_id, {key: value})
        await self.coordinator.hass.services.async_call(
            "climate", service, {"entity_id": acs[0], service_key: value}, blocking=True
        )
