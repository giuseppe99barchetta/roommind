"""Tests for the repair flows."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.repairs import (
    RestartRequiredFixFlow,
    async_create_fix_flow,
    async_sync_room_issues,
)


@pytest.mark.asyncio
async def test_create_fix_flow_returns_instance():
    """Factory returns a RestartRequiredFixFlow."""
    hass = MagicMock()
    flow = await async_create_fix_flow(hass, "restart_required", None)
    assert isinstance(flow, RestartRequiredFixFlow)


@pytest.mark.asyncio
async def test_init_step_delegates_to_confirm():
    """async_step_init delegates to async_step_confirm_restart."""
    flow = RestartRequiredFixFlow()
    flow.hass = MagicMock()
    # Patch the confirm step to track the call
    flow.async_step_confirm_restart = AsyncMock(return_value={"type": "form"})

    result = await flow.async_step_init()
    flow.async_step_confirm_restart.assert_called_once()
    assert result == {"type": "form"}


@pytest.mark.asyncio
async def test_confirm_restart_shows_form_without_input():
    """Without user_input, shows a confirmation form."""
    flow = RestartRequiredFixFlow()
    flow.hass = MagicMock()
    flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "confirm_restart"})

    await flow.async_step_confirm_restart(user_input=None)
    flow.async_show_form.assert_called_once()
    call_kwargs = flow.async_show_form.call_args
    assert call_kwargs[1]["step_id"] == "confirm_restart"


@pytest.mark.asyncio
async def test_confirm_restart_triggers_restart():
    """With user_input, triggers HA restart and creates entry."""
    flow = RestartRequiredFixFlow()
    flow.hass = MagicMock()
    flow.hass.services.async_call = AsyncMock()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

    result = await flow.async_step_confirm_restart(user_input={})

    flow.hass.services.async_call.assert_called_once_with("homeassistant", "restart")
    flow.async_create_entry.assert_called_once_with(title="", data={})
    assert result == {"type": "create_entry"}


@pytest.mark.asyncio
async def test_sync_room_issues_creates_current_anomalies_and_clears_resolved():
    hass = MagicMock()
    hass.data = {"roommind": {"room_issue_ids": {"room_kitchen_long_run"}}}
    rooms = {
        "kitchen": {
            "anomalies": [{"type": "sensor_stale"}],
            "ac_efficiency_status": "possible_issue",
        }
    }

    with (
        patch("custom_components.roommind.repairs.ir.async_create_issue") as create_issue,
        patch("custom_components.roommind.repairs.ir.async_delete_issue") as delete_issue,
    ):
        await async_sync_room_issues(hass, rooms, {"kitchen": {"display_name": "Kitchen"}})

    assert create_issue.call_count == 2
    assert {call.args[2] for call in create_issue.call_args_list} == {
        "room_kitchen_sensor_stale",
        "room_kitchen_ac_efficiency",
    }
    delete_issue.assert_called_once_with(hass, "roommind", "room_kitchen_long_run")
