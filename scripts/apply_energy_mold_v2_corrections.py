from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str, *, count: int = 1, required: bool = True) -> None:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    if old not in text:
        if required:
            raise SystemExit(f"anchor not found in {path}: {old[:140]!r}")
        return
    p.write_text(text.replace(old, new, count), encoding="utf-8")


# ---------------------------------------------------------------------------
# Mold prevention: fix notification rendering and make temporary takeover
# restore an auxiliary mode exactly after risk clears.
# ---------------------------------------------------------------------------
replace(
    "custom_components/roommind/managers/mold_manager.py",
    '''                        await async_send_mold_notification(\n                            self.hass,\n                            area_id,\n                            area_name,\n                            prev_targets,\n                            message=(\n                                f"Mold prevention active in {area_name}: "(\n                                    f"AC dehumidification enabled ({result.prevention_strategy})"\n                                    if result.prevention_strategy in ("dry", "cool")\n                                    else f"temperature raised by "\n                                    f"{celsius_delta_to_ha_fn(result.prevention_delta):.0f}{ha_temp_unit_str_fn()}"\n                                )\n                            ),\n''',
    '''                        strategy_message = (\n                            f"AC dehumidification enabled ({result.prevention_strategy})"\n                            if result.prevention_strategy in ("dry", "cool")\n                            else "temperature raised by "\n                            f"{celsius_delta_to_ha_fn(result.prevention_delta):.0f}{ha_temp_unit_str_fn()}"\n                        )\n                        await async_send_mold_notification(\n                            self.hass,\n                            area_id,\n                            area_name,\n                            prev_targets,\n                            message=f"Mold prevention active in {area_name}: {strategy_message}",\n''',
)

# Coordinator remembers only whether prevention owned the actuator in the prior
# tick. room_hvac_mode remains untouched, so heat/cool/auto restore naturally;
# fan_only/dry need one explicit re-activation because persisted auxiliary modes
# are intentionally preservation-only during normal coordinator refreshes.
replace(
    "custom_components/roommind/coordinator.py",
    '        self._energy_manager = EnergyManager(hass)\n',
    '        self._energy_manager = EnergyManager(hass)\n        self._mold_active_strategies: dict[str, str] = {}\n',
)
replace(
    "custom_components/roommind/coordinator.py",
    '''        mold_prevention_effective = bool(\n            mold_prevention_active_room and automation_enabled and mold_prevention_strategy\n        )\n        effective_requested_hvac_mode = requested_hvac_mode\n''',
    '''        mold_prevention_effective = bool(\n            mold_prevention_active_room and automation_enabled and mold_prevention_strategy\n        )\n        previous_mold_strategy = self._mold_active_strategies.get(area_id)\n        mold_restore_mode: str | None = None\n        if mold_prevention_effective and mold_prevention_strategy is not None:\n            self._mold_active_strategies[area_id] = mold_prevention_strategy\n        elif previous_mold_strategy is not None:\n            self._mold_active_strategies.pop(area_id, None)\n            if requested_hvac_mode in ("fan_only", "dry"):\n                mold_restore_mode = requested_hvac_mode\n\n        effective_requested_hvac_mode = requested_hvac_mode\n''',
)

# Dry prevention must pass the same hard electrical/compressor safety gates as
# the normal autonomous cooling path. Track which ACs were actually activated
# so compressor bookkeeping stays truthful even though thermal mode is IDLE.
replace(
    "custom_components/roommind/coordinator.py",
    '''        else:\n            try:\n                await controller.async_apply(\n''',
    '''        else:\n            mold_aux_activated: set[str] = set()\n            try:\n                await controller.async_apply(\n''',
)
replace(
    "custom_components/roommind/coordinator.py",
    '''                if mold_prevention_effective and mold_prevention_strategy == "dry" and not window_open:\n                    # Unlike a persisted user DRY mode, prevention is an explicit\n                    # automatic activation request. TRVs have just been idled by\n                    # the controller; activate every capable AC in DRY.\n                    for ac_eid in get_ac_eids(room.get("devices", [])):\n                        ac_state = self.hass.states.get(ac_eid)\n                        if ac_state is None or "dry" not in (ac_state.attributes.get("hvac_modes") or []):\n                            continue\n                        await self.hass.services.async_call(\n                            "climate",\n                            "set_hvac_mode",\n                            {"entity_id": ac_eid, "hvac_mode": "dry"},\n                            blocking=True,\n                            context=make_roommind_context(),\n                        )\n                elif requested_hvac_mode in ("dry", "fan_only"):\n''',
    '''                if mold_prevention_effective and mold_prevention_strategy == "dry" and not window_open:\n                    # Unlike a persisted user DRY mode, prevention is an explicit\n                    # automatic activation request. Respect compressor min-off and\n                    # the cycle-scoped electrical budget before starting anything.\n                    dry_acs: list[str] = []\n                    already_running = False\n                    for ac_eid in get_ac_eids(room.get("devices", [])):\n                        ac_state = self.hass.states.get(ac_eid)\n                        if ac_state is None or "dry" not in (ac_state.attributes.get("hvac_modes") or []):\n                            continue\n                        is_running = ac_state.state not in ("off", "unknown", "unavailable", "fan_only")\n                        already_running = already_running or is_running\n                        if not is_running and not self._compressor_manager.check_can_activate(ac_eid):\n                            continue\n                        dry_acs.append(ac_eid)\n                    budget_ok = self._power_budget_manager.request_heat_pump(\n                        area_id,\n                        float(room.get("heat_pump_power_watts", 0) or 0),\n                        already_running,\n                    )\n                    if budget_ok:\n                        for ac_eid in dry_acs:\n                            await self.hass.services.async_call(\n                                "climate",\n                                "set_hvac_mode",\n                                {"entity_id": ac_eid, "hvac_mode": "dry"},\n                                blocking=True,\n                                context=make_roommind_context(),\n                            )\n                            mold_aux_activated.add(ac_eid)\n                elif mold_restore_mode is not None and not window_open:\n                    # Prevention ended: restore a previous auxiliary mode once.\n                    # The persisted canonical mode was never mutated.\n                    for ac_eid in get_ac_eids(room.get("devices", [])):\n                        ac_state = self.hass.states.get(ac_eid)\n                        if ac_state is None or mold_restore_mode not in (ac_state.attributes.get("hvac_modes") or []):\n                            continue\n                        if mold_restore_mode == "dry" and ac_state.state in ("off", "unknown", "unavailable", "fan_only"):\n                            if not self._compressor_manager.check_can_activate(ac_eid):\n                                continue\n                        await self.hass.services.async_call(\n                            "climate",\n                            "set_hvac_mode",\n                            {"entity_id": ac_eid, "hvac_mode": mold_restore_mode},\n                            blocking=True,\n                            context=make_roommind_context(),\n                        )\n                        if mold_restore_mode == "dry":\n                            mold_aux_activated.add(ac_eid)\n                elif requested_hvac_mode in ("dry", "fan_only"):\n''',
)
replace(
    "custom_components/roommind/coordinator.py",
    '''                elif mode != MODE_IDLE:\n                    self._compressor_manager.update_member(eid, True)\n                else:\n                    self._compressor_manager.update_member(eid, False)\n''',
    '''                elif eid in mold_aux_activated:\n                    self._compressor_manager.update_member(eid, True)\n                elif mode != MODE_IDLE:\n                    self._compressor_manager.update_member(eid, True)\n                else:\n                    self._compressor_manager.update_member(eid, False)\n''',
)
replace(
    "custom_components/roommind/coordinator.py",
    '        self._energy_manager.remove_room(area_id)\n        self._heat_source_states.pop(area_id, None)\n',
    '        self._energy_manager.remove_room(area_id)\n        self._mold_active_strategies.pop(area_id, None)\n        self._heat_source_states.pop(area_id, None)\n',
)

# ---------------------------------------------------------------------------
# Tests that intentionally changed in earlier accepted RoomMind refactors.
# Make them assert the current API rather than stale pre-refactor entity counts.
# ---------------------------------------------------------------------------
replace(
    "tests/test_sensor.py",
    '''from custom_components.roommind.sensor import (\n    RoomMindModeSensor,\n    RoomMindTargetTemperatureSensor,\n    _create_room_entities,\n    async_setup_entry,\n)\n''',
    '''from custom_components.roommind.sensor import (\n    RoomMindEnergyTodaySensor,\n    RoomMindModeSensor,\n    RoomMindPowerSensor,\n    RoomMindPredictedEnergySensor,\n    RoomMindPredictedPowerSensor,\n    RoomMindTargetTemperatureSensor,\n    _create_room_entities,\n    async_setup_entry,\n)\n''',
)
replace(
    "tests/test_sensor.py",
    '''    # 2 entities per room (target_temp + mode)\n    add_entities.assert_called_once()\n    entities = add_entities.call_args[0][0]\n    assert len(entities) == 2\n''',
    '''    add_entities.assert_called_once()\n    entities = add_entities.call_args[0][0]\n    room_entities = [e for e in entities if getattr(e, "_area_id", None) == "room_a"]\n    assert len(room_entities) == 8\n    assert any(isinstance(e, RoomMindPowerSensor) for e in room_entities)\n    assert any(isinstance(e, RoomMindEnergyTodaySensor) for e in room_entities)\n''',
)
replace(
    "tests/test_sensor.py",
    '    assert len(entities) == 4  # 2 per room\n',
    '    assert sum(getattr(e, "_area_id", None) in {"room_a", "room_b"} for e in entities) == 16\n',
)
replace(
    "tests/test_sensor.py",
    '''    assert len(entities) == 2\n    assert isinstance(entities[0], RoomMindTargetTemperatureSensor)\n    assert isinstance(entities[1], RoomMindModeSensor)\n''',
    '''    assert len(entities) == 8\n    assert isinstance(entities[0], RoomMindTargetTemperatureSensor)\n    assert isinstance(entities[1], RoomMindModeSensor)\n    assert any(isinstance(e, RoomMindPowerSensor) for e in entities)\n    assert any(isinstance(e, RoomMindEnergyTodaySensor) for e in entities)\n    assert any(isinstance(e, RoomMindPredictedPowerSensor) for e in entities)\n    assert any(isinstance(e, RoomMindPredictedEnergySensor) for e in entities)\n''',
)
# Global sensor entities mean setup is no longer a no-op with zero rooms.
replace(
    "tests/test_sensor.py",
    '''    assert coordinator.async_add_entities is add_entities\n    add_entities.assert_not_called()\n''',
    '''    assert coordinator.async_add_entities is add_entities\n    add_entities.assert_called_once()\n    assert all(getattr(e, "_area_id", None) is None for e in add_entities.call_args[0][0])\n''',
)

replace(
    "tests/test_binary_sensor.py",
    '''    # Only living_room has covers, so one entity created\n    async_add_entities.assert_called_once()\n    entities = async_add_entities.call_args[0][0]\n    assert len(entities) == 1\n    assert isinstance(entities[0], RoomMindCoverPausedSensor)\n''',
    '''    # One room cover sensor plus the two global boiler safety sensors.\n    async_add_entities.assert_called_once()\n    entities = async_add_entities.call_args[0][0]\n    room_entities = [e for e in entities if isinstance(e, RoomMindCoverPausedSensor)]\n    assert len(room_entities) == 1\n''',
)
replace(
    "tests/test_binary_sensor.py",
    '    async_add_entities.assert_not_called()\n',
    '    async_add_entities.assert_called_once()\n    assert len(async_add_entities.call_args[0][0]) == 2\n',
)

# Canonical + energy sensor ownership inventory; legacy override is intentionally orphaned.
replace(
    "tests/coordinator/test_entity_cleanup.py",
    '        mock_registry.async_remove.assert_not_called()\n\n    def test_cleanup_removes_deleted_rooms_and_obsolete_entity_types',
    '        assert {call.args[0] for call in mock_registry.async_remove.call_args_list} == {"climate.roommind_sala_override"}\n\n    def test_cleanup_removes_deleted_rooms_and_obsolete_entity_types',
    count=1,
)
replace(
    "tests/coordinator/test_entity_cleanup.py",
    '''            for suffix, domain in (\n                ("target_temp", "sensor"),\n                ("mode", "sensor"),\n                ("override", "climate"),\n                ("climate_control", "switch"),\n            ):\n''',
    '''            for suffix, domain in (\n                ("target_temp", "sensor"),\n                ("mode", "sensor"),\n                ("climate_control", "switch"),\n            ):\n''',
)

# Snapshot API gained heat-source visibility previously and mold strategy now.
for key in ('    "heat_source",\n', '    "heat_source_reason",\n', '    "mold_prevention_strategy",\n'):
    pass
replace(
    "tests/coordinator/test_process_room_snapshot.py",
    '    "mold_prevention_delta",\n    "shading_factor",\n',
    '    "mold_prevention_delta",\n    "mold_prevention_strategy",\n    "shading_factor",\n',
    count=2,
)
replace(
    "tests/coordinator/test_process_room_snapshot.py",
    '    "active_heat_sources",\n    "compressor_protection_active",\n',
    '    "active_heat_sources",\n    "heat_source",\n    "heat_source_reason",\n    "compressor_protection_active",\n',
    count=2,
)

replace(
    "tests/coordinator/test_update_cycle.py",
    '        assert data == {"rooms": {}}\n',
    '''        assert data["rooms"] == {}\n        assert {"available_power", "reserved_power", "boiler_demand", "boiler_active", "hydraulic_path_safe"} <= set(data)\n''',
)
replace(
    "tests/coordinator/test_update_cycle.py",
    '''        # async_add_entities should be called with 3 entities\n        mock_add_entities.assert_called_once()\n        entities = mock_add_entities.call_args[0][0]\n        assert len(entities) == 2\n''',
    '''        mock_add_entities.assert_called_once()\n        entities = mock_add_entities.call_args[0][0]\n        assert len(entities) == 8\n''',
)

# AC fallback target step is intentionally 1 C when the entity does not expose one.
replace(
    "tests/control/test_heat_source_plan.py",
    'assert temp_call.data["temperature"] == pytest.approx(27.8)',
    'assert temp_call.data["temperature"] == pytest.approx(28.0)',
    required=False,
)

# Valve protection obeys the global automation master: do not start new cycles
# while disabled. Existing active cycles are still closed by async_finish_cycles.
valve = ROOT / "tests/coordinator/test_valve_protection.py"
if valve.exists():
    text = valve.read_text(encoding="utf-8")
    text = text.replace(
        'async def test_valve_protection_runs_when_climate_control_disabled',
        'async def test_valve_protection_does_not_start_when_climate_control_disabled',
    )
    text = text.replace(
        'assert coordinator._valve_manager.is_entity_cycling("climate.trv") is True',
        'assert coordinator._valve_manager.is_entity_cycling("climate.trv") is False',
    )
    valve.write_text(text, encoding="utf-8")

print("energy + mold v2 corrections applied")
