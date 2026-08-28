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
from .coordinator import RoomMindCoordinator, _get_room_display_name
from .managers.room_climate import RoomClimateCapabilities, room_capabilities
from .utils.device_utils import get_ac_eids, get_all_entity_ids, get_trv_eids
from .utils.temp_utils import celsius_to_ha_temp, quantize_temperature_for_entity


def _create_room_climates(
    coordinator: RoomMindCoordinator,
    area_id: str,
) -> list[ClimateEntity]:
    """Create climate entities for a room."""
    # The canonical entity has a stable, concise entity ID.  The old override
    # endpoint remains disabled by default for existing automations.
    return [RoomMindClimate(coordinator, area_id)]


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
    for area_id, room in rooms.items():
        if room.get("is_outdoor", False):
            continue
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
        self._attr_name = f"{_get_room_display_name(coordinator.hass, area_id)} Override"
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

    @property
    def current_humidity(self) -> float | None:
        """Return the room's current relative humidity from coordinator data."""
        data = self.coordinator.data
        if not data:
            return None
        room_data = data.get("rooms", {}).get(self._area_id)
        if not room_data:
            return None
        val = room_data.get("current_humidity")
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

    def _manual_activation_guard(self, mode: str) -> None:
        """Reject manual thermal activation when a hard safety blocks it."""
        if mode not in ("heat", "cool", "dry"):
            return

        room = self._room() or {}
        hass = self.coordinator.hass
        acs = get_ac_eids(room.get("devices", []))
        if not acs:
            return
        store = hass.data[DOMAIN]["store"]
        settings = store.get_settings()

        compressor = self.coordinator._compressor_manager
        compressor.load_groups(settings.get("compressor_groups", []))
        for entity_id in acs:
            state = hass.states.get(entity_id)
            already_running = bool(state and state.state not in ("off", "unknown", "unavailable", "fan_only"))
            if not already_running and not compressor.check_can_activate(entity_id):
                raise ValueError(f"Compressor minimum-off protection blocks {entity_id}")

        if not settings.get("power_budget_enabled", False):
            return

        running_loads: dict[str, float] = {}
        for area_id, other in store.get_rooms().items():
            other_acs = get_ac_eids(other.get("devices", []))
            if any(
                (state := hass.states.get(entity_id))
                and state.state not in ("off", "unknown", "unavailable", "fan_only")
                for entity_id in other_acs
            ):
                running_loads[area_id] = float(other.get("heat_pump_power_watts", 0) or 0)

        budget = self.coordinator._power_budget_manager
        budget.begin_cycle(hass, settings, running_loads)
        if not budget.request_heat_pump(
            self._area_id,
            float(room.get("heat_pump_power_watts", 0) or 0),
            self._area_id in running_loads,
        ):
            raise ValueError("RoomMind power budget blocks this climate activation")

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
        self._attr_name = _get_room_display_name(coordinator.hass, area_id)
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

    def _physical_ac_modes(self) -> tuple[str, ...]:
        modes: list[str] = []
        for entity_id in get_ac_eids((self._room() or {}).get("devices", [])):
            state = self.coordinator.hass.states.get(entity_id)
            if state is not None and state.state not in ("unknown", "unavailable"):
                modes.append(state.state)
        return tuple(modes)

    @property
    def hvac_mode(self) -> HVACMode:
        room = self._room() or {}
        selected = room.get("room_hvac_mode")
        # Backward compatibility for rooms persisted before AUTO replaced the
        # misleading HEAT_COOL label on the canonical entity.
        if selected == "heat_cool":
            selected = "auto"

        # FAN_ONLY and DRY are direct physical AC modes, not autonomous RoomMind
        # control states. A persisted value must never make an AC that is really
        # off look active after restart or an external power-off.
        if selected in ("fan_only", "dry"):
            return HVACMode(selected) if selected in self._physical_ac_modes() else HVACMode.OFF

        if selected in self._capabilities().hvac_modes:
            return HVACMode(selected)
        # A configured room starts in logical AUTO when both directions are
        # available; AUTO means RoomMind may choose heat/cool, not that either is
        # currently running.
        return HVACMode.AUTO if HVACMode.AUTO in self.hvac_modes else self.hvac_modes[0]

    def _target_control_mode(self) -> HVACMode | None:
        """Return the thermal mode whose target should remain visible to clients."""
        room = self._room() or {}
        selected = room.get("room_hvac_mode")
        if selected == "heat_cool":
            selected = "auto"
        if selected in ("auto", "heat", "cool", "dry"):
            return HVACMode(selected)

        last = room.get("room_last_hvac_mode")
        if last == "heat_cool":
            last = "auto"
        if last in ("auto", "heat", "cool", "dry") and HVACMode(last) in self.hvac_modes:
            return HVACMode(last)

        if HVACMode.AUTO in self.hvac_modes:
            return HVACMode.AUTO
        if HVACMode.COOL in self.hvac_modes:
            return HVACMode.COOL
        if HVACMode.HEAT in self.hvac_modes:
            return HVACMode.HEAT
        return None

    @property
    def supported_features(self) -> ClimateEntityFeature:
        caps = self._capabilities()
        features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF

        # Capabilities must be stable across runtime state changes. HomeKit builds
        # its accessory characteristics from this bitmask when the accessory is
        # created, so dropping TARGET_TEMPERATURE while OFF/FAN_ONLY leaves a
        # permanently incomplete accessory until it is recreated.
        if any(mode in caps.hvac_modes for mode in ("auto", "heat", "cool", "dry")):
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
        mode = self._target_control_mode()
        if mode is None:
            return None
        heat, cool = self._logical_targets()
        if mode == HVACMode.AUTO:
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
        fan_mode = (self._room() or {}).get("room_fan_mode")
        return fan_mode if fan_mode in self._capabilities().fan_modes else None

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Expose a saved fan setting that cannot apply in the current HVAC mode."""
        fan_mode = (self._room() or {}).get("room_fan_mode")
        if fan_mode and fan_mode not in self._capabilities().fan_modes:
            return {"fan_mode_unavailable": fan_mode}
        return {}

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
        current_mode = self.hvac_mode
        inactive = current_mode in (HVACMode.OFF, HVACMode.FAN_ONLY)
        selected = self._target_control_mode() if inactive else current_mode
        if selected is None:
            raise ValueError("Room has no temperature-controllable HVAC mode")

        heat, cool = self._logical_targets()
        low, high, single = (
            kwargs.get(ATTR_TARGET_TEMP_LOW),
            kwargs.get(ATTR_TARGET_TEMP_HIGH),
            kwargs.get(ATTR_TEMPERATURE),
        )
        if selected == HVACMode.AUTO:
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
        if inactive:
            # OFF/FAN_ONLY still expose a usable setpoint to HA/HomeKit, but a
            # setpoint edit must never wake hardware or change the selected mode.
            await store.async_update_room(
                self._area_id,
                {
                    "logical_heat_target": heat,
                    "logical_cool_target": cool,
                },
            )
            await self.coordinator.async_request_refresh()
            return

        if selected in (HVACMode.HEAT, HVACMode.COOL, HVACMode.DRY):
            self._manual_activation_guard(selected.value)
        mode = selected.value
        await store.async_update_room(
            self._area_id,
            {
                "logical_heat_target": heat,
                "logical_cool_target": cool,
                "room_hvac_mode": mode,
                "room_last_hvac_mode": mode,
                "override_heat": heat if mode in ("heat", "auto") else None,
                "override_cool": cool if mode in ("cool", "auto") else None,
                "override_until": None,
                "override_type": OVERRIDE_CUSTOM,
            },
        )
        # A setpoint changed through the canonical entity is an explicit user
        # command (HA/HomeKit). Persisting it is not enough: forward it to the
        # physical device that is currently responsible for that direction.
        await self._async_apply_manual_temperature(selected, heat, cool)
        await self.coordinator.async_request_refresh()

    async def _async_apply_manual_temperature(self, selected: HVACMode, heat: float, cool: float) -> None:
        room = self._room() or {}
        devices = room.get("devices", [])
        hass = self.coordinator.hass
        acs = get_ac_eids(devices)
        trvs = get_trv_eids(devices)

        direction = selected.value
        if selected == HVACMode.AUTO:
            live = (self.coordinator.data or {}).get("rooms", {}).get(self._area_id, {})
            commanded = live.get("commanded_mode")
            if commanded == "cooling":
                direction = "cool"
            elif commanded == "heating":
                direction = "heat"
            else:
                # AUTO while idle only changes RoomMind's logical setpoint. Do
                # not wake any physical climate device just to change a target.
                return

        if direction == "heat":
            raw_target = celsius_to_ha_temp(hass, heat)
            for entity_id in trvs:
                target = quantize_temperature_for_entity(hass, entity_id, raw_target, fallback_step=0.5)
                await hass.services.async_call(
                    "climate",
                    "set_temperature",
                    {"entity_id": entity_id, "temperature": target},
                    blocking=True,
                )
            for entity_id in acs:
                state = hass.states.get(entity_id)
                modes = state.attributes.get("hvac_modes", []) if state else []
                if resolve_hvac_mode("heat", modes) is not None:
                    target = quantize_temperature_for_entity(hass, entity_id, raw_target, fallback_step=1.0)
                    await hass.services.async_call(
                        "climate",
                        "set_temperature",
                        {"entity_id": entity_id, "temperature": target},
                        blocking=True,
                    )
            return

        if direction in ("cool", "dry"):
            raw_target = celsius_to_ha_temp(hass, cool)
            for entity_id in acs:
                target = quantize_temperature_for_entity(hass, entity_id, raw_target, fallback_step=1.0)
                await hass.services.async_call(
                    "climate",
                    "set_temperature",
                    {"entity_id": entity_id, "temperature": target},
                    blocking=True,
                )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.HEAT_COOL and HVACMode.AUTO in self.hvac_modes:
            hvac_mode = HVACMode.AUTO
        if hvac_mode not in self.hvac_modes:
            raise ValueError(f"Unsupported room HVAC mode: {hvac_mode}")
        heat, cool = self._logical_targets()
        mode = hvac_mode.value
        room = self._room() or {}
        updates = {"room_hvac_mode": mode, "override_until": None, "override_type": OVERRIDE_CUSTOM}
        updates["override_heat"] = heat if mode in ("heat", "auto") else None
        updates["override_cool"] = cool if mode in ("cool", "auto") else None
        if mode == "off":
            previous = room.get("room_hvac_mode")
            if previous == "heat_cool":
                previous = "auto"
            if previous in ("auto", "heat", "cool", "dry"):
                updates["room_last_hvac_mode"] = previous
            updates.update({"override_heat": None, "override_cool": None, "override_type": None})
        elif mode in ("auto", "heat", "cool", "dry"):
            updates["room_last_hvac_mode"] = mode
        # Explicit HEAT/COOL/OFF/FAN_ONLY/DRY are direct manual commands. AUTO
        # is different: it is permission for RoomMind to choose one direction,
        # so it must never directly switch both heating and cooling hardware on.
        # Validate hard safety before persisting a mode that cannot be applied.
        if mode != "auto":
            self._manual_activation_guard(mode)
            await self._async_apply_manual_hvac_mode(mode, heat, cool)
        await self.coordinator.hass.data[DOMAIN]["store"].async_update_room(self._area_id, updates)
        if mode != "off":
            await self._async_apply_stored_ac_options()
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
                self.coordinator._compressor_manager.update_member(entity_id, False)
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
                    trv_target = quantize_temperature_for_entity(hass, entity_id, ha_heat, fallback_step=0.5)
                    await hass.services.async_call(
                        "climate",
                        "set_temperature",
                        {"entity_id": entity_id, "temperature": trv_target},
                        blocking=True,
                    )
        else:
            for entity_id in trvs:
                await async_turn_off_climate(hass, entity_id, area_id=self._area_id)

        if not acs:
            return
        compressor = self.coordinator._compressor_manager
        for entity_id in acs:
            state = hass.states.get(entity_id)
            supported = state.attributes.get("hvac_modes", []) if state else []
            resolved = resolve_hvac_mode(mode, supported)
            if resolved is None:
                continue
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
                        target_temp_low=quantize_temperature_for_entity(
                            hass, entity_id, celsius_to_ha_temp(hass, heat), fallback_step=1.0
                        ),
                        target_temp_high=quantize_temperature_for_entity(
                            hass, entity_id, celsius_to_ha_temp(hass, cool), fallback_step=1.0
                        ),
                    )
                else:
                    target = cool if mode == "cool" else heat
                    data["temperature"] = quantize_temperature_for_entity(
                        hass, entity_id, celsius_to_ha_temp(hass, target), fallback_step=1.0
                    )
                await hass.services.async_call("climate", "set_temperature", data, blocking=True)
            compressor.update_member(entity_id, mode in ("heat", "cool", "dry"))

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
        room = self._room() or {}
        last = room.get("room_last_hvac_mode")
        if last == "heat_cool":
            last = "auto"
        try:
            preferred = HVACMode(last) if last else None
        except ValueError:
            preferred = None
        if preferred not in self.hvac_modes or preferred == HVACMode.OFF:
            preferred = (
                HVACMode.AUTO
                if HVACMode.AUTO in self.hvac_modes
                else next((mode for mode in self.hvac_modes if mode != HVACMode.OFF), HVACMode.OFF)
            )
        await self.async_set_hvac_mode(preferred)

    async def _async_apply_stored_ac_options(self) -> None:
        """Apply fan/swing settings that may have been edited while the room was off."""
        room = self._room() or {}
        acs = get_ac_eids(room.get("devices", []))
        if not acs:
            return
        options = (
            ("room_fan_mode", "set_fan_mode", "fan_mode", "fan_modes"),
            ("room_swing_mode", "set_swing_mode", "swing_mode", "swing_modes"),
            (
                "room_swing_horizontal_mode",
                "set_swing_horizontal_mode",
                "swing_horizontal_mode",
                "swing_horizontal_modes",
            ),
        )
        for key, service, service_key, supported_key in options:
            value = room.get(key)
            if not value:
                continue
            for entity_id in acs:
                state = self.coordinator.hass.states.get(entity_id)
                if state is None or value not in (state.attributes.get(supported_key) or []):
                    continue
                await self.coordinator.hass.services.async_call(
                    "climate", service, {"entity_id": entity_id, service_key: value}, blocking=True
                )

    async def _set_ac_option(self, key: str, service: str, service_key: str, value: str) -> None:
        acs = get_ac_eids((self._room() or {}).get("devices", []))
        if not acs:
            raise ValueError("Room has no AC device")
        store = self.coordinator.hass.data[DOMAIN]["store"]
        await store.async_update_room(self._area_id, {key: value})
        if self.hvac_mode == HVACMode.OFF:
            return
        for entity_id in acs:
            await self.coordinator.hass.services.async_call(
                "climate", service, {"entity_id": entity_id, service_key: value}, blocking=True
            )
