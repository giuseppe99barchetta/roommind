"""Humidifier platform for RoomMind."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import HVACMode
from homeassistant.components.humidifier import HumidifierDeviceClass, HumidifierEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .climate import RoomMindClimate
from .const import DOMAIN
from .coordinator import RoomMindCoordinator, _get_room_display_name
from .managers.room_climate import room_capabilities
from .utils.device_utils import get_ac_eids


def _room_has_ac(room: dict) -> bool:
    """Return whether the room has a configured air conditioner."""
    return bool(get_ac_eids(room.get("devices", [])))


def _is_humidifier_representation(room: dict) -> bool:
    """Return whether the room exposes Dry as a dehumidifier entity."""
    return room.get("dry_entity_type", "switch") == "humidifier"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RoomMind dehumidifier entities from a config entry."""
    coordinator: RoomMindCoordinator = hass.data[DOMAIN][entry.entry_id]
    store = hass.data[DOMAIN]["store"]
    coordinator.async_add_humidifier_entities = async_add_entities

    entities: list[HumidifierEntity] = []
    for area_id, room in store.get_rooms().items():
        if _room_has_ac(room) and _is_humidifier_representation(room):
            entities.append(RoomMindDryDehumidifier(coordinator, area_id))
            coordinator._dry_humidifier_entity_areas.add(area_id)

    if entities:
        async_add_entities(entities)


class RoomMindDryDehumidifier(CoordinatorEntity, HumidifierEntity):
    """Expose an AC's Dry mode as a dehumidifier with room humidity."""

    _attr_has_entity_name = True
    _attr_device_class = HumidifierDeviceClass.DEHUMIDIFIER
    _attr_icon = "mdi:water-percent"
    _attr_translation_key = "dry_dehumidifier"

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._area_id = area_id
        self._attr_translation_placeholders = {"room": _get_room_display_name(coordinator.hass, area_id)}
        self._attr_unique_id = f"{DOMAIN}_{area_id}_dehumidification"
        self.entity_id = f"humidifier.{DOMAIN}_{area_id}_dehumidification"

    def _room(self) -> dict:
        """Return the current room configuration."""
        return self.coordinator.hass.data[DOMAIN]["store"].get_room(self._area_id) or {}

    def _climate(self) -> RoomMindClimate:
        """Return the canonical RoomMind climate for this room."""
        return RoomMindClimate(self.coordinator, self._area_id)

    @property
    def available(self) -> bool:
        """Only expose active control when Dry is supported and selected."""
        room = self._room()
        return _is_humidifier_representation(room) and HVACMode.DRY.value in room_capabilities(
            self.coordinator.hass, room
        ).hvac_modes

    @property
    def is_on(self) -> bool:
        """Return whether the AC is currently in Dry mode."""
        return self._climate().hvac_mode == HVACMode.DRY

    @property
    def current_humidity(self) -> float | None:
        """Return the configured room humidity reading for HomeKit."""
        humidity_sensor = self._room().get("humidity_sensor")
        state = self.coordinator.hass.states.get(humidity_sensor) if humidity_sensor else None
        if state is None:
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activate the AC's Dry mode."""
        await self._climate().async_set_hvac_mode(HVACMode.DRY)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the AC off only when this entity activated Dry mode."""
        if self._room().get("room_hvac_mode") == HVACMode.DRY.value:
            await self._climate().async_set_hvac_mode(HVACMode.OFF)
