from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.climate import RoomMindClimate, _create_room_climates
from custom_components.roommind.managers.boiler_manager import BoilerManager, BoilerState
from custom_components.roommind.managers.valve_manager import ValveManager


def test_only_canonical_climate_is_created():
    coordinator = MagicMock()
    climates = _create_room_climates(coordinator, "studio")
    assert len(climates) == 1
    assert isinstance(climates[0], RoomMindClimate)


@pytest.mark.asyncio
async def test_boiler_master_off_does_not_abandon_running_boiler():
    hass = MagicMock()
    hass.states.get.return_value = SimpleNamespace(state="heat")
    hass.services.async_call = AsyncMock()
    manager = BoilerManager(hass)
    manager.state = BoilerState.ON
    manager.path_safe = True
    manager._set_bypass = AsyncMock(return_value=True)
    manager._set_boiler = AsyncMock(return_value=True)

    await manager.async_reconcile(
        {
            "climate_control_active": False,
            "boiler_entity": "climate.boiler",
            "boiler_shutdown_delay_seconds": 60,
        },
        {"studio"},
    )

    manager._set_boiler.assert_awaited_with(
        {
            "climate_control_active": False,
            "boiler_entity": "climate.boiler",
            "boiler_shutdown_delay_seconds": 60,
        },
        False,
    )
    assert manager.state == BoilerState.POSTSTOP
    assert manager.demand_rooms == set()


@pytest.mark.asyncio
async def test_valve_cycle_is_closed_when_master_is_disabled():
    hass = MagicMock()
    store = MagicMock()
    store.get_settings.return_value = {"climate_control_active": False}
    hass.data = {"roommind": {"store": store}}
    manager = ValveManager(hass)
    manager._cycling = {"climate.trv": 1.0}
    manager._async_close_valve = AsyncMock()

    await manager.async_finish_cycles({"climate.trv": []})

    manager._async_close_valve.assert_awaited_once()
    assert manager._cycling == {}
    assert manager.actuation_dirty is True
