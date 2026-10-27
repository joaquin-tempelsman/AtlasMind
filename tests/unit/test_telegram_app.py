"""Unit tests for edge/telegram_app.py wiring."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from atlasmind.edge import session
from atlasmind.edge.telegram_app import _make_interrupt_fn


@pytest.mark.unit
@pytest.mark.asyncio
async def test_interrupt_fn_marks_session_expecting_answer():
    """An ingest-time question flips the session so the reply resumes the ingest thread."""
    app = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
    session.drop(99)

    await _make_interrupt_fn(app)(99, "99:personal-diary", "Which Ro?")

    active = session.get(99)
    assert active["expecting"] == "answer"
    assert active["thread_id"] == "99:personal-diary"
    app.bot.send_message.assert_awaited_once_with(chat_id=99, text="Which Ro?")
    session.drop(99)
