"""The coordinator writes the model's training inputs with the history; commands do not change."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.const import HISTORY_WRITE_CYCLES
from custom_components.roommind.utils.history_store import MODEL_INPUT_FIELDS

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

AREA = "living_room_abc12345"


def _setup(hass, mock_config_entry, room=None, settings=None):
    store = _make_store_mock({AREA: room or SAMPLE_ROOM})
    if settings is not None:
        store.get_settings.return_value = settings
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=make_mock_states_get())
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    history = MagicMock()
    history.read_detail = MagicMock(return_value=[])
    coordinator._history_store = history
    return coordinator, history


def _commands(hass):
    return [
        (c.args, {k: v for k, v in c.kwargs.items() if k != "context"}) for c in hass.services.async_call.call_args_list
    ]


async def _written_rows(coordinator, history):
    for _ in range(HISTORY_WRITE_CYCLES):
        await coordinator._async_update_data()
    return [c.args[1] for c in history.record.call_args_list if c.args[0] == AREA]


@pytest.mark.asyncio
async def test_a_trained_interval_is_written_with_the_history(hass, mock_config_entry):
    coordinator, history = _setup(hass, mock_config_entry)
    rows = await _written_rows(coordinator, history)
    assert rows, "a history row was written"
    row = rows[-1]
    # every cycle of the interval trained heating with the window closed: means are written
    assert row["model_power"] > 0
    assert all(isinstance(row[k], float) for k in MODEL_INPUT_FIELDS)
    # the interval is reset after the write
    assert coordinator._model_inputs.take(AREA) == {}


@pytest.mark.asyncio
async def test_learning_disabled_writes_no_inputs(hass, mock_config_entry):
    coordinator, history = _setup(hass, mock_config_entry)
    for _ in range(HISTORY_WRITE_CYCLES - 1):
        await coordinator._async_update_data()
    coordinator._model_inputs.unusable(AREA)
    await coordinator._async_update_data()
    rows = [c.args[1] for c in history.record.call_args_list if c.args[0] == AREA]
    assert rows and not any(k in rows[-1] for k in MODEL_INPUT_FIELDS)


@pytest.mark.asyncio
async def test_device_commands_do_not_depend_on_the_recording(hass, mock_config_entry):
    """Same cycles with the recording made inert: identical service calls."""
    coordinator, history = _setup(hass, mock_config_entry)
    await _written_rows(coordinator, history)
    with_recording = _commands(hass)

    coordinator2, history2 = _setup(hass, mock_config_entry)
    inert = MagicMock()
    inert.take.return_value = {}
    coordinator2._model_inputs = inert
    await _written_rows(coordinator2, history2)
    without = _commands(hass)
    assert with_recording == without
