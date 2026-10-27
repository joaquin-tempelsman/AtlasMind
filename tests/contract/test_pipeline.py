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
        # Stub the real git commit so this test isolates the queue→ingest→reply
        # contract from git I/O timing (a real pull/commit/push can outlive the
        # post-fire sleep window).
        patch("atlasmind.pipeline._vault_commit", new=lambda *a, **k: None),
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
        # Message 2 lands while message 1 is pending, so it now passes through the
        # amendment classifier. Force "new" so both items batch (no real API call).
        patch("atlasmind.pipeline.classify_amendment", new=AsyncMock(
            return_value={"kind": "new"}
        )),
    ):
        pipeline = Pipeline(vault_root=tmp_path, ingest_delay_seconds=0.1)
        await pipeline.process(_raw(text="Msg 1", user_id=1), thread_id="t-5a")
        await pipeline.process(_raw(text="Msg 2", user_id=1), thread_id="t-5b")
        await asyncio.sleep(0.4)

    assert len(ingested) == 1, f"Expected 1 batch, got {len(ingested)}"
    assert len(ingested[0]) == 2


@pytest.mark.contract
@pytest.mark.asyncio
async def test_amendment_modification_interrupts_and_does_not_enqueue(tmp_path: Path):
    """A message classified as a modification proposes a change and is NOT enqueued."""
    bootstrap_run(vault_path=tmp_path)

    with (
        patch("atlasmind.pipeline.normalize", new=AsyncMock(
            return_value=_routed(text="Met Pablou.").normalized
        )),
        patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
            "kb_slug": "personal-diary",
            "rationale": "Test.",
            "confidence": "high",
        })),
    ):
        pipeline = Pipeline(vault_root=tmp_path, ingest_delay_seconds=3600)
        # First message — routes and enqueues normally (no pending batch yet).
        first = await pipeline.process(_raw(text="Met Pablou.", user_id=1), thread_id="t-am1")
        assert "reply" in first
        assert len(pipeline._queues["personal-diary"]) == 1

        # Second message — classifier says it corrects item 0.
        with patch("atlasmind.pipeline.classify_amendment", new=AsyncMock(return_value={
            "kind": "modification",
            "target_index": 0,
            "new_text": "Met Pablo.",
            "rationale": "typo",
        })):
            second = await pipeline.process(
                _raw(text="I meant Pablo.", user_id=1), thread_id="t-am1"
            )

    assert "interrupt_question" in second
    # Still one queued item, text unchanged until the user accepts.
    assert len(pipeline._queues["personal-diary"]) == 1
    assert pipeline._queues["personal-diary"][0].normalized.text == "Met Pablou."


@pytest.mark.contract
@pytest.mark.asyncio
async def test_amendment_accept_rewrites_queued_text(tmp_path: Path):
    """Replying yes to a proposed amendment rewrites the queued item's text."""
    bootstrap_run(vault_path=tmp_path)

    with (
        patch("atlasmind.pipeline.normalize", new=AsyncMock(
            return_value=_routed(text="Met Pablou.").normalized
        )),
        patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
            "kb_slug": "personal-diary",
            "rationale": "Test.",
            "confidence": "high",
        })),
    ):
        pipeline = Pipeline(vault_root=tmp_path, ingest_delay_seconds=3600)
        await pipeline.process(_raw(text="Met Pablou.", user_id=1), thread_id="t-am2")
        with patch("atlasmind.pipeline.classify_amendment", new=AsyncMock(return_value={
            "kind": "modification",
            "target_index": 0,
            "new_text": "Met Pablo.",
            "rationale": "typo",
        })):
            await pipeline.process(_raw(text="I meant Pablo.", user_id=1), thread_id="t-am2")

        result = await pipeline.resume(thread_id="t-am2", answer="yes", user_id=1)

    assert "reply" in result
    assert pipeline._queues["personal-diary"][0].normalized.text == "Met Pablo."


@pytest.mark.contract
@pytest.mark.asyncio
async def test_amendment_reject_leaves_batch_unchanged(tmp_path: Path):
    """Replying no to a proposed amendment leaves the queued item untouched."""
    bootstrap_run(vault_path=tmp_path)

    with (
        patch("atlasmind.pipeline.normalize", new=AsyncMock(
            return_value=_routed(text="Met Pablou.").normalized
        )),
        patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
            "kb_slug": "personal-diary",
            "rationale": "Test.",
            "confidence": "high",
        })),
    ):
        pipeline = Pipeline(vault_root=tmp_path, ingest_delay_seconds=3600)
        await pipeline.process(_raw(text="Met Pablou.", user_id=1), thread_id="t-am3")
        with patch("atlasmind.pipeline.classify_amendment", new=AsyncMock(return_value={
            "kind": "modification",
            "target_index": 0,
            "new_text": "Met Pablo.",
            "rationale": "typo",
        })):
            await pipeline.process(_raw(text="I meant Pablo.", user_id=1), thread_id="t-am3")

        result = await pipeline.resume(thread_id="t-am3", answer="no", user_id=1)

    assert "reply" in result
    assert pipeline._queues["personal-diary"][0].normalized.text == "Met Pablou."


class _FakeLinkFetcher:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[str] = []

    async def fetch(self, url: str) -> tuple[str, dict]:
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        return "Inflation explained\n\nBody text.", {"url": url, "title": "Inflation explained"}


@pytest.mark.contract
@pytest.mark.asyncio
async def test_process_link_message_is_normalized_and_routed(tmp_path: Path):
    """A kind="link" RawMessage is fetched via the pipeline's LinkFetcher and routed."""
    bootstrap_run(vault_path=tmp_path)
    fetcher = _FakeLinkFetcher()
    url = "https://example.com/inflation"
    raw = RawMessage(
        telegram_user_id=1, chat_id=1,
        received_at=datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc),
        kind="link", text=url, url=url,
    )

    with patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
        "kb_slug": "econ-politics", "rationale": "Article.", "confidence": "high",
    })):
        pipeline = Pipeline(vault_root=tmp_path, ingest_delay_seconds=3600, link_fetcher=fetcher)
        result = await pipeline.process(raw, thread_id="t-link")

    assert "reply" in result
    assert fetcher.calls == [url]
    queued = pipeline._queues["econ-politics"][0].normalized
    assert queued.source_kind == "link"
    assert queued.source_meta["url"] == url


@pytest.mark.contract
@pytest.mark.asyncio
async def test_process_link_fetch_error_returns_error_and_queues_nothing(tmp_path: Path):
    """LinkFetchError surfaces as {"error": "Couldn't fetch <url>..."}; nothing is queued."""
    from atlasmind.ingestion.link_fetcher import LinkFetchError

    bootstrap_run(vault_path=tmp_path)
    url = "https://example.com/missing"
    raw = RawMessage(
        telegram_user_id=1, chat_id=1,
        received_at=datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc),
        kind="link", text=url, url=url,
    )
    pipeline = Pipeline(
        vault_root=tmp_path, ingest_delay_seconds=3600,
        link_fetcher=_FakeLinkFetcher(LinkFetchError("HTTP 404")),
    )
    result = await pipeline.process(raw, thread_id="t-link-err")

    assert result["error"].startswith(f"Couldn't fetch {url}")
    assert pipeline._queues == {}


async def _pause_ingest(tmp_path: Path, commits: list, interrupts: list, ingested: list):
    """Build a pipeline whose first ingest run pauses on an ask_user question."""

    async def fake_ingest(items, vault_root, thread_id, model=None):
        ingested.append(list(items))
        return {"interrupt_question": "Is Ro the same person as people/ro.md?"}

    async def fake_interrupt(user_id: int, thread_id: str, question: str) -> None:
        interrupts.append((user_id, thread_id, question))

    pipeline = Pipeline(
        vault_root=tmp_path, ingest_delay_seconds=0.05, interrupt_fn=fake_interrupt,
    )
    with (
        patch("atlasmind.pipeline.normalize", new=AsyncMock(
            return_value=_routed("Asado with Ro.").normalized
        )),
        patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
            "kb_slug": "personal-diary", "rationale": "Diary.", "confidence": "high",
        })),
        patch("atlasmind.pipeline.ingest", new=fake_ingest),
    ):
        await pipeline.process(_raw(user_id=7), thread_id="7")
        await asyncio.sleep(0.2)
    return pipeline


@pytest.mark.contract
@pytest.mark.asyncio
async def test_ingest_interrupt_is_handed_to_edge_with_resumable_thread(tmp_path: Path):
    """An ingest-time ask_user reaches interrupt_fn with a thread_id that resume() accepts."""
    bootstrap_run(vault_path=tmp_path)
    commits: list = []
    interrupts: list = []
    pipeline = await _pause_ingest(tmp_path, commits, interrupts, [])

    assert len(interrupts) == 1
    user_id, thread_id, question = interrupts[0]
    assert user_id == 7
    assert "Ro" in question

    with (
        patch("atlasmind.pipeline.resume_ingest", new=AsyncMock(
            return_value={"summary": "Filed: asado."}
        )),
        patch("atlasmind.pipeline._vault_commit", new=lambda *a, **k: commits.append(a)),
    ):
        result = await pipeline.resume(thread_id=thread_id, answer="yes", user_id=7)

    assert result == {"reply": "Filed: asado."}


@pytest.mark.contract
@pytest.mark.asyncio
async def test_resumed_ingest_batch_is_committed(tmp_path: Path):
    """A batch that finishes after a HITL answer is committed exactly like an uninterrupted one."""
    bootstrap_run(vault_path=tmp_path)
    commits: list = []
    interrupts: list = []
    pipeline = await _pause_ingest(tmp_path, commits, interrupts, [])
    _, thread_id, _ = interrupts[0]

    with (
        patch("atlasmind.pipeline.resume_ingest", new=AsyncMock(
            return_value={"summary": "Filed: asado."}
        )),
        patch("atlasmind.pipeline._vault_commit", new=lambda *a, **k: commits.append(a)),
    ):
        await pipeline.resume(thread_id=thread_id, answer="yes", user_id=7)

    assert len(commits) == 1
    _vault_root, kb_slug, items = commits[0]
    assert kb_slug == "personal-diary"
    assert [i.normalized.text for i in items] == ["Asado with Ro."]


@pytest.mark.contract
@pytest.mark.asyncio
async def test_paused_kb_defers_new_batch_until_resume(tmp_path: Path):
    """Items queued for a KB paused on HITL wait; they ingest only after the pause resolves."""
    bootstrap_run(vault_path=tmp_path)
    commits: list = []
    interrupts: list = []
    ingested: list = []
    pipeline = await _pause_ingest(tmp_path, commits, interrupts, ingested)
    _, thread_id, _ = interrupts[0]

    async def second_ingest(items, vault_root, thread_id, model=None):
        ingested.append(list(items))
        return {"summary": "Filed second."}

    with (
        patch("atlasmind.pipeline.normalize", new=AsyncMock(
            return_value=_routed("Padel with Sebi.").normalized
        )),
        patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
            "kb_slug": "personal-diary", "rationale": "Diary.", "confidence": "high",
        })),
        patch("atlasmind.pipeline.classify_amendment", new=AsyncMock(
            return_value={"kind": "new"}
        )),
        patch("atlasmind.pipeline.ingest", new=second_ingest),
        patch("atlasmind.pipeline.resume_ingest", new=AsyncMock(
            return_value={"summary": "Filed: asado."}
        )),
        patch("atlasmind.pipeline._vault_commit", new=lambda *a, **k: commits.append(a)),
    ):
        await pipeline.process(_raw(user_id=7), thread_id="7")
        await asyncio.sleep(0.2)
        assert len(ingested) == 1, "a second run started while the KB was paused"

        await pipeline.resume(thread_id=thread_id, answer="yes", user_id=7)
        await asyncio.sleep(0.2)

    assert len(ingested) == 2
    assert [i.normalized.text for i in ingested[1]] == ["Padel with Sebi."]
