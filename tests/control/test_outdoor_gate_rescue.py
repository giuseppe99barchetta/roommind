"""Outdoor gate rescue lets rooms far from target ignore the season heuristic."""

from custom_components.roommind.const import MODE_COOLING, MODE_HEATING
from custom_components.roommind.control.mpc_controller import get_can_heat_cool
from custom_components.roommind.control.mpc_optimizer import MPCOptimizer

ROOM = {
    "climate_mode": "auto",
    "devices": [{"entity_id": "climate.trv", "type": "trv"}, {"entity_id": "climate.ac", "type": "ac"}],
}


def test_gate_blocks_without_rescue():
    assert get_can_heat_cool(ROOM, 15.0, 27.0, 10.0) == (False, False)


def test_rescue_is_per_direction():
    room = {**ROOM, "_outdoor_gate_rescue": {"heat": True}}
    assert get_can_heat_cool(room, 15.0, 27.0, 10.0) == (True, False)
    room = {**ROOM, "_outdoor_gate_rescue": {"cool": True}}
    assert get_can_heat_cool(room, 15.0, 27.0, 10.0) == (False, True)


def test_optimizer_honours_rescue():
    optimizer = MPCOptimizer(model=None, outdoor_heating_max=10.0, outdoor_cooling_min=27.0)  # type: ignore[arg-type]
    assert optimizer._is_outdoor_gated(MODE_HEATING, 15.0)
    optimizer = MPCOptimizer(
        model=None,
        outdoor_heating_max=10.0,
        outdoor_cooling_min=27.0,
        gate_rescue={"heat": True},  # type: ignore[arg-type]
    )
    assert not optimizer._is_outdoor_gated(MODE_HEATING, 15.0)
    assert optimizer._is_outdoor_gated(MODE_COOLING, 15.0)
