from pathlib import Path

p = Path("custom_components/roommind/control/mpc_controller.py")
text = p.read_text()
text = text.replace(
'''def _snap_to_step(hass: HomeAssistant, value: float, step: float | None) -> float:
    return quantize_temperature_to_step(value, step, get_temperature_rounding_mode(hass))''',
'''def _snap_to_step(
    value: float,
    step: float | None,
    hass: HomeAssistant | None = None,
) -> float:
    """Snap to a device step while preserving the legacy two-argument API."""
    mode = get_temperature_rounding_mode(hass) if hass is not None else "nearest"
    return quantize_temperature_to_step(value, step, mode)''',
)
# async_idle_device is a module-level function, so use its hass argument.
text = text.replace(
    "_snap_to_step(self.hass, ha_t, float(step))",
    "_snap_to_step(ha_t, float(step), hass)",
)
# MPCController methods have self.hass.
text = text.replace(
    '_snap_to_step(self.hass, data["temperature"], step)',
    '_snap_to_step(data["temperature"], step, self.hass)',
)
text = text.replace(
    '_snap_to_step(self.hass, data["target_temp_low"], step)',
    '_snap_to_step(data["target_temp_low"], step, self.hass)',
)
text = text.replace(
    '_snap_to_step(self.hass, data["target_temp_high"], step)',
    '_snap_to_step(data["target_temp_high"], step, self.hass)',
)
p.write_text(text)

# The default nearest policy is intentionally deterministic half-up now,
# replacing the old Python banker-rounding expectation.
p = Path("tests/control/test_apply.py")
text = p.read_text()
text = text.replace(
    '(22.5, 1.0, 22.0),  # banker\'s rounding: .5 rounds to even',
    '(22.5, 1.0, 23.0),  # RoomMind nearest is deterministic half-up',
)
text = text.replace(
    '(23.5, 1.0, 24.0),  # .5 rounds to even',
    '(23.5, 1.0, 24.0),  # half-up',
)
p.write_text(text)

print("temperature rounding compatibility corrections applied")
