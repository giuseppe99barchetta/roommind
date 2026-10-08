"""RoomMind panel URLs must change when the frontend asset changes."""

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind import _async_register_panel
from custom_components.roommind.const import DOMAIN


@pytest.mark.asyncio
async def test_panel_url_is_versioned_from_the_actual_frontend_content():
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    hass.http.async_register_static_paths = AsyncMock()
    hass.async_add_executor_job = AsyncMock(side_effect=lambda callback: callback())

    with patch("custom_components.roommind.async_register_built_in_panel") as register:
        await _async_register_panel(hass)

    js = Path(__file__).resolve().parents[1] / "custom_components/roommind/frontend/roommind-panel.js"
    digest = hashlib.sha256(js.read_bytes()).hexdigest()[:12]
    assert register.call_args.kwargs["config"]["_panel_custom"]["js_url"] == (
        f"/roommind/roommind-panel.js?v={digest}"
    )
    assert hass.data[DOMAIN]["panel_registered"] is True
