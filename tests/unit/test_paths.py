"""Unit tests for vault/paths.py."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from atlasmind.vault.paths import (
    entity_path,
    note_filename,
    note_path,
    raw_capture_filename,
    resolve_note_path,
    slugify,
    validate_kb_slug,
    link_html_filename,
)

_DT = datetime(2026, 5, 2, 14, 25, 3, tzinfo=timezone.utc)


@pytest.mark.unit
class TestSlugify:
    def test_basic(self):
        assert slugify("Coffee with Mateo") == "coffee-with-mateo"

    def test_max_words(self):
        result = slugify("one two three four five six seven eight", max_words=6)
        assert result == "one-two-three-four-five-six"

    def test_unicode_folding(self):
        assert slugify("Café Tortoni") == "cafe-tortoni"

    def test_special_chars_stripped(self):
        assert slugify("Hello, World! 2026") == "hello-world-2026"

    def test_empty_returns_untitled(self):
        assert slugify("") == "untitled"
        assert slugify("!!!") == "untitled"

    def test_deterministic(self):
        assert slugify("Same input") == slugify("Same input")


@pytest.mark.unit
class TestNoteFilename:
    def test_format(self):
        name = note_filename(_DT, "Coffee with Mateo")
        assert name == "2026-05-02-coffee-with-mateo.md"

    def test_slug_truncated(self):
        name = note_filename(_DT, "one two three four five six seven eight")
        assert name == "2026-05-02-one-two-three-four-five-six.md"


@pytest.mark.unit
class TestNotePath:
    def test_structure(self):
        path = note_path("personal-diary", _DT, "Coffee with Mateo")
        assert path == "personal-diary/notes/2026-05-02-coffee-with-mateo.md"


@pytest.mark.unit
class TestEntityPath:
    def test_structure(self):
        path = entity_path("personal-diary", "people", "Mateo")
        assert path == "personal-diary/people/mateo.md"


@pytest.mark.unit
class TestResolveNotePath:
    def test_no_collision(self, tmp_path: Path):
        path = resolve_note_path(tmp_path, "personal-diary", _DT, "Coffee with Mateo")
        assert path == "personal-diary/notes/2026-05-02-coffee-with-mateo.md"

    def test_collision_appends_counter(self, tmp_path: Path):
        existing = tmp_path / "personal-diary" / "notes" / "2026-05-02-coffee-with-mateo.md"
        existing.parent.mkdir(parents=True)
        existing.touch()
        path = resolve_note_path(tmp_path, "personal-diary", _DT, "Coffee with Mateo")
        assert path == "personal-diary/notes/2026-05-02-coffee-with-mateo-2.md"

    def test_multiple_collisions(self, tmp_path: Path):
        base_dir = tmp_path / "personal-diary" / "notes"
        base_dir.mkdir(parents=True)
        (base_dir / "2026-05-02-coffee-with-mateo.md").touch()
        (base_dir / "2026-05-02-coffee-with-mateo-2.md").touch()
        path = resolve_note_path(tmp_path, "personal-diary", _DT, "Coffee with Mateo")
        assert path == "personal-diary/notes/2026-05-02-coffee-with-mateo-3.md"


@pytest.mark.unit
class TestValidateKbSlug:
    def test_valid_slugs(self):
        assert validate_kb_slug("personal-diary") is True
        assert validate_kb_slug("econ-politics") is True
        assert validate_kb_slug("a") is True

    def test_invalid_slugs(self):
        assert validate_kb_slug("Personal-Diary") is False  # uppercase
        assert validate_kb_slug("personal diary") is False  # space
        assert validate_kb_slug("-starts-with-dash") is False
        assert validate_kb_slug("") is False
        assert validate_kb_slug("a" * 33) is False  # too long


@pytest.mark.unit
def test_link_html_filename():
    filename = link_html_filename(_DT, "https://example.com/article")
    assert filename.startswith("raw/links/")
    assert filename.endswith(".html")
    assert "2026-05-02" in filename


@pytest.mark.unit
class TestRawCaptureFilename:
    def test_structure(self):
        filename = raw_capture_filename(_DT, "Hola mundo")
        assert filename.startswith("raw/captures/")
        assert filename.endswith(".md")
        assert "2026-05-02T14-25-03Z" in filename

    def test_deterministic(self):
        assert raw_capture_filename(_DT, "same text") == raw_capture_filename(_DT, "same text")

    def test_different_text_differs(self):
        assert raw_capture_filename(_DT, "one") != raw_capture_filename(_DT, "two")
