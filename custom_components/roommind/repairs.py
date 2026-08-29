"""Repair flows for the RoomMind integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN


class RestartRequiredFixFlow(RepairsFlow):
    """Handler for restart-required repair."""

    async def async_step_init(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        """Ask the user to confirm a restart."""
        return await self.async_step_confirm_restart()

    async def async_step_confirm_restart(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        """Handle the confirm step."""
        if user_input is not None:
            await self.hass.services.async_call("homeassistant", "restart")
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="confirm_restart",
            data_schema=vol.Schema({}),
        )


async def async_sync_room_issues(hass: HomeAssistant, rooms: dict[str, dict], room_configs: dict[str, dict]) -> None:
    """Mirror current actionable anomalies into Home Assistant Repairs."""
    active_ids: set[str] = set()
    supported_types = {"sensor_stale", "long_run", "target_not_reached", "humidity_high", "ac_efficiency"}
    for area_id, state in rooms.items():
        room_name = room_configs.get(area_id, {}).get("display_name") or area_id
        anomalies = list(state.get("anomalies", []))
        if state.get("ac_efficiency_status") == "possible_issue":
            anomalies.append({"type": "ac_efficiency"})
        for anomaly in anomalies:
            anomaly_type = anomaly.get("type")
            if anomaly_type not in supported_types:
                continue
            issue_id = f"room_{area_id}_{anomaly_type}"
            active_ids.add(issue_id)
            ir.async_create_issue(
                hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                is_persistent=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=anomaly_type,
                translation_placeholders={"room": str(room_name)},
            )

    previous_ids: set[str] = hass.data[DOMAIN].get("room_issue_ids", set())
    for issue_id in previous_ids - active_ids:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    hass.data[DOMAIN]["room_issue_ids"] = active_ids


async def async_create_fix_flow(hass: HomeAssistant, issue_id: str, data: dict[str, str] | None) -> RepairsFlow:
    """Create flow."""
    return RestartRequiredFixFlow()
