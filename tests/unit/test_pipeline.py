"""Unit tests for pipeline.py."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from atlasmind.bootstrap import run as bootstrap_run
from atlasmind.pipeline import Pipeline
from atlasmind.shared.types import NormalizedItem, RawMessage, RoutedItem


def _raw(kind: str = "text", text: str = "Hi", user_id: int = 1) -> RawMessage:
    return RawMessage(
        telegram_user_id=user_id,
        chat_id=user_id,
        received_at=datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc),
        kind=kind,
        text=text,
    )


def _normalized(text: str = "Hi") -> NormalizedItem:
    return NormalizedItem(
        received_at=datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc),
        text=text,
        source_kind="text",
        source_meta={},
        telegram_user_id=1,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_reply_shape(tmp_path: Path):
    """process() returns {"reply": str} when routing succeeds."""
    bootstrap_run(vault_path=tmp_path)
    with (
        patch("atlasmind.pipeline.normalize", new=AsyncMock(return_value=_normalized())),
        patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
            "kb_slug": "personal-diary",
            "rationale": "x",
            "confidence": "high",
        })),
    ):
        p = Pipeline(vault_root=tmp_path, ingest_delay_seconds=3600)
        result = await p.process(_raw(), thread_id="t-1")
    assert "reply" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_interrupt_question(tmp_path: Path):
    """process() returns {"interrupt_question"} when router asks a question."""
    bootstrap_run(vault_path=tmp_path)
    with (
        patch("atlasmind.pipeline.normalize", new=AsyncMock(return_value=_normalized())),
        patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
            "interrupt_question": "Which KB?",
        })),
    ):
        p = Pipeline(vault_root=tmp_path, ingest_delay_seconds=3600)
        result = await p.process(_raw(), thread_id="t-2")
    assert result == {"interrupt_question": "Which KB?"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_normalize_error(tmp_path: Path):
    """process() returns {"error": ...} when normalize raises."""
    bootstrap_run(vault_path=tmp_path)
    with patch("atlasmind.pipeline.normalize", new=AsyncMock(side_effect=RuntimeError("oops"))):
        p = Pipeline(vault_root=tmp_path, ingest_delay_seconds=3600)
        result = await p.process(_raw(), thread_id="t-3")
    assert "error" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resume_no_session_returns_error(tmp_path: Path):
    """resume() with no pending session returns {"error": ...}."""
    bootstrap_run(vault_path=tmp_path)
    p = Pipeline(vault_root=tmp_path, ingest_delay_seconds=3600)
    result = await p.resume(thread_id="unknown", answer="yes", user_id=1)
    assert "error" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resume_after_route_interrupt(tmp_path: Path):
    """resume() after a router interrupt delegates to resume_route and enqueues."""
    bootstrap_run(vault_path=tmp_path)
    with (
        patch("atlasmind.pipeline.normalize", new=AsyncMock(return_value=_normalized())),
        patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
            "interrupt_question": "Which KB?",
        })),
    ):
        p = Pipeline(vault_root=tmp_path, ingest_delay_seconds=3600)
        await p.process(_raw(), thread_id="t-r1")

    with patch("atlasmind.pipeline.resume_route", new=AsyncMock(return_value={
        "kb_slug": "personal-diary",
        "rationale": "User said diary.",
        "confidence": "high",
    })):
        result = await p.resume(thread_id="t-r1", answer="personal-diary", user_id=1)

    assert "reply" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_timer_fires_and_calls_ingest(tmp_path: Path):
    """IngestQueue timer fires ingest() after the delay."""
    bootstrap_run(vault_path=tmp_path)
    called: list = []

    async def fake_ingest(items, vault_root, thread_id, model=None):
        called.append(items)
        return {"summary": "done"}

    with (
        patch("atlasmind.pipeline.normalize", new=AsyncMock(return_value=_normalized())),
        patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
            "kb_slug": "personal-diary",
            "rationale": "x",
            "confidence": "high",
        })),
        patch("atlasmind.pipeline.ingest", new=fake_ingest),
    ):
        p = Pipeline(vault_root=tmp_path, ingest_delay_seconds=0.05)
        await p.process(_raw(user_id=1), thread_id="t-fire")
        await asyncio.sleep(0.2)

    assert len(called) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_timer_reset_on_second_message(tmp_path: Path):
    """Sending a second message resets the debounce timer; only one ingest call fires."""
    bootstrap_run(vault_path=tmp_path)
    called: list = []

    async def fake_ingest(items, vault_root, thread_id, model=None):
        called.append(items)
        return {"summary": "done"}

    with (
        patch("atlasmind.pipeline.normalize", new=AsyncMock(return_value=_normalized())),
        patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
            "kb_slug": "personal-diary",
            "rationale": "x",
            "confidence": "high",
        })),
        patch("atlasmind.pipeline.ingest", new=fake_ingest),
    ):
        p = Pipeline(vault_root=tmp_path, ingest_delay_seconds=0.1)
        await p.process(_raw(text="a"), thread_id="t-a")
        await asyncio.sleep(0.06)
        await p.process(_raw(text="b"), thread_id="t-b")
        await asyncio.sleep(0.3)

    assert len(called) == 1
    assert len(called[0]) == 2


@pytest.mark.unit
def test_is_url_detection():
    from atlasmind.edge.handlers import _is_url
    assert _is_url("https://example.com")
    assert _is_url("http://foo.bar/baz")
    assert not _is_url("just some text")
    assert not _is_url("https://foo.com has more text")
