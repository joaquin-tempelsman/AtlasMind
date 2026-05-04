"""In-memory session table keyed by telegram_user_id.

Each entry tracks whether the user is currently in a HITL flow (expecting
a text answer to an agent question) and which thread_id to resume.
"""
from __future__ import annotations

import time
from typing import Literal

from atlasmind.config import SESSION_TIMEOUT_SECONDS

_sessions: dict[int, dict] = {}


def get(user_id: int) -> dict | None:
    """Return the active session for user_id, or None if absent/expired."""
    entry = _sessions.get(user_id)
    if entry is None:
        return None
    if time.monotonic() - entry["last_active"] > SESSION_TIMEOUT_SECONDS:
        _sessions.pop(user_id, None)
        return None
    return entry


def set_active(
    user_id: int,
    thread_id: str,
    expecting: Literal["answer"] | None = None,
    kb_slug: str | None = None,
) -> None:
    """Create or update a session for user_id."""
    _sessions[user_id] = {
        "thread_id": thread_id,
        "last_active": time.monotonic(),
        "expecting": expecting,
        "kb_slug": kb_slug,
    }


def touch(user_id: int) -> None:
    """Refresh last_active without changing other fields."""
    entry = _sessions.get(user_id)
    if entry is not None:
        entry["last_active"] = time.monotonic()


def drop(user_id: int) -> None:
    """Remove the session for user_id."""
    _sessions.pop(user_id, None)


def clear_all() -> None:
    """Remove all sessions. For test isolation only."""
    _sessions.clear()
