from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"anchor not found in {path}: {old[:160]!r}")
    p.write_text(text.replace(old, new, 1))


# Persisted auxiliary intent must never power on an AC. Only an explicit
# climate.roommind_* command is allowed to activate fan_only/dry. The automatic
# loop merely preserves/reapplies options while the physical AC is already in
# that auxiliary mode.
replace_once(
    "custom_components/roommind/managers/room_climate.py",
    '''    if mode in ("dry", "fan_only"):\n        # Do not reassert an auxiliary mode that the physical device already\n        # reports.  This is especially important during HA startup, when the\n        # first coordinator refresh runs before RoomMind entities are created.\n        state = hass.states.get(entity_id)\n        if state is None or state.state != mode:\n            await hass.services.async_call(\n                "climate",\n                "set_hvac_mode",\n                {"entity_id": entity_id, "hvac_mode": mode},\n                blocking=True,\n                context=make_roommind_context(),\n            )\n''',
    '''    if mode in ("dry", "fan_only"):\n        # Persisted RoomMind state is not an activation request. Auxiliary\n        # modes are activated only by an explicit climate.roommind_* command.\n        # The coordinator may preserve/configure them only while the physical\n        # AC already reports the same mode. This prevents HA startup or a\n        # periodic refresh from powering on an AC that the user left off.\n        state = hass.states.get(entity_id)\n        if state is None or state.state != mode:\n            return\n''',
)

# During ordinary thermal idle, a physical fan_only state is treated as manual
# user intent and must not be shut down. Window-open behavior still follows the
# room toggle. Explicit force_off remains authoritative.
replace_once(
    "custom_components/roommind/control/mpc_controller.py",
    '''                await async_idle_device(\n                    self.hass,\n                    eid,\n                    self._devices,\n                    area_id=self._area_id,\n                    targets=targets,\n                    force_off=force_off,\n                    preserve_fan_only=window_open and not force_off,\n                )\n''',
    '''                preserve_physical_fan_only = (\n                    not force_off\n                    and (not window_open or keep_fan_on_window_open)\n                )\n                await async_idle_device(\n                    self.hass,\n                    eid,\n                    self._devices,\n                    area_id=self._area_id,\n                    targets=targets,\n                    force_off=force_off,\n                    preserve_fan_only=preserve_physical_fan_only,\n                )\n''',
)

# Update the startup regression: persisted fan_only + physical OFF must produce
# no HVAC mode command at all.
replace_once(
    "tests/coordinator/test_window_pause.py",
    '''    async def test_persisted_fan_only_does_not_cycle_off_on_startup(self, hass, mock_config_entry):\n        """Persisted fan_only intent must not send OFF before FAN_ONLY on first refresh."""\n''',
    '''    async def test_persisted_fan_only_does_not_power_on_ac_at_startup(self, hass, mock_config_entry):\n        """Persisted fan_only intent must never power on an AC that is physically off."""\n''',
)
replace_once(
    "tests/coordinator/test_window_pause.py",
    '''        assert call(\n            "climate",\n            "set_hvac_mode",\n            {"entity_id": ac_entity, "hvac_mode": "fan_only"},\n            blocking=True,\n            context=ANY,\n        ) in calls\n\n    @pytest.mark.asyncio\n    async def test_persisted_fan_only_already_active_is_not_reasserted''',
    '''        assert call(\n            "climate",\n            "set_hvac_mode",\n            {"entity_id": ac_entity, "hvac_mode": "fan_only"},\n            blocking=True,\n            context=ANY,\n        ) not in calls\n\n    @pytest.mark.asyncio\n    async def test_persisted_fan_only_already_active_is_not_reasserted''',
)

# Add a regression for a physical fan_only state reached outside RoomMind while
# the room is simply thermally idle: RoomMind must not switch it off.
p = Path("tests/coordinator/test_window_pause.py")
text = p.read_text()
marker = "\n    @pytest.mark.asyncio\n    async def test_window_closed_normal_operation"
if marker not in text:
    raise SystemExit("test insertion marker not found")
block = r'''
    @pytest.mark.asyncio
    async def test_physical_fan_only_is_preserved_during_normal_idle(self, hass, mock_config_entry):
        """Thermal idle must not turn off a physical fan_only state that reflects manual user intent."""
        ac_entity = "climate.living_room_ac"
        room = {
            **SAMPLE_ROOM,
            "thermostats": [],
            "acs": [ac_entity],
            "devices": [{"entity_id": ac_entity, "type": "ac", "role": "auto", "heating_system_type": ""}],
            "room_hvac_mode": "heat_cool",
            "logical_heat_target": 20.0,
            "logical_cool_target": 26.0,
            "window_sensors": [],
        }
        store = _make_store_mock({"living_room_abc12345": room})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                room_temp=23.0,
                extra={
                    ac_entity: (
                        "fan_only",
                        {
                            "hvac_modes": ["off", "cool", "fan_only"],
                            "hvac_action": "fan",
                            "current_temperature": 23.0,
                            "min_temp": 16.0,
                            "max_temp": 30.0,
                        },
                    )
                },
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        calls = hass.services.async_call.call_args_list
        assert call(
            "climate",
            "set_hvac_mode",
            {"entity_id": ac_entity, "hvac_mode": "off"},
            blocking=True,
            context=ANY,
        ) not in calls

'''
p.write_text(text.replace(marker, block + marker, 1))
