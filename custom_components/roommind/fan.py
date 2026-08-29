"""Optional fan entities for direct HomeKit fan-speed control."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import HVACMode
from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.percentage import ordered_list_item_to_percentage, percentage_to_ordered_list_item

from .climate import RoomMindClimate
from .const import DOMAIN
from .coordinator import RoomMindCoordinator, _get_room_display_name
from .managers.room_climate import room_capabilities
from .utils.device_utils import get_ac_eids


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up disabled-by-default HomeKit fan entities for rooms with ACs."""
    coordinator: RoomMindCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_add_fan_entities = async_add_entities
    entities = [
        RoomMindFan(coordinator, area_id)
        for area_id, room in hass.data[DOMAIN]["store"].get_rooms().items()
        if not room.get("is_outdoor", False) and get_ac_eids(room.get("devices", []))
    ]
    coordinator._fan_entity_areas.update(entity._area_id for entity in entities)
    if entities:
        async_add_entities(entities)


class RoomMindFan(CoordinatorEntity, FanEntity):
    """Expose a room's physical AC fan as a separately selectable fan entity."""

    _attr_has_entity_name = True
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:fan"

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator)
        self._area_id = area_id
        self._attr_unique_id = f"{DOMAIN}_{area_id}_fan"
        self._attr_name = f"{_get_room_display_name(coordinator.hass, area_id)} Fan"
        self.entity_id = f"fan.{DOMAIN}_{area_id}"

    def _climate(self) -> RoomMindClimate:
        return RoomMindClimate(self.coordinator, self._area_id)

    def _speed_modes(self) -> list[str]:
        room = self.coordinator.hass.data[DOMAIN]["store"].get_room(self._area_id) or {}
        return [
            mode
            for mode in room_capabilities(self.coordinator.hass, room).fan_modes
            if mode.lower() not in {"auto", "off", "on"}
        ]

    @property
    def available(self) -> bool:
        room = self.coordinator.hass.data[DOMAIN]["store"].get_room(self._area_id) or {}
        return HVACMode.FAN_ONLY.value in room_capabilities(self.coordinator.hass, room).hvac_modes

    @property
    def is_on(self) -> bool:
        room = self.coordinator.hass.data[DOMAIN]["store"].get_room(self._area_id)
        return bool(room and self._climate().hvac_mode == HVACMode.FAN_ONLY)

    @property
    def supported_features(self) -> FanEntityFeature:
        features = FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        return features | FanEntityFeature.SET_SPEED if self._speed_modes() else features

    @property
    def percentage(self) -> int | None:
        if not self.coordinator.hass.data[DOMAIN]["store"].get_room(self._area_id):
            return None
        mode = self._climate().fan_mode
        speeds = self._speed_modes()
        return ordered_list_item_to_percentage(speeds, mode) if mode in speeds else None

    @property
    def speed_count(self) -> int:
        """Return the number of discrete speeds exposed by the AC."""
        return len(self._speed_modes())

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on fan-only, applying a requested speed before activation."""
        if percentage is not None and percentage > 0:
            await self.async_set_percentage(percentage)
            return
        await self._climate().async_set_hvac_mode(HVACMode.FAN_ONLY)

    async def async_turn_off(self, **kwargs: object) -> None:
        if self.is_on:
            await self._climate().async_set_hvac_mode(HVACMode.OFF)

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage <= 0:
            await self.async_turn_off()
            return
        speeds = self._speed_modes()
        if not speeds:
            return
        climate = self._climate()
        await climate.async_set_fan_mode(percentage_to_ordered_list_item(speeds, percentage))
        if not self.is_on:
            # HomeKit sends Active and RotationSpeed together and expects the
            # speed write itself to start the fan. Saving the desired mode
            # first lets RoomMind apply it as part of the FAN_ONLY activation.
            await climate.async_set_hvac_mode(HVACMode.FAN_ONLY)
