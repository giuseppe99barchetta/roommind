"""Select platform for RoomMind configuration entities."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RoomMindCoordinator, _get_room_display_name
from .utils.device_utils import get_ac_eids


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RoomMind configuration selects from a config entry."""
    coordinator: RoomMindCoordinator = hass.data[DOMAIN][entry.entry_id]
    store = hass.data[DOMAIN]["store"]
    coordinator.async_add_select_entities = async_add_entities

    entities: list[SelectEntity] = []
    for area_id, room in store.get_rooms().items():
        if get_ac_eids(room.get("devices", [])):
            entities.append(RoomMindDryEntityTypeSelect(coordinator, area_id))
            coordinator._dry_entity_type_select_areas.add(area_id)

    if entities:
        async_add_entities(entities)


class RoomMindDryEntityTypeSelect(CoordinatorEntity, SelectEntity):
    """Choose how an AC's Dry mode is exposed by RoomMind."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:water-sync"
    _attr_translation_key = "dry_entity_type"
    _attr_options = ["humidifier", "switch"]

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        """Initialize the selector."""
        super().__init__(coordinator)
        self._area_id = area_id
        self._attr_translation_placeholders = {"room": _get_room_display_name(coordinator.hass, area_id)}
        self._attr_unique_id = f"{DOMAIN}_{area_id}_dry_entity_type"
        self.entity_id = f"select.{DOMAIN}_{area_id}_dry_entity_type"

    @property
    def current_option(self) -> str:
        """Return the representation selected for this room."""
        room = self.coordinator.hass.data[DOMAIN]["store"].get_room(self._area_id) or {}
        return room.get("dry_entity_type", "switch")

    async def async_select_option(self, option: str) -> None:
        """Persist the selected representation and swap the endpoint."""
        store = self.coordinator.hass.data[DOMAIN]["store"]
        room = await store.async_update_room(self._area_id, {"dry_entity_type": option})
        await self.coordinator._async_sync_dry_entity(self._area_id, room)
        await self.coordinator.async_request_refresh()
