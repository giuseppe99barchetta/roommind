"""Dashboard card registration (#346)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.roommind import CARD_URL, _async_register_card
from custom_components.roommind.const import DOMAIN

pytestmark = pytest.mark.asyncio

CARD = b"customElements.define('roommind-room-card')"
DIGEST = hashlib.sha256(CARD).hexdigest()[:12]


@pytest.fixture
def card_hass(hass):
    hass.data[DOMAIN] = {}
    hass.http.async_register_static_paths = AsyncMock()
    return hass


def _built(exists: bool = True):
    return (
        patch.object(Path, "exists", return_value=exists),
        patch.object(Path, "read_bytes", return_value=CARD),
        patch("custom_components.roommind.add_extra_js_url"),
    )


async def test_the_card_loads_on_every_page_with_a_content_query(card_hass):
    exists, read, add = _built()
    with exists, read, add as add_url:
        await _async_register_card(card_hass)

    card_hass.http.async_register_static_paths.assert_awaited_once()
    (config,) = card_hass.http.async_register_static_paths.await_args.args[0]
    assert config.url_path == CARD_URL
    add_url.assert_called_once_with(card_hass, f"{CARD_URL}?v={DIGEST}")


async def test_a_reload_registers_the_card_only_once(card_hass):
    exists, read, add = _built()
    with exists, read, add as add_url:
        await _async_register_card(card_hass)
        await _async_register_card(card_hass)

    assert add_url.call_count == 1
    card_hass.http.async_register_static_paths.assert_awaited_once()


async def test_an_already_served_path_still_adds_the_card(card_hass):
    card_hass.http.async_register_static_paths.side_effect = RuntimeError("already registered")
    exists, read, add = _built()
    with exists, read, add as add_url:
        await _async_register_card(card_hass)

    add_url.assert_called_once()


async def test_without_a_built_card_nothing_is_registered(card_hass):
    exists, read, add = _built(exists=False)
    with exists, read, add as add_url:
        await _async_register_card(card_hass)

    add_url.assert_not_called()
    card_hass.http.async_register_static_paths.assert_not_awaited()
    assert "card_registered" not in card_hass.data[DOMAIN]


async def test_the_built_card_bundle_defines_the_card():
    bundle = Path(__file__).parent.parent / "custom_components" / "roommind" / "frontend" / "roommind-card.js"
    code = bundle.read_text(encoding="utf-8")
    assert "customElements.define" in code and "roommind-room-card" in code
    assert "roommind-panel" not in code  # no panel component in the card bundle
