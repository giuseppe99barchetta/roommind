"""Tests for notification_utils.py — notification sending and throttling."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import homeassistant.helpers.config_validation as cv
import pytest
import voluptuous as vol
from homeassistant.components.notify.const import NOTIFY_SERVICE_SCHEMA

from custom_components.roommind.utils.notification_utils import (
    NotificationThrottler,
    async_send_mold_notification,
    dismiss_mold_notification,
)

# --- NotificationThrottler ---


class TestNotificationThrottler:
    def test_allows_first_send(self):
        """First send for a key should always be allowed."""
        throttler = NotificationThrottler()
        assert throttler.should_send("test_key", cooldown_seconds=3600) is True

    def test_blocks_within_cooldown(self):
        """Should block if cooldown has not elapsed."""
        throttler = NotificationThrottler()
        throttler.record_sent("test_key")
        assert throttler.should_send("test_key", cooldown_seconds=3600) is False

    def test_allows_after_cooldown(self):
        """Should allow after cooldown has elapsed."""
        throttler = NotificationThrottler()
        throttler._last_sent["test_key"] = time.time() - 3601
        assert throttler.should_send("test_key", cooldown_seconds=3600) is True

    def test_independent_keys(self):
        """Different keys have independent cooldowns."""
        throttler = NotificationThrottler()
        throttler.record_sent("key_a")
        assert throttler.should_send("key_a", cooldown_seconds=3600) is False
        assert throttler.should_send("key_b", cooldown_seconds=3600) is True

    def test_clear_resets_throttle(self):
        """Clearing a key allows immediate re-send."""
        throttler = NotificationThrottler()
        throttler.record_sent("test_key")
        assert throttler.should_send("test_key", cooldown_seconds=3600) is False
        throttler.clear("test_key")
        assert throttler.should_send("test_key", cooldown_seconds=3600) is True

    def test_clear_nonexistent_key_safe(self):
        """Clearing a key that was never recorded should not error."""
        throttler = NotificationThrottler()
        throttler.clear("nonexistent")  # should not raise


# --- async_send_mold_notification ---


async def _send(hass, *args, **kwargs):
    """Call async_send_mold_notification and wait for its background delivery."""
    hass.async_create_background_task = MagicMock(side_effect=lambda coro, name: asyncio.ensure_future(coro))
    task = await async_send_mold_notification(hass, *args, **kwargs)
    if task is not None:
        await task
    return task


@pytest.mark.asyncio
async def test_send_notification_with_targets():
    """Should call notify.send_message for each target."""
    hass = MagicMock()
    hass.services.async_call = AsyncMock()

    targets = [
        {"entity_id": "notify.mobile_app_kevin", "person_entity": "", "notify_when": "always"},
        {"entity_id": "notify.mobile_app_lisa", "person_entity": "", "notify_when": "always"},
    ]

    await _send(
        hass,
        "living_room",
        targets,
        message="Test mold alert",
        title="RoomMind: Test",
    )

    assert hass.services.async_call.call_count == 2
    for call in hass.services.async_call.call_args_list:
        assert call[0][0] == "notify"
        assert call[0][1] == "send_message"
        assert call[0][2] == {
            "entity_id": call[0][2]["entity_id"],
            "message": "Test mold alert",
            "title": "RoomMind: Test",
        }
        assert call.kwargs == {"blocking": True}


@pytest.mark.asyncio
async def test_send_notification_home_only_skips_away():
    """Target with home_only should be skipped when person is away."""
    hass = MagicMock()
    hass.services.async_call = AsyncMock()

    person_state = MagicMock()
    person_state.state = "not_home"
    hass.states.get = MagicMock(return_value=person_state)

    targets = [
        {"entity_id": "notify.mobile_app_kevin", "person_entity": "person.kevin", "notify_when": "home_only"},
    ]

    with patch("custom_components.roommind.utils.notification_utils.async_create") as mock_persistent:
        await _send(
            hass,
            "living_room",
            targets,
            message="Test",
            title="Test",
        )

    # notify service should NOT be called
    hass.services.async_call.assert_not_called()
    # Fallback persistent notification should be created (all targets skipped)
    mock_persistent.assert_called_once()


@pytest.mark.asyncio
async def test_send_notification_home_only_sends_when_home():
    """Target with home_only should be sent when person is home."""
    hass = MagicMock()
    hass.services.async_call = AsyncMock()

    person_state = MagicMock()
    person_state.state = "home"
    hass.states.get = MagicMock(return_value=person_state)

    targets = [
        {"entity_id": "notify.mobile_app_kevin", "person_entity": "person.kevin", "notify_when": "home_only"},
    ]

    await _send(
        hass,
        "living_room",
        targets,
        message="Test",
        title="Test",
    )

    hass.services.async_call.assert_called_once()


@pytest.mark.asyncio
async def test_send_notification_no_targets_persistent():
    """Empty targets list → fallback to persistent notification."""
    hass = MagicMock()

    with patch("custom_components.roommind.utils.notification_utils.async_create") as mock_create:
        await _send(
            hass,
            "living_room",
            [],
            message="Test mold alert",
            title="RoomMind: Test",
        )

    mock_create.assert_called_once_with(
        hass,
        "Test mold alert",
        title="RoomMind: Test",
        notification_id="roommind_mold_living_room_risk",
    )


@pytest.mark.asyncio
async def test_send_notification_person_unavailable_treated_as_home():
    """Person entity unavailable → treated as home (fail-safe)."""
    hass = MagicMock()
    hass.services.async_call = AsyncMock()

    person_state = MagicMock()
    person_state.state = "unavailable"
    notify_state = MagicMock()
    notify_state.state = "unknown"
    hass.states.get = MagicMock(side_effect=lambda eid: person_state if eid == "person.kevin" else notify_state)

    targets = [
        {"entity_id": "notify.mobile_app_kevin", "person_entity": "person.kevin", "notify_when": "home_only"},
    ]

    await _send(
        hass,
        "living_room",
        targets,
        message="Test",
        title="Test",
    )

    # Should send because unavailable is treated as home
    hass.services.async_call.assert_called_once()


@pytest.mark.asyncio
async def test_send_notification_custom_tag_suffix():
    """Tag is for persistent fallback, not unsupported notify.send_message data."""
    hass = MagicMock()
    hass.services.async_call = AsyncMock()

    targets = [
        {"entity_id": "notify.mobile_app_kevin", "person_entity": "", "notify_when": "always"},
    ]

    await _send(
        hass,
        "bedroom",
        targets,
        message="Prevention active",
        title="RoomMind",
        tag_suffix="prevention",
    )

    call_data = hass.services.async_call.call_args[0][2]
    assert call_data == {
        "entity_id": "notify.mobile_app_kevin",
        "message": "Prevention active",
        "title": "RoomMind",
    }


# --- dismiss_mold_notification ---


def test_dismiss_notification():
    """Should dismiss persistent notification with correct ID."""
    hass = MagicMock()

    with patch("custom_components.roommind.utils.notification_utils.async_dismiss") as mock_dismiss:
        dismiss_mold_notification(hass, "living_room", "risk")

    mock_dismiss.assert_called_once_with(hass, "roommind_mold_living_room_risk")


def test_dismiss_notification_prevention_suffix():
    """Should use correct suffix for prevention notifications."""
    hass = MagicMock()

    with patch("custom_components.roommind.utils.notification_utils.async_dismiss") as mock_dismiss:
        dismiss_mold_notification(hass, "bedroom", "prevention")

    mock_dismiss.assert_called_once_with(hass, "roommind_mold_bedroom_prevention")


@pytest.mark.asyncio
async def test_send_notification_skips_target_with_empty_entity_id():
    """Target with empty entity_id should be skipped (no notify call)."""
    hass = MagicMock()
    hass.services.async_call = AsyncMock()

    targets = [{"entity_id": "", "person_entity": "", "notify_when": "always"}]

    with patch("custom_components.roommind.utils.notification_utils.async_create") as mock_create:
        await _send(
            hass,
            "living_room",
            targets,
            message="Test",
            title="Test",
        )

    hass.services.async_call.assert_not_called()
    mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_send_notification_service_exception_triggers_fallback():
    """If notify service raises, warning is logged and fallback is used."""
    hass = MagicMock()
    hass.services.async_call = AsyncMock(side_effect=Exception("service unavailable"))

    targets = [{"entity_id": "notify.test", "person_entity": "", "notify_when": "always"}]

    with patch("custom_components.roommind.utils.notification_utils.async_create") as mock_create:
        await _send(
            hass,
            "living_room",
            targets,
            message="Test",
            title="Test",
        )

    mock_create.assert_called_once()


# The schemas Home Assistant registers: the entity action only takes message and title
# (extra keys rejected), a legacy notify service also takes data (#502).
SEND_MESSAGE_SCHEMA = cv.make_entity_service_schema(
    {vol.Required("message"): cv.string, vol.Optional("title"): cv.string}
)


def _notify_hass(entities: frozenset[str] = frozenset(), legacy: frozenset[str] = frozenset()) -> MagicMock:
    """hass whose notify actions validate like Home Assistant's."""
    hass = MagicMock()
    hass.states.get = MagicMock(side_effect=lambda eid: MagicMock(state="unknown") if eid in entities else None)
    hass.services.has_service = MagicMock(side_effect=lambda domain, service: domain == "notify" and service in legacy)

    async def _call(domain, service, data, **kwargs):
        if service == "send_message":
            SEND_MESSAGE_SCHEMA(data)
        else:
            NOTIFY_SERVICE_SCHEMA(data)

    hass.services.async_call = AsyncMock(side_effect=_call)
    return hass


@pytest.mark.asyncio
async def test_unavailable_notify_entity_counts_as_failed():
    """HA skips an unavailable entity without an error; the alert must still reach the sidebar."""
    hass = _notify_hass(entities=frozenset({"notify.pixel_9"}))
    hass.states.get = MagicMock(return_value=MagicMock(state="unavailable"))
    targets = [{"entity_id": "notify.pixel_9", "person_entity": "", "notify_when": "always"}]

    with patch("custom_components.roommind.utils.notification_utils.async_create") as mock_create:
        await _send(hass, "living_room", targets, "Alert", "RoomMind")

    hass.services.async_call.assert_not_awaited()
    mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_other_legacy_services_get_no_data():
    """Only the Companion app knows tag and group; e.g. signal_messenger rejects them."""
    hass = _notify_hass(legacy=frozenset({"signal_home"}))
    targets = [{"entity_id": "notify.signal_home", "person_entity": "", "notify_when": "always"}]

    await _send(hass, "living_room", targets, "Alert", "RoomMind")

    hass.services.async_call.assert_awaited_once_with(
        "notify", "signal_home", {"message": "Alert", "title": "RoomMind"}, blocking=True
    )


@pytest.mark.asyncio
async def test_delivery_waits_in_the_background_and_a_hanging_push_falls_back(monkeypatch):
    """The cycle gets the task back before the push answers; a push that never answers times out."""
    monkeypatch.setattr("custom_components.roommind.utils.notification_utils.NOTIFY_TIMEOUT_S", 0.05)
    hass = _notify_hass(entities=frozenset({"notify.pixel_9"}))
    hass.async_create_background_task = MagicMock(side_effect=lambda coro, name: asyncio.ensure_future(coro))

    async def _hangs(*args, **kwargs):
        await asyncio.sleep(10)

    hass.services.async_call.side_effect = _hangs
    targets = [{"entity_id": "notify.pixel_9", "person_entity": "", "notify_when": "always"}]

    with patch("custom_components.roommind.utils.notification_utils.async_create") as mock_create:
        task = await async_send_mold_notification(hass, "living_room", targets, "Alert", "RoomMind")
        assert task is not None and not task.done()
        mock_create.assert_not_called()
        await task

    mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_dismissal_cancels_a_hanging_delivery_so_no_late_fallback(monkeypatch):
    """The condition cleared while a push hangs: the timeout must not post a stale sidebar alert."""
    from custom_components.roommind.utils import notification_utils as nu

    monkeypatch.setattr(nu, "NOTIFY_TIMEOUT_S", 0.05)
    hass = _notify_hass(entities=frozenset({"notify.pixel_9"}))
    hass.async_create_background_task = MagicMock(side_effect=lambda coro, name: asyncio.ensure_future(coro))

    async def _hangs(*args, **kwargs):
        await asyncio.sleep(10)

    hass.services.async_call.side_effect = _hangs
    targets = [{"entity_id": "notify.pixel_9", "person_entity": "", "notify_when": "always"}]
    with (
        patch("custom_components.roommind.utils.notification_utils.async_create") as mock_create,
        patch("custom_components.roommind.utils.notification_utils.async_dismiss"),
    ):
        task = await async_send_mold_notification(hass, "living_room", targets, "Alert", "RoomMind")
        dismiss_mold_notification(hass, "living_room")
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.1)
    mock_create.assert_not_called()
    assert nu._pending_deliveries == {}


@pytest.mark.asyncio
async def test_a_new_alert_replaces_the_pending_delivery_of_the_same_tag():
    from custom_components.roommind.utils import notification_utils as nu

    hass = _notify_hass(entities=frozenset({"notify.pixel_9"}))
    hass.async_create_background_task = MagicMock(side_effect=lambda coro, name: asyncio.ensure_future(coro))
    gate = asyncio.Event()

    async def _waits(*args, **kwargs):
        await gate.wait()

    hass.services.async_call.side_effect = _waits
    targets = [{"entity_id": "notify.pixel_9", "person_entity": "", "notify_when": "always"}]
    first = await async_send_mold_notification(hass, "living_room", targets, "Alert 1", "RoomMind")
    second = await async_send_mold_notification(hass, "living_room", targets, "Alert 2", "RoomMind")
    await asyncio.sleep(0)
    assert first.cancelled()
    gate.set()
    await second
    assert nu._pending_deliveries == {}
