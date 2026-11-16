"""Coordinator side of the learned radiator afterglow (#493/#495, learning only)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from custom_components.roommind.const import MODE_HEATING, MODE_IDLE
from custom_components.roommind.control.mpc_controller import MPCController
from custom_components.roommind.managers.boiler_manager import BoilerManager

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

TRV = "climate.living_room"
AC = "climate.living_room_ac"
BYPASS = "climate.hall_bypass"
COORD = "custom_components.roommind.coordinator"


def _st(state, **attrs):
    return SimpleNamespace(state=state, attributes=attrs)


def _cmd(eid, *, active=True, device_type="trv", pf=0.5):
    return SimpleNamespace(entity_id=eid, active=active, device_type=device_type, power_fraction=pf)


def _setup(hass, mock_config_entry, *, devices, states, settings=None, system="radiator"):
    room = {**SAMPLE_ROOM, "heating_system_type": system, "devices": devices}
    settings = settings or {}
    store = _make_store_mock(rooms={room["area_id"]: room}, settings=settings)
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()
    hass.states.get = MagicMock(side_effect=states.get)
    return _create_coordinator(hass, mock_config_entry), room, settings


def _trv(eid=TRV):
    return {"entity_id": eid, "type": "trv", "role": "auto", "heating_system_type": "radiator"}


def _ac():
    return {"entity_id": AC, "type": "ac", "role": "auto", "heating_system_type": ""}


def _step(coordinator, room, settings, **overrides):
    kwargs = dict(
        area_id=room["area_id"],
        room=room,
        settings=settings,
        mode=MODE_HEATING,
        power_fraction=0.6,
        current_temp_raw=20.0,
        window_open=False,
        raw_open=False,
        shading_factor=1.0,
        q_occupancy=0.0,
        has_external_sensor=True,
        heat_source_plan=None,
        climate_active=True,
        boiler_wait=False,
        compressor_forced_on=False,
    )
    kwargs.update(overrides)
    with patch.object(coordinator._residual_learner, "step", return_value=None) as step:
        coordinator._step_residual_learner(**kwargs)
    return step.call_args.kwargs if step.called else None


# ---------------------------------------------------------------------------
# AC gate: only an AC that heats disturbs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ac_state", "disturbed"),
    [
        (_st("off"), False),  # heating-capable AC, off, no heat-source plan
        (_st("heat", hvac_action="idle"), False),  # left in heat mode, not firing
        (_st("heat", hvac_action="heating"), True),
        (_st("heat"), True),  # no hvac_action (Midea): its mode decides
        (_st("heat_cool"), True),
    ],
)
def test_ac_disturbs_only_while_it_heats(hass, mock_config_entry, ac_state, disturbed):
    coordinator, room, settings = _setup(
        hass,
        mock_config_entry,
        devices=[_trv(), _ac()],
        states={TRV: _st("heat", hvac_action="heating"), AC: ac_state},
    )
    kwargs = _step(coordinator, room, settings)
    assert kwargs["disturbed"] is disturbed
    assert kwargs["delivered_power"] == pytest.approx(1.0)


def test_plan_active_ac_without_action_disturbs(hass, mock_config_entry):
    coordinator, room, settings = _setup(
        hass, mock_config_entry, devices=[_trv(), _ac()], states={TRV: _st("heat"), AC: _st("off")}
    )
    plan = SimpleNamespace(commands=[_cmd(TRV), _cmd(AC, device_type="ac")])
    assert _step(coordinator, room, settings, heat_source_plan=plan)["disturbed"] is True


def test_compressor_hold_disturbs(hass, mock_config_entry):
    coordinator, room, settings = _setup(hass, mock_config_entry, devices=[_trv()], states={TRV: _st("heat")})
    assert _step(coordinator, room, settings, compressor_forced_on=True)["disturbed"] is True


# ---------------------------------------------------------------------------
# Delivered power: the room's radiators only
# ---------------------------------------------------------------------------


def test_mixed_plan_counts_only_the_radiator(hass, mock_config_entry):
    coordinator, room, settings = _setup(
        hass,
        mock_config_entry,
        devices=[_trv(), _ac()],
        states={TRV: _st("heat", hvac_action="idle"), AC: _st("heat", hvac_action="heating")},
    )
    plan = SimpleNamespace(commands=[_cmd(TRV), _cmd(AC, device_type="ac")])
    assert _step(coordinator, room, settings, heat_source_plan=plan)["delivered_power"] == 0.0
    # The EKF label is unchanged: without the filter the AC still counts
    assert coordinator._delivered_training_power(room, MODE_HEATING, 0.6, plan) == pytest.approx(0.5)


def test_ac_only_plan_is_no_radiator_run(hass, mock_config_entry):
    coordinator, room, settings = _setup(
        hass,
        mock_config_entry,
        devices=[_trv(), _ac()],
        states={TRV: _st("heat", hvac_action="heating"), AC: _st("heat", hvac_action="heating")},
    )
    plan = SimpleNamespace(commands=[_cmd(TRV, active=False), _cmd(AC, device_type="ac")])
    assert _step(coordinator, room, settings, heat_source_plan=plan)["delivered_power"] is None


def test_unavailable_radiator_is_no_run_not_the_commanded_power(hass, mock_config_entry):
    coordinator, room, settings = _setup(hass, mock_config_entry, devices=[_trv()], states={TRV: _st("unavailable")})
    plan = SimpleNamespace(commands=[_cmd(TRV)])
    assert _step(coordinator, room, settings)["delivered_power"] is None
    assert _step(coordinator, room, settings, heat_source_plan=plan)["delivered_power"] is None


def test_pinned_valve_delivers_its_held_opening(hass, mock_config_entry):
    coordinator, room, settings = _setup(
        hass, mock_config_entry, devices=[_trv()], states={TRV: _st("heat", hvac_action="idle")}
    )
    with (
        patch(f"{COORD}.get_valve_entities", return_value={TRV: MagicMock()}),
        patch(f"{COORD}.held_opening", return_value=0.4),
    ):
        kwargs = _step(coordinator, room, settings)
    assert kwargs["delivered_power"] == pytest.approx(0.4)
    assert kwargs["disturbed"] is False


def test_valve_held_open_while_idle_disturbs(hass, mock_config_entry):
    coordinator, room, settings = _setup(hass, mock_config_entry, devices=[_trv()], states={TRV: _st("off")})
    with (
        patch(f"{COORD}.get_valve_entities", return_value={TRV: MagicMock()}),
        patch(f"{COORD}.held_opening", return_value=0.3),
    ):
        kwargs = _step(coordinator, room, settings, mode=MODE_IDLE)
    assert kwargs["disturbed"] is True
    assert kwargs["delivered_power"] is None


# ---------------------------------------------------------------------------
# Boiler: waiting and bypass radiators
# ---------------------------------------------------------------------------


def test_boiler_wait_disturbs_and_delivers_nothing(hass, mock_config_entry):
    coordinator, room, settings = _setup(
        hass, mock_config_entry, devices=[_trv()], states={TRV: _st("heat", hvac_action="heating")}
    )
    kwargs = _step(coordinator, room, settings, boiler_wait=True)
    assert kwargs["disturbed"] is True
    assert kwargs["delivered_power"] is None


@pytest.mark.parametrize("boiler_heats", [True, False])
def test_bypass_radiator_disturbs_while_the_boiler_heats(hass, mock_config_entry, boiler_heats):
    coordinator, room, settings = _setup(
        hass,
        mock_config_entry,
        devices=[_trv(), _trv(BYPASS)],
        states={TRV: _st("off"), BYPASS: _st("heat")},
        settings={"boiler_entity": "switch.boiler", "hydraulic_bypass_entities": [BYPASS]},
    )
    with patch.object(BoilerManager, "heat_available", new_callable=PropertyMock, return_value=boiler_heats):
        kwargs = _step(coordinator, room, settings, mode=MODE_IDLE)
    assert kwargs["disturbed"] is boiler_heats


def test_disturbances_of_the_room(hass, mock_config_entry):
    coordinator, room, settings = _setup(hass, mock_config_entry, devices=[_trv()], states={TRV: _st("heat")})
    for overrides in (
        {"window_open": True},
        {"raw_open": True},
        {"climate_active": False},
        {"has_external_sensor": False},
    ):
        assert _step(coordinator, room, settings, **overrides)["disturbed"] is True, overrides
    settings["learning_disabled_rooms"] = [room["area_id"]]
    assert _step(coordinator, room, settings)["disturbed"] is True


def test_non_radiator_room_is_not_fed(hass, mock_config_entry):
    coordinator, room, settings = _setup(
        hass, mock_config_entry, devices=[_trv()], states={TRV: _st("heat")}, system="underfloor"
    )
    assert _step(coordinator, room, settings) is None


# ---------------------------------------------------------------------------
# Full cycle: samples are folded in, control is unchanged
# ---------------------------------------------------------------------------


def _cycle_setup(hass, mock_config_entry):
    room = {**SAMPLE_ROOM, "heating_system_type": "radiator", "devices": [_trv()]}
    store = _make_store_mock(rooms={room["area_id"]: room}, settings={"climate_control_active": True})
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()
    hass.states.get = make_mock_states_get(
        temp="18.0", schedule_state="on", schedule_attrs={"current_event": True, "friendly_name": "Heat"}
    )
    return _create_coordinator(hass, mock_config_entry), room["area_id"]


@pytest.mark.asyncio
async def test_sample_is_folded_into_the_learned_scale(hass, mock_config_entry):
    coordinator, aid = _cycle_setup(hass, mock_config_entry)
    with patch.object(coordinator._residual_learner, "step", return_value=2.5) as step:
        await coordinator._async_update_data()
    assert step.call_args.kwargs["system_type"] == "radiator"
    assert coordinator._model_manager.get_residual_scale(aid) == pytest.approx(1.5)  # (1 + 1 + 2.5) / 3
    assert coordinator._model_manager.get_residual_samples(aid) == 1


async def _run_cycle(hass, mock_config_entry, *, learned: bool):
    coordinator, aid = _cycle_setup(hass, mock_config_entry)
    # A recent stop: the profile's residual heat is non-zero in both runs
    now = 1_800_000_000.0
    coordinator._residual_tracker._on_since[aid] = now - 3720
    coordinator._residual_tracker._off_since[aid] = now - 120
    coordinator._residual_tracker._off_power[aid] = 1.0
    if learned:
        mgr = coordinator._model_manager
        for _ in range(10):
            mgr.update_residual_scale(aid, 5.0)
        mgr.update_residual_tau(aid, 40.0, 10.0)
    training = MagicMock()
    with (
        patch("time.time", return_value=now),
        patch(f"{COORD}.MPCController", wraps=MPCController) as ctrl,
        patch.object(coordinator._ekf_training, "process", training),
        patch.object(coordinator._residual_learner, "step", return_value=3.0 if learned else None),
    ):
        result = await coordinator._async_update_data()
    return (
        [c.args for c in hass.services.async_call.call_args_list],
        ctrl.call_args.kwargs["q_residual"],
        training.call_args.kwargs["q_residual"],
        result["rooms"][aid]["mode"],
    )


@pytest.mark.asyncio
async def test_learned_afterglow_does_not_change_control(hass, mock_config_entry):
    """Learning only: the same cycle sends the same commands with a learned scale and decay time."""
    plain = await _run_cycle(hass, mock_config_entry, learned=False)
    learned = await _run_cycle(hass, mock_config_entry, learned=True)
    assert plain[1] > 0.0  # the controller does get the profile's residual heat
    assert learned == plain


@pytest.mark.asyncio
async def test_thermal_reset_drops_the_learner_state(hass, mock_config_entry):
    coordinator, aid = _cycle_setup(hass, mock_config_entry)
    coordinator._model_manager.update_residual_scale(aid, 4.0)
    coordinator._residual_learner._obs[aid] = MagicMock()
    coordinator.reset_thermal_room(aid)
    assert aid not in coordinator._residual_learner._obs
    assert coordinator._model_manager.get_residual_scale(aid) == 1.0
    coordinator._residual_learner._runs[aid] = MagicMock()
    coordinator.reset_thermal_all()
    assert coordinator._residual_learner._runs == {}
