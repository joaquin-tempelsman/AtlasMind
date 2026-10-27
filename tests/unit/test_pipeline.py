"""Unit tests for pipeline.py."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from atlasmind.bootstrap import run as bootstrap_run
from atlasmind.pipeline import Pipeline
from atlasmind.shared.types import NormalizedItem, RawMessage


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
        patch("atlasmind.pipeline.classify_amendment", new=AsyncMock(
            return_value={"kind": "new"}
        )),
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


# ---------------------------------------------------------------------------
# Batch amendment helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "answer,expected",
    [
        ("yes", True), ("Yes", True), ("y", True), ("yeah", True), ("ok", True),
        ("sí", True), ("si", True), ("dale", True), ("do it", True),
        ("yes please", True), ("correct", True),
        ("no", False), ("nope", False), ("leave it", False), ("cancel", False),
        ("déjalo", False), ("", False), ("maybe later", False),
    ],
)
def test_is_affirmative(answer: str, expected: bool):
    from atlasmind.pipeline import _is_affirmative
    assert _is_affirmative(answer) is expected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pending_items_for_user_flattens_queues(tmp_path: Path):
    """_pending_items_for_user returns one entry per queued item across KBs."""
    bootstrap_run(vault_path=tmp_path)
    p = Pipeline(vault_root=tmp_path, ingest_delay_seconds=3600)
    assert p._pending_items_for_user(1) == []

    with (
        patch("atlasmind.pipeline.normalize", new=AsyncMock(return_value=_normalized("a"))),
        patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
            "kb_slug": "personal-diary", "rationale": "x", "confidence": "high",
        })),
        patch("atlasmind.pipeline.classify_amendment", new=AsyncMock(
            return_value={"kind": "new"}
        )),
    ):
        await p.process(_raw(text="a"), thread_id="t-a")
        await p.process(_raw(text="b"), thread_id="t-b")

    pending = p._pending_items_for_user(1)
    assert len(pending) == 2
    kb_slug, idx, item = pending[0]
    assert kb_slug == "personal-diary"
    assert idx == 0
    assert hasattr(item, "text")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_amendment_reject_keeps_text_and_keeps_batch_pending(tmp_path: Path):
    """A negative reply leaves the queued text unchanged and the batch still pending."""
    bootstrap_run(vault_path=tmp_path)
    with (
        patch("atlasmind.pipeline.normalize", new=AsyncMock(return_value=_normalized("Pablou"))),
        patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
            "kb_slug": "personal-diary", "rationale": "x", "confidence": "high",
        })),
    ):
        p = Pipeline(vault_root=tmp_path, ingest_delay_seconds=3600)
        await p.process(_raw(text="Pablou"), thread_id="t-x")
        with patch("atlasmind.pipeline.classify_amendment", new=AsyncMock(return_value={
            "kind": "modification", "target_index": 0,
            "new_text": "Pablo", "rationale": "typo",
        })):
            interrupt = await p.process(_raw(text="I meant Pablo"), thread_id="t-x")
        assert "interrupt_question" in interrupt

        result = await p.resume(thread_id="t-x", answer="no", user_id=1)

    assert "reply" in result
    assert p._queues["personal-diary"][0].normalized.text == "Pablou"
    assert "t-x" not in p._pending_amendments


@pytest.mark.unit
@pytest.mark.asyncio
async def test_text_message_does_not_create_link_fetcher(tmp_path: Path):
    """The default LinkFetcher is only constructed when a link message arrives."""
    bootstrap_run(vault_path=tmp_path)
    with (
        patch("atlasmind.pipeline.ReadabilityLinkFetcher") as fetcher_cls,
        patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
            "kb_slug": "personal-diary", "rationale": "x", "confidence": "high",
        })),
    ):
        p = Pipeline(vault_root=tmp_path, ingest_delay_seconds=3600)
        await p.process(_raw(text="hello"), thread_id="t-nofetch")

    fetcher_cls.assert_not_called()
    assert p.link_fetcher is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_link_message_creates_default_fetcher_once(tmp_path: Path):
    """The first link builds a ReadabilityLinkFetcher; later links reuse it."""
    bootstrap_run(vault_path=tmp_path)
    fake = AsyncMock()
    fake.fetch.return_value = ("Title\n\nBody", {"url": "u", "title": "Title"})
    url = "https://example.com/a"
    raw = RawMessage(
        telegram_user_id=1, chat_id=1,
        received_at=datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc),
        kind="link", text=url, url=url,
    )
    with (
        patch("atlasmind.pipeline.ReadabilityLinkFetcher", return_value=fake) as fetcher_cls,
        patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
            "kb_slug": "econ-politics", "rationale": "x", "confidence": "high",
        })),
        patch("atlasmind.pipeline.classify_amendment", new=AsyncMock(
            return_value={"kind": "new"}
        )),
    ):
        p = Pipeline(vault_root=tmp_path, ingest_delay_seconds=3600)
        await p.process(raw, thread_id="t-l1")
        await p.process(raw, thread_id="t-l2")

    fetcher_cls.assert_called_once()
    assert fake.fetch.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_link_fetch_error_message_includes_reason(tmp_path: Path):
    """The error reply names the URL and the fetcher's reason."""
    from atlasmind.ingestion.link_fetcher import LinkFetchError

    bootstrap_run(vault_path=tmp_path)
    fake = AsyncMock()
    fake.fetch.side_effect = LinkFetchError("HTTP 500 fetching u")
    url = "https://example.com/b"
    raw = RawMessage(
        telegram_user_id=1, chat_id=1,
        received_at=datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc),
        kind="link", text=url, url=url,
    )
    p = Pipeline(vault_root=tmp_path, ingest_delay_seconds=3600, link_fetcher=fake)
    result = await p.process(raw, thread_id="t-l3")

    assert result == {"error": f"Couldn't fetch {url}: HTTP 500 fetching u"}


def _paused_pipeline(tmp_path: Path, **kwargs) -> Pipeline:
    """A pipeline with one personal-diary batch paused on an ingest HITL question."""
    p = Pipeline(vault_root=tmp_path, ingest_delay_seconds=0.05, **kwargs)
    p._pending_ingest["1:personal-diary"] = ("personal-diary", 1, [])
    return p


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_interrupt_falls_back_to_reply_fn(tmp_path: Path):
    """Without interrupt_fn, the question is still delivered through reply_fn."""
    bootstrap_run(vault_path=tmp_path)
    replies: list = []

    async def fake_reply(user_id: int, text: str) -> None:
        replies.append((user_id, text))

    async def fake_ingest(items, vault_root, thread_id, model=None):
        return {"interrupt_question": "Which Ro?"}

    with (
        patch("atlasmind.pipeline.normalize", new=AsyncMock(return_value=_normalized())),
        patch("atlasmind.pipeline.route", new=AsyncMock(return_value={
            "kb_slug": "personal-diary", "rationale": "x", "confidence": "high",
        })),
        patch("atlasmind.pipeline.ingest", new=fake_ingest),
    ):
        p = Pipeline(vault_root=tmp_path, ingest_delay_seconds=0.05, reply_fn=fake_reply)
        await p.process(_raw(user_id=1), thread_id="1")
        await asyncio.sleep(0.2)

    assert replies == [(1, "Which Ro?")]
    assert "1:personal-diary" in p._pending_ingest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resume_ingest_commit_failure_returns_error(tmp_path: Path):
    """If the post-resume commit fails, the user gets the commit error, not the summary."""
    bootstrap_run(vault_path=tmp_path)
    p = _paused_pipeline(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("push rejected")

    with (
        patch("atlasmind.pipeline.resume_ingest", new=AsyncMock(return_value={"summary": "ok"})),
        patch("atlasmind.pipeline._vault_commit", new=boom),
    ):
        result = await p.resume(thread_id="1:personal-diary", answer="yes", user_id=1)

    assert result == {"error": "Ingested but vault commit failed: push rejected"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resume_ingest_exception_unpauses_kb_and_flushes_queue(tmp_path: Path):
    """A failed resume clears the pause so items queued meanwhile still ingest."""
    bootstrap_run(vault_path=tmp_path)
    p = _paused_pipeline(tmp_path)
    called: list = []

    async def fake_ingest(items, vault_root, thread_id, model=None):
        called.append(items)
        return {"summary": "done"}

    from atlasmind.shared.types import RoutedItem
    p._queues["personal-diary"] = [RoutedItem(
        normalized=_normalized("queued during pause"), kb_slug="personal-diary",
        routing_rationale="x", confidence="high",
    )]

    with (
        patch("atlasmind.pipeline.resume_ingest", new=AsyncMock(side_effect=RuntimeError("x"))),
        patch("atlasmind.pipeline.ingest", new=fake_ingest),
        patch("atlasmind.pipeline._vault_commit", new=lambda *a, **k: None),
    ):
        result = await p.resume(thread_id="1:personal-diary", answer="yes", user_id=1)
        await asyncio.sleep(0.2)

    assert "error" in result
    assert "1:personal-diary" not in p._pending_ingest
    assert len(called) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_repeated_ingest_interrupt_keeps_batch_paused(tmp_path: Path):
    """A second ask_user during resume keeps the same batch paused for the next answer."""
    bootstrap_run(vault_path=tmp_path)
    p = _paused_pipeline(tmp_path)

    with patch("atlasmind.pipeline.resume_ingest", new=AsyncMock(
        return_value={"interrupt_question": "And Sebi?"}
    )):
        result = await p.resume(thread_id="1:personal-diary", answer="yes", user_id=1)

    assert result == {"interrupt_question": "And Sebi?"}
    assert p._pending_ingest["1:personal-diary"] == ("personal-diary", 1, [])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_router_no_decision_returns_error_and_queues_nothing(tmp_path: Path):
    """If the router never commits, the user gets an error and nothing is queued."""
    from atlasmind.agents.router import RouterNoDecisionError

    bootstrap_run(vault_path=tmp_path)
    with (
        patch("atlasmind.pipeline.normalize", new=AsyncMock(return_value=_normalized())),
        patch("atlasmind.pipeline.route", new=AsyncMock(
            side_effect=RouterNoDecisionError("Router finished without choosing a KB")
        )),
    ):
        p = Pipeline(vault_root=tmp_path, ingest_delay_seconds=3600)
        result = await p.process(_raw(text="Went to the dentist"), thread_id="t-nd")

    assert result == {"error": "Routing failed: Router finished without choosing a KB"}
    assert p._queues == {}
