"""Energy history bootstrap runs once per start, even when it fails (S3)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.coordinator.conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

POWER_ROOM = {
    **SAMPLE_ROOM,
    "devices": [
        {
            "entity_id": "climate.living_room",
            "type": "ac",
            "role": "auto",
            "heating_system_type": "",
            "power_sensor_entity_id": "sensor.ac_power",
        }
    ],
}


@pytest.mark.asyncio
async def test_failed_energy_bootstrap_is_not_retried_every_cycle(hass, mock_config_entry, caplog):
    store = _make_store_mock(rooms={"living_room_abc12345": POWER_ROOM})
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=make_mock_states_get())
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    history = MagicMock()
    history.read_detail.side_effect = OSError("broken csv")
    history.read_history.return_value = []
    coordinator._history_store = history
    # Room processing failing too means update_room never marks the room as bootstrapped.
    coordinator._async_process_room = AsyncMock(side_effect=RuntimeError("room failed"))

    for _ in range(3):
        await coordinator._async_update_data()

    assert history.read_detail.call_count == 1
    assert caplog.text.count("Energy history bootstrap failed") == 1
