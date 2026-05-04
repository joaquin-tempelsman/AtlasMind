"""Unit tests for vault/frontmatter.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from atlasmind.vault.frontmatter import (
    format_kb_log_entry,
    format_routing_log_entry,
    parse,
    parse_log_entries,
    parse_routing_log_entries,
    serialize,
    write_file,
    parse_file,
)


@pytest.mark.unit
def test_parse_extracts_metadata_and_body():
    text = "---\ntype: note\nkb: reflections\n---\n\n# Title\n\nBody text."
    meta, body = parse(text)
    assert meta["type"] == "note"
    assert meta["kb"] == "reflections"
    assert "Title" in body


@pytest.mark.unit
def test_serialize_roundtrip():
    meta = {"type": "note", "kb": "reflections", "date": "2026-05-02"}
    body = "# My Note\n\nSome content."
    serialized = serialize(meta, body)
    parsed_meta, parsed_body = parse(serialized)
    assert parsed_meta["type"] == "note"
    assert parsed_meta["kb"] == "reflections"
    assert "My Note" in parsed_body


@pytest.mark.unit
def test_parse_no_frontmatter():
    text = "# Just a body\n\nNo frontmatter here."
    meta, body = parse(text)
    assert meta == {}
    assert "body" in body.lower() or "Just" in body


@pytest.mark.unit
def test_write_and_parse_file_roundtrip(tmp_path: Path):
    path = tmp_path / "test.md"
    meta = {"type": "kb_agent_md", "kb_slug": "test-kb", "version": 1}
    body = "# Test KB\n\nContent here."
    write_file(path, meta, body)
    assert path.exists()
    loaded_meta, loaded_body = parse_file(path)
    assert loaded_meta["type"] == "kb_agent_md"
    assert loaded_meta["kb_slug"] == "test-kb"
    assert "Content" in loaded_body


@pytest.mark.unit
def test_parse_log_entries_finds_headers():
    text = (
        "# Log\n\n"
        "## [2026-05-02T14:00:00Z] ingest | note-slug\n"
        "**Note:** [[some/path]]\n"
        "\n"
        "## [2026-05-02T15:00:00Z] ingest | another-slug\n"
        "**Note:** [[another/path]]\n"
    )
    entries = parse_log_entries(text)
    assert len(entries) == 2
    assert entries[0]["kind"] == "ingest"
    assert entries[0]["rest"] == "note-slug"
    assert entries[1]["timestamp"] == "2026-05-02T15:00:00Z"


@pytest.mark.unit
def test_parse_log_entries_skips_malformed():
    text = "## [bad entry\nsome content\n## [2026-01-01T00:00:00Z] ingest | ok\n"
    entries = parse_log_entries(text)
    assert len(entries) == 1
    assert entries[0]["rest"] == "ok"


@pytest.mark.unit
def test_format_routing_log_entry():
    entry = format_routing_log_entry(
        ts="2026-05-02T14:25:03Z",
        kb_slug="personal-diary",
        confidence="high",
        source="voice (whisper)",
        preview="Met Mateo at Tortoni...",
        rationale="Real-world encounter with a named friend.",
        file_path="personal-diary/notes/2026-05-02-coffee.md",
    )
    assert "## [2026-05-02T14:25:03Z] route | personal-diary | high" in entry
    assert "**Source:** voice (whisper)" in entry
    assert "**Rationale:** Real-world encounter" in entry


@pytest.mark.unit
def test_format_kb_log_entry():
    entry = format_kb_log_entry(
        ts="2026-05-02T14:25:03Z",
        note_slug="coffee-with-mateo",
        note_path="personal-diary/notes/2026-05-02-coffee-with-mateo.md",
        pages_updated=["personal-diary/people/mateo.md"],
        summary="Met Mateo at Tortoni.",
    )
    assert "## [2026-05-02T14:25:03Z] ingest | coffee-with-mateo" in entry
    assert "personal-diary/people/mateo.md" in entry
