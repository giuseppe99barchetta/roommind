"""Tests for the native heat-source engine (heat pump / hybrid / boiler)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from custom_components.roommind.const import MODE_HEATING
from custom_components.roommind.managers.heat_source_orchestrator import evaluate_native_heat_sources

from . import test_heat_source_integration as hsi
from .test_heat_source_integration import DEFAULT_SETTINGS, ROOM_WITH_TRV_AND_AC, _make_hass_states, _setup_store

# Reuse the integration fixtures (TRV + AC room, real store).
coordinator = hsi.coordinator
real_store = hsi.real_store

# cold=2, mild=8, hybrid gap=1.5, hysteresis=0.5
ROOM = {
    "heat_source_orchestration": True,
    "heat_source_boiler_outdoor_threshold": 2.0,
    "heat_source_heat_pump_outdoor_threshold": 8.0,
    "heat_source_hybrid_delta": 1.5,
    "heat_source_hysteresis": 0.5,
    "devices": [{"entity_id": "climate.trv", "type": "trv"}, {"entity_id": "climate.ac", "type": "ac"}],
}


def _hass() -> MagicMock:
    hass = MagicMock()
    st = MagicMock()
    st.state = "heat"
    st.attributes = {"hvac_modes": ["off", "heat", "cool"]}
    hass.states.get.return_value = st
    return hass


def _settle(outdoor: float, current: float, previous: str, cycles: int = 4) -> list[str]:
    """Feed the engine its own output repeatedly with unchanged inputs."""
    hass = _hass()
    seen = []
    for _ in range(cycles):
        plan = evaluate_native_heat_sources(ROOM, MODE_HEATING, 0.5, current, 21.0, outdoor, previous, hass)
        previous = plan.active_sources
        seen.append(previous)
    return seen


@pytest.mark.parametrize(
    ("outdoor", "previous", "expected"),
    [
        (2.3, "boiler", "boiler"),  # inside cold + h: boiler is held
        (7.7, "heat_pump", "heat_pump"),  # inside mild - h: heat pump is held
    ],
)
def test_outdoor_hysteresis_holds_current_source_with_large_gap(outdoor, previous, expected):
    """A large deficit near a threshold must not flip-flop source <-> hybrid."""
    assert _settle(outdoor, 18.0, previous) == [expected] * 4


def test_outdoor_thresholds_entered_without_hysteresis():
    assert _settle(2.0, 20.9, "heat_pump", cycles=1) == ["boiler"]
    assert _settle(8.0, 20.9, "boiler", cycles=1) == ["heat_pump"]


def test_large_gap_enters_hybrid_in_middle_band():
    assert _settle(5.0, 19.0, "heat_pump", cycles=1) == ["hybrid"]


@pytest.mark.parametrize(("outdoor", "expected"), [(5.0, "heat_pump"), (7.8, "heat_pump")])
def test_hybrid_exits_when_gap_shrinks(outdoor, expected):
    """Hybrid must not keep both sources on until the setpoint (A3)."""
    assert _settle(outdoor, 20.5, "hybrid", cycles=1) == [expected]


def test_hybrid_held_inside_gap_hysteresis():
    # gap 1.2 >= 1.5 - 0.5 → hybrid keeps running
    assert _settle(5.0, 19.8, "hybrid", cycles=1) == ["hybrid"]


# ---------------------------------------------------------------------------
# Coordinator: source dwell
# ---------------------------------------------------------------------------

NATIVE_ROOM = {**ROOM_WITH_TRV_AND_AC, "native_heat_source": True, "heat_source_min_dwell_minutes": 10}


async def _run(coordinator, hass, real_store, previous, changed_at, **states):
    await _setup_store(real_store, NATIVE_ROOM)
    coordinator._heat_source_states["living_room"] = previous
    coordinator._heat_source_changed_at["living_room"] = changed_at
    hass.states.get = MagicMock(side_effect=_make_hass_states(**states))
    await coordinator._async_update_data()
    return coordinator._heat_source_states.get("living_room")


class TestNativeDwell:
    @pytest.mark.asyncio
    async def test_dwell_holds_previous_source(self, coordinator, real_store, hass):
        assert await _run(coordinator, hass, real_store, "heat_pump", time.monotonic(), outdoor_temp="0.0") == (
            "heat_pump"
        )

    @pytest.mark.asyncio
    async def test_switch_after_dwell_elapsed(self, coordinator, real_store, hass):
        assert (
            await _run(coordinator, hass, real_store, "heat_pump", time.monotonic() - 3600, outdoor_temp="0.0")
            == "boiler"
        )

    @pytest.mark.asyncio
    async def test_lost_heat_pump_switches_immediately(self, coordinator, real_store, hass):
        state = await _run(
            coordinator,
            hass,
            real_store,
            "heat_pump",
            time.monotonic(),
            outdoor_temp="12.0",
            extra={"climate.ac_living": ("unavailable", {})},
        )
        assert state == "boiler"

    @pytest.mark.asyncio
    async def test_budget_denied_switches_to_boiler_during_dwell(self, coordinator, real_store, hass):
        coordinator._power_budget_manager.request_heat_pump = MagicMock(return_value=False)
        state = await _run(coordinator, hass, real_store, "heat_pump", time.monotonic(), outdoor_temp="12.0")
        assert state == "boiler"

    @pytest.mark.asyncio
    async def test_dwell_restoring_stopped_heat_pump_respects_denied_budget(self, coordinator, real_store, hass):
        """CR-02: cold outdoor plans boiler (no budget request); the dwell must not
        then restart an externally stopped AC without budget admission."""
        coordinator._power_budget_manager.request_heat_pump = MagicMock(return_value=False)
        state = await _run(
            coordinator,
            hass,
            real_store,
            "heat_pump",
            time.monotonic(),
            outdoor_temp="0.0",
            extra={"climate.ac_living": ("off", {"hvac_modes": ["off", "heat", "cool", "heat_cool"]})},
        )
        assert state == "boiler"
        coordinator._power_budget_manager.request_heat_pump.assert_called()
        ac_starts = [
            c
            for c in hass.services.async_call.call_args_list
            if c.args[2].get("entity_id") == "climate.ac_living" and c.args[2].get("hvac_mode") not in (None, "off")
        ]
        assert ac_starts == []

    @pytest.mark.parametrize(("ac_state", "expected"), [("off", "boiler"), ("heat_cool", "heat_pump")])
    @pytest.mark.asyncio
    async def test_dwell_budget_uses_physical_ac_state_with_real_manager(
        self, coordinator, real_store, hass, ac_state, expected
    ):
        """IR2-001: routing history alone must not pre-admit a stopped AC;
        a physically running AC stays admitted."""
        await real_store.async_load()
        with patch(
            "custom_components.roommind.managers.power_budget_manager.read_sensor_value",
            return_value=100,
        ):
            await real_store.async_save_settings(
                {
                    **DEFAULT_SETTINGS,
                    "power_budget_enabled": True,
                    "power_sensor": "sensor.house_power",
                    "power_sensor_mode": "available",
                }
            )
            await real_store.async_save_room("living_room", {**NATIVE_ROOM, "heat_pump_power_watts": 2000})
            coordinator._heat_source_states["living_room"] = "heat_pump"
            coordinator._heat_source_changed_at["living_room"] = time.monotonic()
            hass.states.get = MagicMock(
                side_effect=_make_hass_states(
                    outdoor_temp="0.0",
                    extra={"climate.ac_living": (ac_state, {"hvac_modes": ["off", "heat", "cool", "heat_cool"]})},
                )
            )
            await coordinator._async_update_data()
        assert coordinator._heat_source_states.get("living_room") == expected
        if expected == "boiler":
            ac_starts = [
                c
                for c in hass.services.async_call.call_args_list
                if c.args[2].get("entity_id") == "climate.ac_living" and c.args[2].get("hvac_mode") not in (None, "off")
            ]
            assert ac_starts == []
