"""Unit tests for vault/fs.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from atlasmind.vault.fs import PathEscapeError, append_md, exists, list_md, read_md, write_md


@pytest.mark.unit
def test_write_and_read_roundtrip(vault: Path):
    write_md(vault, "kb1/notes/test.md", "# Hello\n")
    assert read_md(vault, "kb1/notes/test.md") == "# Hello\n"


@pytest.mark.unit
def test_write_creates_parent_dirs(vault: Path):
    write_md(vault, "deep/nested/path/file.md", "content")
    assert (vault / "deep" / "nested" / "path" / "file.md").exists()


@pytest.mark.unit
def test_append_adds_content(vault: Path):
    write_md(vault, "log.md", "line1\n")
    append_md(vault, "log.md", "line2\n")
    assert read_md(vault, "log.md") == "line1\nline2\n"


@pytest.mark.unit
def test_append_raises_if_file_missing(vault: Path):
    with pytest.raises(FileNotFoundError):
        append_md(vault, "nonexistent.md", "content")


@pytest.mark.unit
def test_path_escape_raises(vault: Path):
    with pytest.raises(PathEscapeError):
        read_md(vault, "../../../etc/passwd")


@pytest.mark.unit
def test_path_escape_raises_double_dot(vault: Path):
    with pytest.raises(PathEscapeError):
        write_md(vault, "kb/../../../outside.md", "bad")


@pytest.mark.unit
def test_exists_returns_true_for_written_file(vault: Path):
    write_md(vault, "notes/x.md", "hi")
    assert exists(vault, "notes/x.md") is True


@pytest.mark.unit
def test_exists_returns_false_for_missing(vault: Path):
    assert exists(vault, "no-such-file.md") is False


@pytest.mark.unit
def test_exists_returns_false_for_escape(vault: Path):
    assert exists(vault, "../outside.md") is False


@pytest.mark.unit
def test_list_md_finds_all_markdown(vault: Path):
    write_md(vault, "kb1/notes/a.md", "a")
    write_md(vault, "kb1/notes/b.md", "b")
    write_md(vault, "kb1/index.md", "idx")
    paths = list_md(vault)
    assert "kb1/notes/a.md" in paths
    assert "kb1/notes/b.md" in paths
    assert "kb1/index.md" in paths


@pytest.mark.unit
def test_list_md_scoped_to_subfolder(vault: Path):
    write_md(vault, "kb1/notes/a.md", "a")
    write_md(vault, "kb2/notes/b.md", "b")
    paths = list_md(vault, "kb1")
    assert all(p.startswith("kb1/") for p in paths)
    assert not any(p.startswith("kb2/") for p in paths)
