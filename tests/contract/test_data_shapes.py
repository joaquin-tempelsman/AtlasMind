"""Contract tests: data shapes (RawMessage, NormalizedItem, RoutedItem, IngestionResult).

These tests assert the field set, types, and that the shapes cross layer boundaries correctly.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from atlasmind.shared.types import IngestionResult, NormalizedItem, RawMessage, RoutedItem


@pytest.mark.contract
class TestRawMessage:
    def test_required_fields(self):
        now = datetime.now(timezone.utc)
        msg = RawMessage(
            telegram_user_id=123,
            chat_id=456,
            received_at=now,
            kind="text",
            text="hello",
        )
        assert msg.telegram_user_id == 123
        assert msg.chat_id == 456
        assert msg.received_at == now
        assert msg.kind == "text"
        assert msg.text == "hello"
        assert msg.voice_file_id is None
        assert msg.url is None
        assert msg.raw_payload == {}

    def test_voice_kind(self):
        msg = RawMessage(
            telegram_user_id=1, chat_id=1,
            received_at=datetime.now(timezone.utc),
            kind="voice",
            voice_file_id="abc123",
        )
        assert msg.kind == "voice"
        assert msg.text is None

    def test_link_kind(self):
        msg = RawMessage(
            telegram_user_id=1, chat_id=1,
            received_at=datetime.now(timezone.utc),
            kind="link",
            url="https://example.com",
        )
        assert msg.kind == "link"
        assert msg.url == "https://example.com"

    def test_linked_url_field_defaults_none(self):
        msg = RawMessage(
            telegram_user_id=1, chat_id=1,
            received_at=datetime.now(timezone.utc),
            kind="voice",
            voice_file_id="xyz",
        )
        assert msg.linked_url is None

    def test_linked_url_set_on_voice(self):
        msg = RawMessage(
            telegram_user_id=1, chat_id=1,
            received_at=datetime.now(timezone.utc),
            kind="voice",
            voice_file_id="xyz",
            linked_url="https://cenital.com/article",
        )
        assert msg.linked_url == "https://cenital.com/article"

    def test_linked_url_set_on_text(self):
        msg = RawMessage(
            telegram_user_id=1, chat_id=1,
            received_at=datetime.now(timezone.utc),
            kind="text",
            text="Great analysis",
            linked_url="https://cnn.com/2026/05/article",
        )
        assert msg.linked_url == "https://cnn.com/2026/05/article"

    def test_is_dataclass(self):
        assert dataclasses.is_dataclass(RawMessage)


@pytest.mark.contract
class TestNormalizedItem:
    def test_required_fields(self):
        now = datetime.now(timezone.utc)
        item = NormalizedItem(
            received_at=now,
            text="extracted text",
            source_kind="text",
            source_meta={},
            telegram_user_id=99,
        )
        assert item.text == "extracted text"
        assert item.source_kind == "text"
        assert item.source_meta == {}
        assert item.telegram_user_id == 99

    def test_link_meta(self):
        item = NormalizedItem(
            received_at=datetime.now(timezone.utc),
            text="title\n\nbody",
            source_kind="link",
            source_meta={"url": "https://x.com", "title": "X", "fetched_at": "2026-01-01T00:00:00Z"},
            telegram_user_id=1,
        )
        assert item.source_meta["url"] == "https://x.com"
        assert item.source_meta["title"] == "X"

    def test_is_dataclass(self):
        assert dataclasses.is_dataclass(NormalizedItem)


@pytest.mark.contract
class TestRoutedItem:
    def test_wraps_normalized(self):
        normalized = NormalizedItem(
            received_at=datetime.now(timezone.utc),
            text="hello",
            source_kind="text",
            source_meta={},
            telegram_user_id=1,
        )
        routed = RoutedItem(
            normalized=normalized,
            kb_slug="personal-diary",
            routing_rationale="Real-world event.",
            confidence="high",
        )
        assert routed.normalized is normalized
        assert routed.kb_slug == "personal-diary"
        assert routed.confidence == "high"

    def test_is_dataclass(self):
        assert dataclasses.is_dataclass(RoutedItem)


@pytest.mark.contract
class TestIngestionResult:
    def test_required_fields(self):
        result = IngestionResult(
            kb_slug="reflections",
            note_path="reflections/notes/2026-05-02-on-status.md",
            pages_touched=["reflections/notes/2026-05-02-on-status.md", "reflections/index.md"],
            commit_message="ingest: on-status (reflections)",
            summary_for_user="Filed note 'On status games'.",
        )
        assert result.kb_slug == "reflections"
        assert len(result.pages_touched) == 2

    def test_is_dataclass(self):
        assert dataclasses.is_dataclass(IngestionResult)
