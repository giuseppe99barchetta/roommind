from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"anchor not found in {path}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1))


replace_once(
    "custom_components/roommind/control/mpc_controller.py",
    """        elif mode == MODE_IDLE:\n            for eid in thermostats + self.acs:\n""",
    """        elif mode == MODE_IDLE:\n            # Respect auxiliary-mode exclusions here as well.  fan_only/dry\n            # are thermally idle, but the AC must not receive an intermediate\n            # OFF before the auxiliary mode is applied.\n            for eid in [e for e in thermostats + self.acs if e not in _exclude]:\n""",
)

replace_once(
    "custom_components/roommind/managers/room_climate.py",
    """    if mode in (\"dry\", \"fan_only\"):\n        await hass.services.async_call(\n            \"climate\",\n            \"set_hvac_mode\",\n            {\"entity_id\": entity_id, \"hvac_mode\": mode},\n            blocking=True,\n            context=make_roommind_context(),\n        )\n""",
    """    if mode in (\"dry\", \"fan_only\"):\n        # Do not reassert an auxiliary mode that the physical device already\n        # reports.  This is especially important during HA startup, when the\n        # first coordinator refresh runs before RoomMind entities are created.\n        state = hass.states.get(entity_id)\n        if state is None or state.state != mode:\n            await hass.services.async_call(\n                \"climate\",\n                \"set_hvac_mode\",\n                {\"entity_id\": entity_id, \"hvac_mode\": mode},\n                blocking=True,\n                context=make_roommind_context(),\n            )\n""",
)

# Strengthen the window/startup regression test so it represents the real
# persisted RoomMind intent, not only a physical AC already in fan_only.
replace_once(
    "tests/coordinator/test_window_pause.py",
    """            \"window_sensors\": [\"binary_sensor.living_room_window\"],\n        }\n""",
    """            \"window_sensors\": [\"binary_sensor.living_room_window\"],\n            \"room_hvac_mode\": \"fan_only\",\n            \"keep_fan_only_on_window_open\": True,\n        }\n""",
)

# Add direct controller tests for the closed-window startup case and the
# redundant auxiliary-mode guard.
path = Path("tests/coordinator/test_window_pause.py")
text = path.read_text()
marker = "\n    @pytest.mark.asyncio\n    async def test_window_closed_normal_operation"
if marker not in text:
    raise SystemExit("window test insertion marker not found")
block = r'''
    @pytest.mark.asyncio
    async def test_persisted_fan_only_does_not_cycle_off_on_startup(self, hass, mock_config_entry):
        """Persisted fan_only intent must not send OFF before FAN_ONLY on first refresh."""
        ac_entity = "climate.living_room_ac"
        room = {
            **SAMPLE_ROOM,
            "thermostats": [],
            "acs": [ac_entity],
            "devices": [{"entity_id": ac_entity, "type": "ac", "role": "auto", "heating_system_type": ""}],
            "room_hvac_mode": "fan_only",
            "keep_fan_only_on_window_open": True,
            "window_sensors": [],
        }
        store = _make_store_mock({"living_room_abc12345": room})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                extra={
                    ac_entity: (
                        "off",
                        {"hvac_modes": ["off", "cool", "fan_only"], "min_temp": 16.0, "max_temp": 30.0},
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
        assert call(
            "climate",
            "set_hvac_mode",
            {"entity_id": ac_entity, "hvac_mode": "fan_only"},
            blocking=True,
            context=ANY,
        ) in calls

    @pytest.mark.asyncio
    async def test_persisted_fan_only_already_active_is_not_reasserted(self, hass, mock_config_entry):
        """Startup must not resend FAN_ONLY when the AC already reports fan_only."""
        ac_entity = "climate.living_room_ac"
        room = {
            **SAMPLE_ROOM,
            "thermostats": [],
            "acs": [ac_entity],
            "devices": [{"entity_id": ac_entity, "type": "ac", "role": "auto", "heating_system_type": ""}],
            "room_hvac_mode": "fan_only",
            "keep_fan_only_on_window_open": True,
            "window_sensors": [],
        }
        store = _make_store_mock({"living_room_abc12345": room})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                extra={
                    ac_entity: (
                        "fan_only",
                        {"hvac_modes": ["off", "cool", "fan_only"], "min_temp": 16.0, "max_temp": 30.0},
                    )
                },
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        hvac_calls = [c for c in hass.services.async_call.call_args_list if len(c.args) >= 2 and c.args[:2] == ("climate", "set_hvac_mode")]
        assert not any(c.args[2].get("entity_id") == ac_entity for c in hvac_calls)

'''
path.write_text(text.replace(marker, block + marker, 1))
