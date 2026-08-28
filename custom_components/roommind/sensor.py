"""Sensor platform for RoomMind."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RoomMindCoordinator, _get_room_display_name, _room_has_power_sensor


def _create_room_energy_entities(coordinator: RoomMindCoordinator, area_id: str) -> list[SensorEntity]:
    """Create sensors backed by a configured AC consumption sensor."""
    return [
        RoomMindPowerSensor(coordinator, area_id),
        RoomMindEnergyTodaySensor(coordinator, area_id),
        RoomMindPredictedPowerSensor(coordinator, area_id),
        RoomMindPredictedEnergySensor(coordinator, area_id),
        RoomMindPredictedEnergyConfidenceSensor(coordinator, area_id),
    ]


def _create_room_entities(
    coordinator: RoomMindCoordinator, area_id: str, room: dict | None = None
) -> list[SensorEntity]:
    """Create room sensors, adding energy entities only when they are meaningful."""
    if room is None:
        store = coordinator.hass.data[DOMAIN]["store"]
        room = store.get_room(area_id) or {}
    entities: list[SensorEntity] = [
        RoomMindTargetTemperatureSensor(coordinator, area_id),
        RoomMindModeSensor(coordinator, area_id),
        RoomMindHeatSourceSensor(coordinator, area_id),
        RoomMindHeatSourceReasonSensor(coordinator, area_id),
    ]
    if _room_has_power_sensor(room):
        entities.extend(_create_room_energy_entities(coordinator, area_id))
    return entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RoomMind sensor entities from a config entry."""
    coordinator: RoomMindCoordinator = hass.data[DOMAIN][entry.entry_id]
    store = hass.data[DOMAIN]["store"]

    # Store the callback on the coordinator so dynamic entity creation works
    coordinator.async_add_entities = async_add_entities

    # Create entities for rooms that already exist in the store
    rooms = store.get_rooms()
    entities: list[SensorEntity] = []
    for area_id, room in rooms.items():
        entities.extend(_create_room_entities(coordinator, area_id, room))
        coordinator._entity_areas.add(area_id)
        if _room_has_power_sensor(room):
            coordinator._energy_entity_areas.add(area_id)
    entities.extend(
        [
            RoomMindBoilerDemandSensor(coordinator),
            RoomMindAvailablePowerSensor(coordinator),
            RoomMindReservedPowerSensor(coordinator),
        ]
    )
    if entities:
        async_add_entities(entities)


class _RoomMindBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for all RoomMind room sensors."""

    _attr_has_entity_name = True
    _data_key: str  # Key in the room state dict (e.g. "current_temp")

    def __init__(
        self,
        coordinator: RoomMindCoordinator,
        area_id: str,
        suffix: str,
        name_label: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._area_id = area_id
        self._attr_unique_id = f"{DOMAIN}_{area_id}_{suffix}"
        self._attr_name = f"{_get_room_display_name(coordinator.hass, area_id)} {name_label}"
        self.entity_id = f"sensor.{DOMAIN}_{area_id}_{suffix}"

    @property
    def native_value(self) -> float | str | None:
        """Return the sensor value from the coordinator data."""
        room = self.coordinator.data.get("rooms", {}).get(self._area_id)
        if room:
            val = room.get(self._data_key)
            return val if isinstance(val, (float, int, str)) else None
        return None


class RoomMindTargetTemperatureSensor(_RoomMindBaseSensor):
    """Sensor showing the target temperature for a RoomMind room."""

    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _data_key = "target_temp"

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator, area_id, "target_temp", "Target Temperature")


class RoomMindModeSensor(_RoomMindBaseSensor):
    """Sensor showing the current mode for a RoomMind room."""

    _data_key = "mode"

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator, area_id, "mode", "Mode")

    @property
    def native_value(self) -> str | None:
        """Return the current mode, defaulting to 'idle'."""
        room = self.coordinator.data.get("rooms", {}).get(self._area_id)
        if room:
            val = room.get("mode", "idle")
            return str(val) if val is not None else "idle"
        return "idle"


class RoomMindHeatSourceSensor(_RoomMindBaseSensor):
    _data_key = "heat_source"

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator, area_id, "heat_source", "Heat Source")


class RoomMindHeatSourceReasonSensor(_RoomMindBaseSensor):
    _data_key = "heat_source_reason"

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator, area_id, "heat_source_reason", "Heat Source Reason")


class RoomMindPowerSensor(_RoomMindBaseSensor):
    _data_key = "ac_power_w"
    _attr_native_unit_of_measurement = "W"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator, area_id, "power", "AC Power")


class RoomMindEnergyTodaySensor(_RoomMindBaseSensor):
    _data_key = "ac_energy_today_kwh"
    _attr_native_unit_of_measurement = "kWh"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator, area_id, "energy_today", "AC Energy Today")


class RoomMindPredictedPowerSensor(_RoomMindBaseSensor):
    _data_key = "predicted_power_w"
    _attr_native_unit_of_measurement = "W"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator, area_id, "predicted_power", "Predicted AC Power")


class RoomMindPredictedEnergySensor(_RoomMindBaseSensor):
    _data_key = "predicted_energy_1h_kwh"
    _attr_native_unit_of_measurement = "kWh"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator, area_id, "predicted_energy_1h", "Predicted AC Energy 1h")


class RoomMindPredictedEnergyConfidenceSensor(_RoomMindBaseSensor):
    """Reliability level of the learned one-hour AC energy forecast."""

    _data_key = "energy_prediction_confidence"

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator, area_id, "predicted_energy_confidence", "Predicted AC Energy Confidence")


class _GlobalSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _key: str

    def __init__(self, coordinator: RoomMindCoordinator, suffix: str, name: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{suffix}"
        self._attr_name = name
        self.entity_id = f"sensor.{DOMAIN}_{suffix}"

    @property
    def native_value(self) -> Any:
        return (self.coordinator.data or {}).get(self._key)


class RoomMindBoilerDemandSensor(_GlobalSensor):
    _key = "boiler_demand"

    def __init__(self, coordinator: RoomMindCoordinator) -> None:
        super().__init__(coordinator, "boiler_demand", "Boiler Demand")


class RoomMindAvailablePowerSensor(_GlobalSensor):
    _key = "available_power"
    _attr_native_unit_of_measurement = "W"

    def __init__(self, coordinator: RoomMindCoordinator) -> None:
        super().__init__(coordinator, "available_power", "Available Power")


class RoomMindReservedPowerSensor(_GlobalSensor):
    _key = "reserved_power"
    _attr_native_unit_of_measurement = "W"

    def __init__(self, coordinator: RoomMindCoordinator) -> None:
        super().__init__(coordinator, "reserved_power", "Reserved Power")
