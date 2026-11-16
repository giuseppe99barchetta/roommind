"""Notification utilities for RoomMind.

Provides throttled notification sending to HA notify entities with
per-device home/away filtering and persistent-notification fallback.
"""

from __future__ import annotations

import asyncio
import logging
import time

from homeassistant.components.persistent_notification import (
    async_create,
    async_dismiss,
)
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

NOTIF_PREFIX = "roommind_mold_"
# Per target; a phone push that hangs must not hold back the others or the fallback
NOTIFY_TIMEOUT_S = 15
# Running deliveries by tag: a dismissal cancels them, so a late failure cannot
# post the sidebar fallback for a condition that has already cleared.
_pending_deliveries: dict[str, asyncio.Task[None]] = {}


class NotificationThrottler:
    """Per-key in-memory throttling to prevent notification spam."""

    def __init__(self) -> None:
        self._last_sent: dict[str, float] = {}

    def should_send(self, key: str, cooldown_seconds: float) -> bool:
        """Return True if enough time has passed since the last send for *key*."""
        now = time.time()
        last = self._last_sent.get(key, 0.0)
        return (now - last) >= cooldown_seconds

    def record_sent(self, key: str) -> None:
        """Record that a notification was just sent for *key*."""
        self._last_sent[key] = time.time()

    def clear(self, key: str) -> None:
        """Clear throttle state for *key* (allows immediate re-send)."""
        self._last_sent.pop(key, None)


def _is_person_home(hass: HomeAssistant, person_entity: str) -> bool:
    """Check if a person entity is home (fail-safe: unknown/unavailable → home)."""
    state = hass.states.get(person_entity)
    if state is None or state.state in ("unavailable", "unknown"):
        return True  # fail-safe: treat as home
    return bool(state.state == "home")


async def async_send_mold_notification(
    hass: HomeAssistant,
    area_id: str,
    targets: list[dict],
    message: str,
    title: str,
    tag_suffix: str = "risk",
) -> asyncio.Task[None] | None:
    """Send mold notification to configured targets.

    For each target dict ``{entity_id, person_entity, notify_when}``:
    - If ``notify_when == "home_only"`` and *person_entity* is set and the
      person is not home, the target is skipped.
    - Otherwise the notification is sent via ``notify.send_message``.
      That entity action only accepts ``message`` and ``title``; the tag is
      used by the persistent-notification fallback, not passed as ``data``.

    If *targets* is empty, a persistent HA notification is created as fallback.
    The sends run in a background task (returned), each waits for the delivery,
    so the coordinator cycle does not; the fallback follows when all of them failed.

    Args:
        hass: Home Assistant instance.
        area_name: Human-readable area name (for display in notifications).
        targets: List of notification target dicts.
        message: Notification body text.
        title: Notification title.
        tag_suffix: Suffix for deduplication tag (e.g. "risk", "prevention").
    """
    tag = f"{NOTIF_PREFIX}{area_id}_{tag_suffix}"
    notification_id = tag

    if not targets:
        # Fallback: persistent notification in HA sidebar
        async_create(hass, message, title=title, notification_id=notification_id)
        return None

    recipients: list[str] = []
    for target in targets:
        entity_id = target.get("entity_id", "")
        if not entity_id:
            continue

        # Home/away filtering
        person_entity = target.get("person_entity", "")
        notify_when = target.get("notify_when", "always")
        if notify_when == "home_only" and person_entity:
            if not _is_person_home(hass, person_entity):
                _LOGGER.debug(
                    "Skipping mold notification to %s — person %s is away",
                    entity_id,
                    person_entity,
                )
                continue
        recipients.append(entity_id)

    if not recipients:
        # All targets were skipped → persistent fallback
        async_create(hass, message, title=title, notification_id=notification_id)
        return None
    previous = _pending_deliveries.pop(tag, None)
    if previous is not None and not previous.done():
        previous.cancel()
    task: asyncio.Task[None] = hass.async_create_background_task(
        _async_deliver(hass, recipients, message, title, tag), name=f"roommind_notify_{tag}"
    )
    _pending_deliveries[tag] = task
    task.add_done_callback(lambda t: _pending_deliveries.pop(tag, None) if _pending_deliveries.get(tag) is t else None)
    return task


async def _async_deliver(hass: HomeAssistant, recipients: list[str], message: str, title: str, tag: str) -> None:
    """Send to every recipient; the sidebar gets the message only when none of them took it."""
    sent_any = False
    for entity_id in recipients:
        try:
            async with asyncio.timeout(NOTIFY_TIMEOUT_S):
                await _async_notify(hass, entity_id, message, title, tag)
            sent_any = True
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Failed to send mold notification to %s: %s", entity_id, repr(err))
    if not sent_any:
        async_create(hass, message, title=title, notification_id=tag)


async def _async_notify(hass: HomeAssistant, target: str, message: str, title: str, tag: str) -> None:
    """Send to a notify entity, or to a legacy notify service of that name.

    ``notify.send_message`` accepts only message and title and rejects ``data``
    (#502); a legacy service such as ``notify.mobile_app_<phone>`` has no state.
    An unavailable entity is skipped by HA without an error, so it counts as
    failed here. Only the Companion app's services get ``data`` (tag and group,
    the app replaces the room's older alert).
    """
    state = hass.states.get(target)
    if state is not None:
        if state.state == "unavailable":
            raise ValueError("notify entity is unavailable")
        await hass.services.async_call(
            "notify", "send_message", {"entity_id": target, "message": message, "title": title}, blocking=True
        )
        return
    domain, _, service = target.partition(".")
    if domain != "notify" or not hass.services.has_service("notify", service):
        raise ValueError("no notify entity or service with this name")
    data: dict = {"message": message, "title": title}
    if service.startswith("mobile_app_"):
        data["data"] = {"tag": tag, "group": "roommind"}
    await hass.services.async_call("notify", service, data, blocking=True)


def dismiss_mold_notification(
    hass: HomeAssistant,
    area_id: str,
    tag_suffix: str = "risk",
) -> None:
    """Dismiss the persistent mold notification for a room and stop a delivery still running."""
    notification_id = f"{NOTIF_PREFIX}{area_id}_{tag_suffix}"
    pending = _pending_deliveries.pop(notification_id, None)
    if pending is not None and not pending.done():
        pending.cancel()
    async_dismiss(hass, notification_id)
