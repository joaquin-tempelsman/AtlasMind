"""Unit tests for ingestion/normalize.py — all I/O mocked."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from atlasmind.ingestion.link_fetcher import LinkFetchError
from atlasmind.ingestion.normalize import normalize
from atlasmind.shared.types import RawMessage

_NOW = datetime(2026, 5, 2, 14, 25, 3, tzinfo=timezone.utc)


def _raw(**kwargs) -> RawMessage:
    defaults = dict(telegram_user_id=1, chat_id=1, received_at=_NOW, kind="text")
    defaults.update(kwargs)
    return RawMessage(**defaults)


@pytest.mark.unit
async def test_normalize_text():
    raw = _raw(kind="text", text="  Hello world  ")
    item = await normalize(raw)
    assert item.text == "Hello world"
    assert item.source_kind == "text"
    assert item.source_meta == {}
    assert item.telegram_user_id == 1
    assert item.received_at == _NOW


@pytest.mark.unit
async def test_normalize_voice():
    raw = _raw(kind="voice", text="transcribed text", voice_file_id="file123")
    item = await normalize(raw)
    assert item.text == "transcribed text"
    assert item.source_kind == "voice"
    assert item.source_meta["voice_file_id"] == "file123"


@pytest.mark.unit
async def test_normalize_link_calls_fetcher(tmp_path: Path):
    raw = _raw(kind="link", url="https://example.com/article")
    fetcher = AsyncMock()
    fetcher.fetch.return_value = (
        "Article Title\n\nArticle body text.",
        {"url": "https://example.com/article", "title": "Article Title", "fetched_at": "2026-05-02T14:25:03Z"},
    )
    item = await normalize(raw, link_fetcher=fetcher, vault_root=tmp_path)
    assert item.text.startswith("Article Title")
    assert item.source_kind == "link"
    assert item.source_meta["url"] == "https://example.com/article"
    assert item.source_meta["title"] == "Article Title"
    fetcher.fetch.assert_awaited_once_with("https://example.com/article")


@pytest.mark.unit
async def test_normalize_link_persists_html(tmp_path: Path):
    raw = _raw(kind="link", url="https://example.com")
    fetcher = AsyncMock()
    fetcher.fetch.return_value = (
        "Content",
        {"url": "https://example.com", "title": "Example", "fetched_at": "2026-05-02T14:25:03Z"},
    )
    item = await normalize(raw, link_fetcher=fetcher, vault_root=tmp_path)
    assert "html_path" in item.source_meta
    html_path = tmp_path / item.source_meta["html_path"]
    assert html_path.exists()


@pytest.mark.unit
async def test_normalize_link_raises_on_fetch_error():
    raw = _raw(kind="link", url="https://bad-url.example")
    fetcher = AsyncMock()
    fetcher.fetch.side_effect = LinkFetchError("HTTP 404 fetching url")
    with pytest.raises(LinkFetchError):
        await normalize(raw, link_fetcher=fetcher)


@pytest.mark.unit
async def test_normalize_link_requires_fetcher():
    raw = _raw(kind="link", url="https://example.com")
    with pytest.raises(ValueError, match="link_fetcher"):
        await normalize(raw)


@pytest.mark.unit
async def test_normalize_unknown_kind():
    raw = _raw(kind="text")
    raw.kind = "unknown"  # type: ignore[assignment]
    with pytest.raises(ValueError, match="Unknown"):
        await normalize(raw)
