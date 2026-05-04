"""Contract tests for pipeline.py — cross-layer boundary assertions.

These test the shape of what pipeline.process() and pipeline.resume() return,
and verify that the IngestQueue fires the KB ingestion agent after batching.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from atlasmind.bootstrap import run as bootstrap_run
from atlasmind.pipeline import Pipeline
from atlasmind.shared.types import NormalizedItem, RawMessage, RoutedItem


def _raw(kind: str = "text", text: str = "Test message.", user_id: int = 1) -> RawMessage:
    return RawMessage(
        telegram_user_id=user_id,
        chat_id=user_id,
        received_at=datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc),
        kind=kind,
        text=text,
    )


def _routed(text: str = "Test.", kb_slug: str = "personal-diary") -> RoutedItem:
    return RoutedItem(
        normalized=NormalizedItem(
            received_at=datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc),
            text=text,
            source_kind="text",
            source_meta={},
            telegram_user_id=1,
        ),
        kb_slug=kb_slug,
        routing_rationale="Test.",
        confidence="high",
    )


@pytest.mark.contract
@pytest.mark.asyncio
async def test_process_returns_reply_shape(tmp_path: Path):
    """pipeline.process() returns {"reply": str} on successful route + queue."""
    bootstrap_run(vault_path=tmp_path)

    routed = _routed()
    with (
        patch("atlasmind.pipeline.normalize", new=AsyncMock(
            return_value=routed.normalized
        )),
        patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
            "kb_slug": "personal-diary",
            "rationale": "Test.",
            "confidence": "high",
        })),
    ):
        pipeline = Pipeline(vault_root=tmp_path, ingest_delay_seconds=3600)
        result = await pipeline.process(_raw(), thread_id="t-1")

    assert "reply" in result
    assert isinstance(result["reply"], str)
    assert "personal-diary" in result["reply"].lower() or "diary" in result["reply"].lower()


@pytest.mark.contract
@pytest.mark.asyncio
async def test_process_returns_interrupt_question_shape(tmp_path: Path):
    """pipeline.process() returns {"interrupt_question": str} when router interrupts."""
    bootstrap_run(vault_path=tmp_path)

    with (
        patch("atlasmind.pipeline.normalize", new=AsyncMock(
            return_value=_routed().normalized
        )),
        patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
            "interrupt_question": "Is this diary or reflections?",
        })),
    ):
        pipeline = Pipeline(vault_root=tmp_path, ingest_delay_seconds=3600)
        result = await pipeline.process(_raw(), thread_id="t-2")

    assert "interrupt_question" in result
    assert isinstance(result["interrupt_question"], str)


@pytest.mark.contract
@pytest.mark.asyncio
async def test_resume_returns_reply_after_route_interrupt(tmp_path: Path):
    """pipeline.resume() returns {"reply": str} after a router HITL is answered."""
    bootstrap_run(vault_path=tmp_path)

    with (
        patch("atlasmind.pipeline.normalize", new=AsyncMock(
            return_value=_routed().normalized
        )),
        patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
            "interrupt_question": "Which KB?",
        })),
    ):
        pipeline = Pipeline(vault_root=tmp_path, ingest_delay_seconds=3600)
        await pipeline.process(_raw(), thread_id="t-3")

    with patch("atlasmind.pipeline.resume_route", new=AsyncMock(return_value={
        "kb_slug": "personal-diary",
        "rationale": "User said diary.",
        "confidence": "high",
    })):
        result = await pipeline.resume(thread_id="t-3", answer="personal-diary", user_id=1)

    assert "reply" in result


@pytest.mark.contract
@pytest.mark.asyncio
async def test_ingest_queue_fires_after_delay(tmp_path: Path):
    """After the debounce timer fires, the KB ingestion agent is invoked with queued items."""
    bootstrap_run(vault_path=tmp_path)

    ingested: list[list] = []

    async def fake_ingest(items, vault_root, thread_id, model=None):
        ingested.append(list(items))
        return {"summary": "Ingested."}

    reply_calls: list[tuple] = []

    async def fake_reply(user_id: int, text: str) -> None:
        reply_calls.append((user_id, text))

    with (
        patch("atlasmind.pipeline.normalize", new=AsyncMock(
            return_value=_routed().normalized
        )),
        patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
            "kb_slug": "personal-diary",
            "rationale": "Test.",
            "confidence": "high",
        })),
        patch("atlasmind.pipeline.ingest", new=fake_ingest),
    ):
        pipeline = Pipeline(vault_root=tmp_path, ingest_delay_seconds=0.05, reply_fn=fake_reply)
        await pipeline.process(_raw(user_id=1), thread_id="t-4")
        # Wait for the debounce timer to fire
        await asyncio.sleep(0.2)

    assert len(ingested) == 1
    assert len(ingested[0]) == 1
    assert ingested[0][0].kb_slug == "personal-diary"
    # reply_fn should have been called with the summary
    assert any("ingested" in text.lower() or "diary" in text.lower() for _, text in reply_calls)


@pytest.mark.contract
@pytest.mark.asyncio
async def test_ingest_queue_batches_multiple_items(tmp_path: Path):
    """Two items routed to the same KB within the delay window are batched in one agent call."""
    bootstrap_run(vault_path=tmp_path)

    ingested: list[list] = []

    async def fake_ingest(items, vault_root, thread_id, model=None):
        ingested.append(list(items))
        return {"summary": "Ingested 2."}

    with (
        patch("atlasmind.pipeline.normalize", new=AsyncMock(
            return_value=_routed().normalized
        )),
        patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
            "kb_slug": "personal-diary",
            "rationale": "Test.",
            "confidence": "high",
        })),
        patch("atlasmind.pipeline.ingest", new=fake_ingest),
    ):
        pipeline = Pipeline(vault_root=tmp_path, ingest_delay_seconds=0.1)
        await pipeline.process(_raw(text="Msg 1", user_id=1), thread_id="t-5a")
        await pipeline.process(_raw(text="Msg 2", user_id=1), thread_id="t-5b")
        await asyncio.sleep(0.4)

    assert len(ingested) == 1, f"Expected 1 batch, got {len(ingested)}"
    assert len(ingested[0]) == 2
