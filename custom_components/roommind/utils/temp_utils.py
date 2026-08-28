"""Temperature unit conversion utilities for RoomMind."""

from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant

from ..const import DOMAIN


def _is_fahrenheit(hass: HomeAssistant, entity_id: str | None = None) -> bool:
    """Check if the value is in Fahrenheit.

    When *entity_id* is provided the entity's own ``unit_of_measurement``
    attribute is used.  This is race-condition-safe during HA unit-system
    changes because entity state + attributes are always updated atomically.
    Falls back to the global HA config when no entity is given.
    """
    if entity_id:
        state = hass.states.get(entity_id)
        if state:
            uom = state.attributes.get("unit_of_measurement")
            if uom:
                return bool(uom == "°F")
    return bool(hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT)


def ha_temp_to_celsius(
    hass: HomeAssistant,
    value: float,
    *,
    entity_id: str | None = None,
) -> float:
    """Convert temperature from HA unit system to Celsius.

    Pass *entity_id* when reading from a sensor entity to avoid race
    conditions during unit-system changes.
    """
    if _is_fahrenheit(hass, entity_id):
        return (value - 32) * 5 / 9
    return value


def celsius_to_ha_temp(hass: HomeAssistant, value: float) -> float:
    """Convert temperature from Celsius to HA unit system."""
    if hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT:
        return value * 9 / 5 + 32
    return value


def celsius_delta_to_ha(hass: HomeAssistant, delta: float) -> float:
    """Convert a temperature delta from Celsius to HA unit system (factor only)."""
    if hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT:
        return delta * 9 / 5
    return delta


def ha_temp_unit_str(hass: HomeAssistant) -> str:
    """Return '°C' or '°F' based on HA config."""
    if hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT:
        return "°F"
    return "°C"


TEMPERATURE_ROUNDING_MODES = {"nearest", "down", "up"}
DEFAULT_TEMPERATURE_ROUNDING_MODE = "nearest"


def get_temperature_rounding_mode(hass: HomeAssistant) -> str:
    """Return the global physical-device temperature rounding preference."""
    try:
        store = hass.data.get(DOMAIN, {}).get("store")
        mode = store.get_settings().get("temperature_rounding_mode") if store else None
    except (AttributeError, TypeError):
        mode = None
    return mode if mode in TEMPERATURE_ROUNDING_MODES else DEFAULT_TEMPERATURE_ROUNDING_MODE


def quantize_temperature_to_step(value: float, step: float | None, mode: str = "nearest") -> float:
    """Quantize *value* to *step* using deterministic up/down/nearest rounding."""
    import math

    if step is None or step <= 0:
        return float(value)
    if mode not in TEMPERATURE_ROUNDING_MODES:
        mode = DEFAULT_TEMPERATURE_ROUNDING_MODE

    ratio = float(value) / float(step)
    epsilon = 1e-9
    if mode == "down":
        units = math.floor(ratio + epsilon)
    elif mode == "up":
        units = math.ceil(ratio - epsilon)
    else:
        # Half-up instead of Python's bankers rounding: 26.5 -> 27 for step 1.
        units = math.floor(ratio + 0.5 + epsilon)
    return round(units * float(step), 3)


def quantize_temperature_for_entity(
    hass: HomeAssistant,
    entity_id: str,
    value: float,
    *,
    fallback_step: float | None = None,
) -> float:
    """Quantize an HA-unit setpoint to a climate entity's supported step."""
    state = hass.states.get(entity_id)
    attrs = state.attributes if state is not None else {}
    raw_step = attrs.get("target_temp_step", fallback_step)
    try:
        step = float(raw_step) if raw_step is not None else None
    except (TypeError, ValueError):
        step = fallback_step

    result = quantize_temperature_to_step(value, step, get_temperature_rounding_mode(hass))
    for key, fn in (("min_temp", max), ("max_temp", min)):
        raw = attrs.get(key)
        if raw is not None:
            try:
                result = fn(result, float(raw))
            except (TypeError, ValueError):
                pass
    return round(result, 3)
