"""Tests for orphaned entity cleanup, history management."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .conftest import (
    _create_coordinator,
)


class TestCoverageGaps:
    """Tests covering uncovered coordinator lines."""

    def test_cleanup_orphaned_entities_removes_orphaned(self, hass, mock_config_entry):
        """cleanup_orphaned_entities removes entities for deleted rooms."""
        from custom_components.roommind.const import DOMAIN

        coordinator = _create_coordinator(hass, mock_config_entry)

        store = MagicMock()
        store.get_rooms.return_value = {"living_room": {"covers": ["cover.x"]}}
        hass.data = {DOMAIN: {"store": store}}

        # Simulate entity registry entries
        entry_valid_temp = MagicMock()
        entry_valid_temp.unique_id = f"{DOMAIN}_living_room_target_temp"
        entry_valid_temp.platform = "roommind"
        entry_valid_temp.entity_id = "sensor.roommind_living_room_target_temp"

        entry_valid_mode = MagicMock()
        entry_valid_mode.unique_id = f"{DOMAIN}_living_room_mode"
        entry_valid_mode.platform = "roommind"
        entry_valid_mode.entity_id = "sensor.roommind_living_room_mode"

        entry_valid_cover_auto = MagicMock()
        entry_valid_cover_auto.unique_id = f"{DOMAIN}_living_room_cover_auto"
        entry_valid_cover_auto.platform = "roommind"
        entry_valid_cover_auto.entity_id = "switch.roommind_living_room_cover_auto"

        entry_valid_cover_paused = MagicMock()
        entry_valid_cover_paused.unique_id = f"{DOMAIN}_living_room_cover_paused"
        entry_valid_cover_paused.platform = "roommind"
        entry_valid_cover_paused.entity_id = "binary_sensor.roommind_living_room_cover_paused"

        # Orphaned: room no longer exists
        entry_orphaned_room = MagicMock()
        entry_orphaned_room.unique_id = f"{DOMAIN}_deleted_room_target_temp"
        entry_orphaned_room.platform = "roommind"
        entry_orphaned_room.entity_id = "sensor.roommind_deleted_room_target_temp"

        # Non-roommind entity -- should be ignored
        entry_other = MagicMock()
        entry_other.unique_id = "other_integration_something"
        entry_other.platform = "other_integration"
        entry_other.entity_id = "sensor.other_thing"

        mock_registry = MagicMock()
        # Global entity (not per-room) -- should be kept
        entry_vacation = MagicMock()
        entry_vacation.unique_id = f"{DOMAIN}_vacation"
        entry_vacation.platform = "roommind"
        entry_vacation.entity_id = "switch.roommind_vacation"

        entry_climate_control = MagicMock()
        entry_climate_control.platform = DOMAIN
        entry_climate_control.unique_id = f"{DOMAIN}_climate_control"
        entry_climate_control.entity_id = "switch.roommind_climate_control"

        mock_registry.entities.values.return_value = [
            entry_valid_temp,
            entry_valid_mode,
            entry_valid_cover_auto,
            entry_valid_cover_paused,
            entry_orphaned_room,
            entry_other,
            entry_vacation,
            entry_climate_control,
        ]

        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_registry,
        ):
            coordinator.cleanup_orphaned_entities()

        # Only the orphaned entity should be removed (vacation is global, not orphaned)
        mock_registry.async_remove.assert_called_once_with("sensor.roommind_deleted_room_target_temp")

    def test_cleanup_orphaned_entities_removes_cover_entities_without_covers(self, hass, mock_config_entry):
        """cleanup_orphaned_entities removes cover entities when room has no covers configured."""
        from custom_components.roommind.const import DOMAIN

        coordinator = _create_coordinator(hass, mock_config_entry)

        store = MagicMock()
        # Room exists but has no covers
        store.get_rooms.return_value = {"living_room": {}}
        hass.data = {DOMAIN: {"store": store}}

        entry_cover_auto = MagicMock()
        entry_cover_auto.unique_id = f"{DOMAIN}_living_room_cover_auto"
        entry_cover_auto.platform = "roommind"
        entry_cover_auto.entity_id = "switch.roommind_living_room_cover_auto"

        entry_cover_paused = MagicMock()
        entry_cover_paused.unique_id = f"{DOMAIN}_living_room_cover_paused"
        entry_cover_paused.platform = "roommind"
        entry_cover_paused.entity_id = "binary_sensor.roommind_living_room_cover_paused"

        entry_valid = MagicMock()
        entry_valid.unique_id = f"{DOMAIN}_living_room_target_temp"
        entry_valid.platform = "roommind"
        entry_valid.entity_id = "sensor.roommind_living_room_target_temp"

        mock_registry = MagicMock()
        mock_registry.entities.values.return_value = [
            entry_cover_auto,
            entry_cover_paused,
            entry_valid,
        ]

        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_registry,
        ):
            coordinator.cleanup_orphaned_entities()

        # Cover entities removed (room has no covers), target_temp kept
        removed_ids = [c.args[0] for c in mock_registry.async_remove.call_args_list]
        assert "switch.roommind_living_room_cover_auto" in removed_ids
        assert "binary_sensor.roommind_living_room_cover_paused" in removed_ids
        assert "sensor.roommind_living_room_target_temp" not in removed_ids

    def test_cleanup_orphaned_entities_no_orphans(self, hass, mock_config_entry):
        """cleanup_orphaned_entities does nothing when all entities are valid."""
        from custom_components.roommind.const import DOMAIN

        coordinator = _create_coordinator(hass, mock_config_entry)

        store = MagicMock()
        store.get_rooms.return_value = {"living_room": {"covers": ["cover.x"]}}
        hass.data = {DOMAIN: {"store": store}}

        entry_valid = MagicMock()
        entry_valid.unique_id = f"{DOMAIN}_living_room_target_temp"
        entry_valid.platform = "roommind"
        entry_valid.entity_id = "sensor.roommind_living_room_target_temp"

        mock_registry = MagicMock()
        mock_registry.entities.values.return_value = [entry_valid]

        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_registry,
        ):
            coordinator.cleanup_orphaned_entities()

        mock_registry.async_remove.assert_not_called()

    def test_cleanup_preserves_canonical_and_native_hybrid_entities(self, hass, mock_config_entry):
        """Cleanup preserves all current per-room and global entity types."""
        from custom_components.roommind.const import DOMAIN

        coordinator = _create_coordinator(hass, mock_config_entry)
        store = MagicMock()
        store.get_rooms.return_value = {"sala": {"devices": [{"entity_id": "climate.sala_ac", "type": "ac"}]}}
        hass.data = {DOMAIN: {"store": store}}

        entries = []
        for unique_id, entity_id in (
            (f"{DOMAIN}_sala", "climate.roommind_sala"),
            (f"{DOMAIN}_sala_override", "climate.roommind_sala_override"),
            (f"{DOMAIN}_sala_heat_source", "sensor.roommind_sala_heat_source"),
            (
                f"{DOMAIN}_sala_heat_source_reason",
                "sensor.roommind_sala_heat_source_reason",
            ),
            (f"{DOMAIN}_sala_dehumidification", "switch.roommind_sala_dehumidification"),
            (f"{DOMAIN}_vacation", "switch.roommind_vacation"),
            (f"{DOMAIN}_boiler_demand", "sensor.roommind_boiler_demand"),
            (f"{DOMAIN}_available_power", "sensor.roommind_available_power"),
            (f"{DOMAIN}_reserved_power", "sensor.roommind_reserved_power"),
            (f"{DOMAIN}_boiler_active", "binary_sensor.roommind_boiler_active"),
            (
                f"{DOMAIN}_hydraulic_path_safe",
                "binary_sensor.roommind_hydraulic_path_safe",
            ),
        ):
            entry = MagicMock()
            entry.unique_id = unique_id
            entry.platform = "roommind"
            entry.entity_id = entity_id
            entries.append(entry)

        mock_registry = MagicMock()
        mock_registry.entities.values.return_value = entries
        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_registry,
        ):
            coordinator.cleanup_orphaned_entities()

        assert {call.args[0] for call in mock_registry.async_remove.call_args_list} == {
            "climate.roommind_sala_override"
        }

    def test_cleanup_removes_deleted_rooms_and_obsolete_entity_types(self, hass, mock_config_entry):
        """Cleanup removes IDs not present in the authoritative ownership inventory."""
        from custom_components.roommind.const import DOMAIN

        coordinator = _create_coordinator(hass, mock_config_entry)
        store = MagicMock()
        store.get_rooms.return_value = {"sala": {}}
        hass.data = {DOMAIN: {"store": store}}

        entries = []
        for unique_id, entity_id in (
            (f"{DOMAIN}_deleted_room", "climate.roommind_deleted_room"),
            (
                f"{DOMAIN}_deleted_room_heat_source",
                "sensor.roommind_deleted_room_heat_source",
            ),
            (f"{DOMAIN}_sala_obsolete", "sensor.roommind_sala_obsolete"),
        ):
            entry = MagicMock()
            entry.unique_id = unique_id
            entry.platform = "roommind"
            entry.entity_id = entity_id
            entries.append(entry)

        mock_registry = MagicMock()
        mock_registry.entities.values.return_value = entries
        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_registry,
        ):
            coordinator.cleanup_orphaned_entities()

        assert {call.args[0] for call in mock_registry.async_remove.call_args_list} == {
            "climate.roommind_deleted_room",
            "sensor.roommind_deleted_room_heat_source",
            "sensor.roommind_sala_obsolete",
        }

    def test_cleanup_orphaned_entities_skips_non_string_unique_id(self, hass, mock_config_entry):
        """cleanup_orphaned_entities skips entities with non-string unique_id (e.g. int)."""
        from custom_components.roommind.const import DOMAIN

        coordinator = _create_coordinator(hass, mock_config_entry)

        store = MagicMock()
        store.get_rooms.return_value = {"living_room": {}}
        hass.data = {DOMAIN: {"store": store}}

        entry_int_uid = MagicMock()
        entry_int_uid.unique_id = 12345
        entry_int_uid.platform = "roommind"
        entry_int_uid.entity_id = "sensor.some_other_integration"

        entry_none_uid = MagicMock()
        entry_none_uid.unique_id = None
        entry_none_uid.platform = "roommind"
        entry_none_uid.entity_id = "sensor.no_uid"

        mock_registry = MagicMock()
        mock_registry.entities.values.return_value = [entry_int_uid, entry_none_uid]

        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_registry,
        ):
            coordinator.cleanup_orphaned_entities()

        mock_registry.async_remove.assert_not_called()

    @pytest.mark.asyncio
    async def test_room_removed_cleans_history_store(self, hass, mock_config_entry):
        """async_room_removed calls history_store.remove_room."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator.async_request_refresh = AsyncMock()

        mock_history_store = MagicMock()
        mock_history_store.remove_room = MagicMock()
        coordinator._history_store = mock_history_store

        mock_registry = MagicMock()
        mock_registry.entities = MagicMock()
        mock_registry.entities.values.return_value = []
        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_registry,
        ):
            await coordinator.async_room_removed("test_room")

        mock_history_store.remove_room.assert_called_once_with("test_room")

    def test_cleanup_keeps_entities_when_area_id_is_prefix_of_another(self, hass, mock_config_entry):
        """A shorter area_id must not claim a longer room's entities (#340).

        Rooms ``bedroom`` and ``bedroom_2_l`` coexist. The entity
        ``roommind_bedroom_2_l_override`` must survive cleanup — previously the
        prefix match against ``bedroom`` deleted it.
        """
        from custom_components.roommind.const import DOMAIN

        coordinator = _create_coordinator(hass, mock_config_entry)

        store = MagicMock()
        store.get_rooms.return_value = {"bedroom": {}, "bedroom_2_l": {}}
        hass.data = {DOMAIN: {"store": store}}

        entries = []
        for area in ("bedroom", "bedroom_2_l"):
            for suffix, domain in (
                ("target_temp", "sensor"),
                ("mode", "sensor"),
                ("climate_control", "switch"),
            ):
                e = MagicMock()
                e.unique_id = f"{DOMAIN}_{area}_{suffix}"
                e.platform = "roommind"
                e.entity_id = f"{domain}.{DOMAIN}_{area}_{suffix}"
                entries.append(e)

        mock_registry = MagicMock()
        mock_registry.entities.values.return_value = entries

        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_registry,
        ):
            coordinator.cleanup_orphaned_entities()

        # Nothing removed — every entity is owned by an existing room.
        mock_registry.async_remove.assert_not_called()

    @pytest.mark.asyncio
    async def test_room_removed_does_not_remove_prefix_sibling_entities(self, hass, mock_config_entry):
        """Removing ``bedroom`` must not delete ``bedroom_2_l`` entities (#340)."""
        from custom_components.roommind.const import DOMAIN

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator.async_request_refresh = AsyncMock()
        coordinator._history_store = None

        entry_bedroom = MagicMock()
        entry_bedroom.unique_id = f"{DOMAIN}_bedroom"
        entry_bedroom.platform = "roommind"
        entry_bedroom.entity_id = "climate.roommind_bedroom"

        entry_bedroom_heat_source = MagicMock()
        entry_bedroom_heat_source.unique_id = f"{DOMAIN}_bedroom_heat_source"
        entry_bedroom_heat_source.platform = "roommind"
        entry_bedroom_heat_source.entity_id = "sensor.roommind_bedroom_heat_source"

        entry_bedroom_heat_source_reason = MagicMock()
        entry_bedroom_heat_source_reason.unique_id = f"{DOMAIN}_bedroom_heat_source_reason"
        entry_bedroom_heat_source_reason.platform = "roommind"
        entry_bedroom_heat_source_reason.entity_id = "sensor.roommind_bedroom_heat_source_reason"

        entry_sibling = MagicMock()
        entry_sibling.unique_id = f"{DOMAIN}_bedroom_2_l"
        entry_sibling.platform = "roommind"
        entry_sibling.entity_id = "climate.roommind_bedroom_2_l"

        mock_registry = MagicMock()
        mock_registry.entities.values.return_value = [
            entry_bedroom,
            entry_bedroom_heat_source,
            entry_bedroom_heat_source_reason,
            entry_sibling,
        ]

        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_registry,
        ):
            await coordinator.async_room_removed("bedroom")

        removed_ids = [c.args[0] for c in mock_registry.async_remove.call_args_list]
        assert "climate.roommind_bedroom" in removed_ids
        assert "sensor.roommind_bedroom_heat_source" in removed_ids
        assert "sensor.roommind_bedroom_heat_source_reason" in removed_ids
        assert "climate.roommind_bedroom_2_l" not in removed_ids


def test_cleanup_removes_canonical_climate_for_outdoor_room(hass, mock_config_entry):
    from custom_components.roommind.const import DOMAIN

    coordinator = _create_coordinator(hass, mock_config_entry)
    store = MagicMock()
    store.get_rooms.return_value = {"terrace": {"area_id": "terrace", "is_outdoor": True}}
    hass.data = {DOMAIN: {"store": store}}

    entry = MagicMock()
    entry.unique_id = f"{DOMAIN}_terrace"
    entry.platform = "roommind"
    entry.entity_id = "climate.roommind_terrace"
    mock_registry = MagicMock()
    mock_registry.entities.values.return_value = [entry]

    with patch(
        "homeassistant.helpers.entity_registry.async_get",
        return_value=mock_registry,
    ):
        coordinator.cleanup_orphaned_entities()

    mock_registry.async_remove.assert_called_once_with("climate.roommind_terrace")


def test_cleanup_never_removes_entities_the_platforms_create(hass, mock_config_entry):
    """Regression: new sensors were created and then deleted again at every startup."""
    from custom_components.roommind.binary_sensor import (
        RoomMindAiringRecommendedSensor,
        RoomMindBoilerActiveSensor,
        RoomMindHydraulicPathSafeSensor,
    )
    from custom_components.roommind.const import DOMAIN
    from custom_components.roommind.sensor import (
        RoomMindAvailablePowerSensor,
        RoomMindBoilerDemandSensor,
        RoomMindReservedPowerSensor,
        _create_room_entities,
    )

    coordinator = _create_coordinator(hass, mock_config_entry)
    room = {"devices": [], "humidity_sensor": "sensor.h"}
    store = MagicMock()
    store.get_rooms.return_value = {"studio": room}
    hass.data = {DOMAIN: {"store": store}}

    created = [
        *_create_room_entities(coordinator, "studio", room),
        RoomMindAiringRecommendedSensor(coordinator),
        RoomMindBoilerActiveSensor(coordinator),
        RoomMindHydraulicPathSafeSensor(coordinator),
        RoomMindBoilerDemandSensor(coordinator),
        RoomMindAvailablePowerSensor(coordinator),
        RoomMindReservedPowerSensor(coordinator),
    ]
    entries = []
    for entity in created:
        entry = MagicMock()
        entry.unique_id = entity.unique_id
        entry.platform = "roommind"
        entry.entity_id = entity.entity_id
        entries.append(entry)
    mock_registry = MagicMock()
    mock_registry.entities.values.return_value = entries

    with patch("homeassistant.helpers.entity_registry.async_get", return_value=mock_registry):
        coordinator.cleanup_orphaned_entities()

    mock_registry.async_remove.assert_not_called()


def test_cleanup_ignores_foreign_platform_with_roommind_prefix(hass, mock_config_entry):
    """Startup cleanup never removes another platform's roommind_-prefixed entity (#433)."""
    from custom_components.roommind.const import DOMAIN

    coordinator = _create_coordinator(hass, mock_config_entry)
    store = MagicMock()
    store.get_rooms.return_value = {"living_room": {}}
    hass.data = {DOMAIN: {"store": store}}

    foreign = MagicMock()
    foreign.platform = "input_boolean"
    foreign.unique_id = f"{DOMAIN}_summer_mode"
    foreign.entity_id = "input_boolean.roommind_summer_mode"

    mock_registry = MagicMock()
    mock_registry.entities.values.return_value = [foreign]
    with patch("homeassistant.helpers.entity_registry.async_get", return_value=mock_registry):
        coordinator.cleanup_orphaned_entities()

    mock_registry.async_remove.assert_not_called()


@pytest.mark.asyncio
async def test_room_removed_ignores_foreign_platform_with_owned_unique_id(hass, mock_config_entry):
    """Deleting a room never removes another platform's entity sharing a generated unique ID."""
    from custom_components.roommind.const import DOMAIN

    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator.async_request_refresh = AsyncMock()
    room_id = "living_room"

    own = MagicMock()
    own.platform = DOMAIN
    own.unique_id = f"{DOMAIN}_{room_id}_target_temp"
    own.entity_id = f"sensor.roommind_{room_id}_target_temp"

    foreign = MagicMock()
    foreign.platform = "template"
    foreign.unique_id = f"{DOMAIN}_{room_id}_target_temp"
    foreign.entity_id = f"sensor.template_{room_id}_target_temp"

    mock_registry = MagicMock()
    mock_registry.entities.values.return_value = [own, foreign]
    with patch("homeassistant.helpers.entity_registry.async_get", return_value=mock_registry):
        await coordinator.async_room_removed(room_id)

    removed = [c.args[0] for c in mock_registry.async_remove.call_args_list]
    assert removed == [own.entity_id]
