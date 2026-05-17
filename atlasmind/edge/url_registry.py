"""Per-user URL registry for reply-based URL linking.

When a URL message arrives, L0 registers both the user's message_id and the
bot's confirmation message_id so that either can be replied to. 24-hour TTL,
module-level (survives across sessions), separate from the session store.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

_TTL = timedelta(hours=24)

# user_id → {message_id: (url, registered_at)}
_registry: dict[int, dict[int, tuple[str, datetime]]] = defaultdict(dict)


def register(user_id: int, message_id: int, url: str) -> None:
    """Associate message_id with url for user_id."""
    _prune(user_id)
    _registry[user_id][message_id] = (url, datetime.now(timezone.utc))


def lookup(user_id: int, message_id: int) -> str | None:
    """Return the URL for message_id, or None if not found / expired."""
    _prune(user_id)
    entry = _registry[user_id].get(message_id)
    return entry[0] if entry else None


def clear_user(user_id: int) -> None:
    """Remove all registry entries for user_id. Used in tests."""
    _registry.pop(user_id, None)


def clear_all() -> None:
    """Clear the entire registry. Used in tests."""
    _registry.clear()


def _prune(user_id: int) -> None:
    cutoff = datetime.now(timezone.utc) - _TTL
    _registry[user_id] = {
        mid: (url, ts)
        for mid, (url, ts) in _registry[user_id].items()
        if ts > cutoff
    }
