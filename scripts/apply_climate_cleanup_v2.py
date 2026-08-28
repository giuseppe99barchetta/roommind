from pathlib import Path


def replace(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"pattern not found: {label}")
    return text.replace(old, new, 1)


p = Path("custom_components/roommind/climate.py")
text = p.read_text()

# Keep the legacy override class importable for compatibility/tests, but stop
# creating an override entity. Registry cleanup removes already-created ones.
text = replace(
    text,
    '    return [RoomMindClimate(coordinator, area_id), RoomMindOverrideClimate(coordinator, area_id)]',
    '    return [RoomMindClimate(coordinator, area_id)]',
    "canonical climate creation",
)

# Auxiliary direct modes are physical state, and any configured AC may be the
# one currently running (multi-AC rooms).
text = replace(
    text,
'''    def _physical_ac_mode(self) -> str | None:
        acs = get_ac_eids((self._room() or {}).get("devices", []))
        if not acs:
            return None
        state = self.coordinator.hass.states.get(acs[0])
        return state.state if state is not None else None
''',
'''    def _physical_ac_modes(self) -> tuple[str, ...]:
        modes: list[str] = []
        for entity_id in get_ac_eids((self._room() or {}).get("devices", [])):
            state = self.coordinator.hass.states.get(entity_id)
            if state is not None and state.state not in ("unknown", "unavailable"):
                modes.append(state.state)
        return tuple(modes)
''',
    "physical AC modes",
)
text = replace(
    text,
    '            return HVACMode(selected) if self._physical_ac_mode() == selected else HVACMode.OFF',
    '            return HVACMode(selected) if selected in self._physical_ac_modes() else HVACMode.OFF',
    "aux physical state",
)

# Hard-safety guard for manual activation. Explicit manual commands bypass
# schedules/presence/windows/MPC policy, but not compressor min-off or power budget.
needle = '    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:\n'
guard = '''    def _manual_activation_guard(self, mode: str) -> None:
        """Reject manual thermal activation when a hard safety blocks it."""
        if mode not in ("heat", "cool", "dry"):
            return

        room = self._room() or {}
        hass = self.coordinator.hass
        acs = get_ac_eids(room.get("devices", []))
        if not acs:
            return
        store = hass.data[DOMAIN]["store"]
        settings = store.get_settings()

        compressor = self.coordinator._compressor_manager
        compressor.load_groups(settings.get("compressor_groups", []))
        for entity_id in acs:
            state = hass.states.get(entity_id)
            already_running = bool(
                state and state.state not in ("off", "unknown", "unavailable", "fan_only")
            )
            if not already_running and not compressor.check_can_activate(entity_id):
                raise ValueError(f"Compressor minimum-off protection blocks {entity_id}")

        if not settings.get("power_budget_enabled", False):
            return

        running_loads: dict[str, float] = {}
        for area_id, other in store.get_rooms().items():
            other_acs = get_ac_eids(other.get("devices", []))
            if any(
                (state := hass.states.get(entity_id))
                and state.state not in ("off", "unknown", "unavailable", "fan_only")
                for entity_id in other_acs
            ):
                running_loads[area_id] = float(other.get("heat_pump_power_watts", 0) or 0)

        budget = self.coordinator._power_budget_manager
        budget.begin_cycle(hass, settings, running_loads)
        if not budget.request_heat_pump(
            self._area_id,
            float(room.get("heat_pump_power_watts", 0) or 0),
            self._area_id in running_loads,
        ):
            raise ValueError("RoomMind power budget blocks this climate activation")

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
'''
text = replace(text, needle, guard, "manual safety guard")

# Validate and apply direct mode before persisting it. If safety rejects the
# command, the canonical entity must not claim a mode that hardware did not enter.
old = '''        await self.coordinator.hass.data[DOMAIN]["store"].async_update_room(self._area_id, updates)

        # Explicit HEAT/COOL/OFF/FAN_ONLY/DRY are direct manual commands. AUTO
        # is different: it is permission for RoomMind to choose one direction,
        # so it must never directly switch both heating and cooling hardware on.
        if mode != "auto":
            await self._async_apply_manual_hvac_mode(mode, heat, cool)
        await self.coordinator.async_request_refresh()
'''
new = '''        # Explicit HEAT/COOL/OFF/FAN_ONLY/DRY are direct manual commands. AUTO
        # is different: it is permission for RoomMind to choose one direction,
        # so it must never directly switch both heating and cooling hardware on.
        # Validate hard safety before persisting a mode that cannot be applied.
        if mode != "auto":
            self._manual_activation_guard(mode)
            await self._async_apply_manual_hvac_mode(mode, heat, cool)
        await self.coordinator.hass.data[DOMAIN]["store"].async_update_room(self._area_id, updates)
        await self.coordinator.async_request_refresh()
'''
text = replace(text, old, new, "manual HVAC ordering")

# For explicit thermal modes, validate hard safety before persisting a new
# setpoint. AUTO while idle remains a logical-only change and never wakes hardware.
old = '''        store = self.coordinator.hass.data[DOMAIN]["store"]
        mode = selected.value if selected != HVACMode.OFF else "heat_cool"
        await store.async_update_room(
'''
new = '''        if selected in (HVACMode.HEAT, HVACMode.COOL, HVACMode.DRY):
            self._manual_activation_guard(selected.value)
        store = self.coordinator.hass.data[DOMAIN]["store"]
        mode = selected.value if selected != HVACMode.OFF else "heat_cool"
        await store.async_update_room(
'''
text = replace(text, old, new, "manual temperature safety ordering")

# OFF updates compressor bookkeeping after the explicit hardware shutdown.
text = replace(
    text,
'''        if mode == "off":
            for entity_id in get_all_entity_ids(devices):
                await async_turn_off_climate(hass, entity_id, area_id=self._area_id)
            return
''',
'''        if mode == "off":
            for entity_id in get_all_entity_ids(devices):
                await async_turn_off_climate(hass, entity_id, area_id=self._area_id)
                self.coordinator._compressor_manager.update_member(entity_id, False)
            return
''',
    "manual off tracking",
)

# Apply explicit manual HVAC mode to every configured AC rather than only acs[0].
old = '''        if not acs:
            return
        entity_id = acs[0]
        state = hass.states.get(entity_id)
        supported = state.attributes.get("hvac_modes", []) if state else []
        resolved = resolve_hvac_mode(mode, supported)
        if resolved is None:
            return
        await hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": entity_id, "hvac_mode": resolved},
            blocking=True,
        )
        if mode in ("cool", "heat", "heat_cool", "auto"):
            data: dict[str, Any] = {"entity_id": entity_id}
            if mode in ("heat_cool", "auto") and state and state.attributes.get("target_temp_low") is not None:
                data.update(
                    target_temp_low=quantize_temperature_for_entity(
                        hass, entity_id, celsius_to_ha_temp(hass, heat), fallback_step=1.0
                    ),
                    target_temp_high=quantize_temperature_for_entity(
                        hass, entity_id, celsius_to_ha_temp(hass, cool), fallback_step=1.0
                    ),
                )
            else:
                target = cool if mode == "cool" else heat
                data["temperature"] = quantize_temperature_for_entity(
                    hass, entity_id, celsius_to_ha_temp(hass, target), fallback_step=1.0
                )
            await hass.services.async_call("climate", "set_temperature", data, blocking=True)
'''
new = '''        if not acs:
            return
        compressor = self.coordinator._compressor_manager
        for entity_id in acs:
            state = hass.states.get(entity_id)
            supported = state.attributes.get("hvac_modes", []) if state else []
            resolved = resolve_hvac_mode(mode, supported)
            if resolved is None:
                continue
            await hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": entity_id, "hvac_mode": resolved},
                blocking=True,
            )
            if mode in ("cool", "heat", "heat_cool", "auto"):
                data: dict[str, Any] = {"entity_id": entity_id}
                if mode in ("heat_cool", "auto") and state and state.attributes.get("target_temp_low") is not None:
                    data.update(
                        target_temp_low=quantize_temperature_for_entity(
                            hass, entity_id, celsius_to_ha_temp(hass, heat), fallback_step=1.0
                        ),
                        target_temp_high=quantize_temperature_for_entity(
                            hass, entity_id, celsius_to_ha_temp(hass, cool), fallback_step=1.0
                        ),
                    )
                else:
                    target = cool if mode == "cool" else heat
                    data["temperature"] = quantize_temperature_for_entity(
                        hass, entity_id, celsius_to_ha_temp(hass, target), fallback_step=1.0
                    )
                await hass.services.async_call("climate", "set_temperature", data, blocking=True)
            compressor.update_member(entity_id, mode in ("heat", "cool", "dry"))
'''
text = replace(text, old, new, "multi AC manual HVAC")

# Fan/swing settings are room-level, so apply them to every AC in the room.
old = '''        store = self.coordinator.hass.data[DOMAIN]["store"]
        await store.async_update_room(self._area_id, {key: value})
        await self.coordinator.hass.services.async_call(
            "climate", service, {"entity_id": acs[0], service_key: value}, blocking=True
        )
'''
new = '''        store = self.coordinator.hass.data[DOMAIN]["store"]
        await store.async_update_room(self._area_id, {key: value})
        for entity_id in acs:
            await self.coordinator.hass.services.async_call(
                "climate", service, {"entity_id": entity_id, service_key: value}, blocking=True
            )
'''
text = replace(text, old, new, "multi AC options")

p.write_text(text)
