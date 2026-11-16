"""Coordinator gate of afterglow control (room switch `residual_control_enabled`, off by default)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import MODE_HEATING, MODE_IDLE
from custom_components.roommind.control.mpc_controller import MPCController

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

COORD = "custom_components.roommind.coordinator"
TRV = "climate.living_room"


def _room(enabled: bool, system: str = "radiator") -> dict:
    return {
        **SAMPLE_ROOM,
        "heating_system_type": system,
        "residual_control_enabled": enabled,
        "devices": [{"entity_id": TRV, "type": "trv", "role": "auto", "heating_system_type": system}],
    }


def _coord(hass, mock_config_entry, room):
    store = _make_store_mock(rooms={room["area_id"]: room}, settings={"climate_control_active": True})
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()
    hass.states.get = make_mock_states_get(
        temp="18.0", schedule_state="on", schedule_attrs={"current_event": True, "friendly_name": "Heat"}
    )
    coordinator = _create_coordinator(hass, mock_config_entry)
    return coordinator, room["area_id"]


def _learned(coordinator, aid):
    coordinator._model_manager.update_residual_scale(aid, 4.0)
    coordinator._model_manager.update_residual_tau(aid, 30.0, 10.0)


def _stopped(coordinator, aid, now):
    tracker = coordinator._residual_tracker
    tracker._on_since[aid] = now - 3720
    tracker._off_since[aid] = now - 120
    tracker._off_power[aid] = 1.0


@pytest.mark.parametrize(
    ("enabled", "system", "samples", "expected"),
    [
        (False, "radiator", True, False),
        (True, "radiator", False, False),
        (True, "", True, False),
        (True, "radiator", True, True),
    ],
)
def test_afterglow_inputs_only_with_switch_radiator_and_samples(
    hass, mock_config_entry, enabled, system, samples, expected
):
    room = _room(enabled, system)
    coordinator, aid = _coord(hass, mock_config_entry, room)
    if samples:
        _learned(coordinator, aid)
    now = time.time()
    _stopped(coordinator, aid, now)
    plain = coordinator._residual_tracker.get_q_residual(aid, system, MODE_IDLE)
    inputs, q = coordinator._afterglow_inputs(aid, room, system, True, 20.0, plain)
    assert (inputs is not None) is expected
    if expected:
        assert inputs["scale"] == coordinator._model_manager.get_residual_scale(aid)
        assert inputs["tau"] == coordinator._model_manager.get_residual_tau(aid)
        assert q != plain  # the controller gets the learned afterglow
    else:
        assert q == plain  # identical inputs with the switch off


def test_managed_mode_room_gets_no_afterglow_control(hass, mock_config_entry):
    room = _room(True)
    coordinator, aid = _coord(hass, mock_config_entry, room)
    _learned(coordinator, aid)
    assert coordinator._afterglow_inputs(aid, room, "radiator", False, 20.0, 0.1) == (None, 0.1)


def test_heat_run_is_the_learners_run_at_delivered_power(hass, mock_config_entry):
    """With a pinned valve the run's power is the held opening, not 1.0."""
    room = _room(True)
    coordinator, aid = _coord(hass, mock_config_entry, room)
    _learned(coordinator, aid)
    coordinator._previous_modes[aid] = MODE_HEATING
    with patch.object(coordinator._residual_learner, "run_state", return_value=(25.0, 0.4)):
        inputs, _ = coordinator._afterglow_inputs(aid, room, "radiator", True, 20.0, 0.0)
    assert inputs["heat_run"] == (25.0, 0.4)


async def _run_cycle(hass, mock_config_entry, enabled):
    room = _room(enabled)
    coordinator, aid = _coord(hass, mock_config_entry, room)
    _learned(coordinator, aid)
    now = 1_800_000_000.0
    _stopped(coordinator, aid, now)
    training = MagicMock()
    with (
        patch("time.time", return_value=now),
        patch(f"{COORD}.MPCController", wraps=MPCController) as ctrl,
        patch.object(coordinator._ekf_training, "process", training),
    ):
        await coordinator._async_update_data()
    return ctrl.call_args.kwargs, training.call_args.kwargs["q_residual"]


@pytest.mark.asyncio
async def test_switch_off_sends_todays_controller_inputs(hass, mock_config_entry):
    off_kwargs, off_ekf = await _run_cycle(hass, mock_config_entry, False)
    on_kwargs, on_ekf = await _run_cycle(hass, mock_config_entry, True)
    assert off_kwargs["afterglow"] is None
    assert on_kwargs["afterglow"] is not None
    assert on_kwargs["q_residual"] > off_kwargs["q_residual"]  # learned scale 4 > profile
    # The EKF keeps the profile's residual heat either way (no feedback on the learned scale)
    assert on_ekf == off_ekf


@pytest.mark.asyncio
async def test_sensor_lag_follows_the_final_mode(hass, mock_config_entry):
    """C2-03: the stop is recorded from the mode the cycle ended with, not the controller's choice."""
    room = _room(True)
    coordinator, aid = _coord(hass, mock_config_entry, room)
    _learned(coordinator, aid)  # afterglow control needs a learned room
    plan = MagicMock(temperatures=[20.2, 20.4], dt_minutes=5.0)
    common = dict(
        area_id=aid,
        room=room,
        settings={},
        current_temp_raw=20.2,
        power_fraction=0.0,
        window_open=False,
        raw_open=False,
        q_residual=0.0,
        shading_factor=1.0,
        q_occupancy=0.0,
        has_external_sensor=True,
        heat_source_plan=None,
        climate_active=True,
        afterglow_plan=plan,
    )
    coordinator._previous_modes[aid] = MODE_HEATING
    await coordinator._observe_and_train(mode=MODE_IDLE, **common)  # e.g. a window turned the heating off
    assert aid in coordinator._afterglow_reading._stops
    await coordinator._observe_and_train(mode=MODE_HEATING, **common)
    assert aid not in coordinator._afterglow_reading._stops
