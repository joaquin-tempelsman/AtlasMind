"""Unit tests for ingestion/normalize.py — all I/O mocked."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

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
    # text is short repr — full article stored in source_meta["raw_article_text"]
    assert "[Link]" in item.text
    assert "Article Title" in item.text
    assert item.source_kind == "link"
    assert item.source_meta["url"] == "https://example.com/article"
    assert item.source_meta["title"] == "Article Title"
    assert item.source_meta["raw_article_text"] == "Article Title\n\nArticle body text."
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


@pytest.mark.unit
async def test_normalize_link_short_repr_no_full_text_in_text():
    """link items: NormalizedItem.text is short repr, not full article."""
    raw = _raw(kind="link", url="https://ft.com/article")
    fetcher = AsyncMock()
    fetcher.fetch.return_value = (
        "Full article text that is very long...",
        {"url": "https://ft.com/article", "title": "FT: Argentina deal", "fetched_at": "2026-05-02T14:25:03Z"},
    )
    item = await normalize(raw, link_fetcher=fetcher)
    assert item.text == "[Link] FT: Argentina deal\nURL: https://ft.com/article"
    assert item.source_meta["raw_article_text"] == "Full article text that is very long..."


@pytest.mark.unit
async def test_normalize_link_short_repr_no_title():
    """link items without title fall back to url-only short repr."""
    raw = _raw(kind="link", url="https://example.com")
    fetcher = AsyncMock()
    fetcher.fetch.return_value = (
        "Some text.",
        {"url": "https://example.com", "fetched_at": "2026-05-02T14:25:03Z"},
    )
    item = await normalize(raw, link_fetcher=fetcher)
    assert item.text == "[Link] https://example.com"


@pytest.mark.unit
async def test_normalize_voice_with_linked_url():
    """voice + linked_url: linked_url stored in source_meta."""
    raw = _raw(kind="voice", text="My commentary", voice_file_id="abc",
               linked_url="https://cenital.com/article")
    item = await normalize(raw)
    assert item.text == "My commentary"
    assert item.source_meta["voice_file_id"] == "abc"
    assert item.source_meta["linked_url"] == "https://cenital.com/article"


@pytest.mark.unit
async def test_normalize_voice_without_linked_url():
    """voice without linked_url: source_meta has no linked_url key."""
    raw = _raw(kind="voice", text="Just a note", voice_file_id="xyz")
    item = await normalize(raw)
    assert "linked_url" not in item.source_meta


@pytest.mark.unit
async def test_normalize_text_with_linked_url():
    """text + linked_url: linked_url stored in source_meta."""
    raw = _raw(kind="text", text="Interesting take", linked_url="https://cnn.com/piece")
    item = await normalize(raw)
    assert item.text == "Interesting take"
    assert item.source_meta["linked_url"] == "https://cnn.com/piece"


@pytest.mark.unit
async def test_normalize_text_without_linked_url():
    """text without linked_url: source_meta is empty (no capture without vault_root)."""
    raw = _raw(kind="text", text="Plain text")
    item = await normalize(raw)
    assert item.source_meta == {}


# ── raw capture ────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_normalize_no_capture_without_vault_root():
    """No raw_capture_path when vault_root is None."""
    raw = _raw(kind="text", text="Hola mundo")
    item = await normalize(raw)
    assert "raw_capture_path" not in item.source_meta


@pytest.mark.unit
async def test_normalize_text_capture_is_verbatim(tmp_path: Path):
    """The capture file body equals the input text byte-for-byte (untranslated)."""
    raw = _raw(kind="text", text="  Hola, ¿qué tal?  ")
    item = await normalize(raw, vault_root=tmp_path)
    rel = item.source_meta["raw_capture_path"]
    saved = (tmp_path / rel).read_text(encoding="utf-8")
    # frontmatter + verbatim original (not the stripped NormalizedItem.text)
    assert saved.endswith("\n\n  Hola, ¿qué tal?  ")
    assert "type: raw_capture" in saved
    # NormalizedItem.text is still the stripped canonical text
    assert item.text == "Hola, ¿qué tal?"


@pytest.mark.unit
async def test_normalize_voice_capture(tmp_path: Path):
    """Voice transcript is captured with source_kind=voice."""
    raw = _raw(kind="voice", text="transcripción", voice_file_id="f1")
    item = await normalize(raw, vault_root=tmp_path)
    rel = item.source_meta["raw_capture_path"]
    saved = (tmp_path / rel).read_text(encoding="utf-8")
    assert "source_kind: voice" in saved
    assert saved.endswith("transcripción")


@pytest.mark.unit
async def test_normalize_empty_text_no_capture(tmp_path: Path):
    """Whitespace-only text writes no capture file."""
    raw = _raw(kind="text", text="   ")
    item = await normalize(raw, vault_root=tmp_path)
    assert "raw_capture_path" not in item.source_meta
    assert not (tmp_path / "raw" / "captures").exists() or not any(
        (tmp_path / "raw" / "captures").glob("*.md")
    )
