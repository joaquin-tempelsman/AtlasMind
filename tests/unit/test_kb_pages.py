"""Unit tests for agents/tools/kb_pages.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from atlasmind.agents.tools.kb_pages import _update_index_text, make_kb_page_tools
from atlasmind.bootstrap import run as bootstrap_run
from atlasmind.vault.fs import PathEscapeError


# ── _update_index_text ────────────────────────────────────────────────────────

@pytest.mark.unit
def test_update_index_existing_section():
    text = "# Index\n\n## Notes\n- existing\n\n## People\n- alice\n"
    result = _update_index_text(text, "Notes", "- new entry")
    assert "- new entry" in result
    assert "## Notes" in result
    # new entry should be in the Notes section before People
    notes_pos = result.index("## Notes")
    people_pos = result.index("## People")
    entry_pos = result.index("- new entry")
    assert notes_pos < entry_pos < people_pos


@pytest.mark.unit
def test_update_index_creates_section():
    text = "# Index\n\n## Notes\n- existing\n"
    result = _update_index_text(text, "Projects", "- my project")
    assert "## Projects" in result
    assert "my project" in result


@pytest.mark.unit
def test_update_index_preserves_existing():
    text = "# Index\n\n## Notes\n- existing\n"
    result = _update_index_text(text, "Notes", "- new")
    assert "- existing" in result
    assert "- new" in result


# ── make_kb_page_tools ────────────────────────────────────────────────────────

@pytest.fixture()
def kb_tools(tmp_path: Path):
    bootstrap_run(vault_path=tmp_path)
    return make_kb_page_tools(tmp_path, "personal-diary"), tmp_path


@pytest.mark.unit
def test_write_then_list(kb_tools):
    tools, _ = kb_tools
    write = next(t for t in tools if t.name == "write_page")
    lst = next(t for t in tools if t.name == "list_pages")

    write.invoke({"rel_path": "notes/my-note.md", "content": "# Hello"})
    pages = lst.invoke({})
    assert any("my-note.md" in p for p in pages)


@pytest.mark.unit
def test_read_missing_page_returns_message(kb_tools):
    tools, _ = kb_tools
    read = next(t for t in tools if t.name == "read_page")
    result = read.invoke({"rel_path": "notes/nonexistent.md"})
    assert "not found" in result


@pytest.mark.unit
def test_path_escape_in_list_pages(kb_tools):
    tools, _ = kb_tools
    lst = next(t for t in tools if t.name == "list_pages")
    with pytest.raises(PathEscapeError):
        lst.invoke({"folder": "../reflections"})


@pytest.mark.unit
def test_search_returns_empty_on_no_match(kb_tools):
    tools, _ = kb_tools
    search = next(t for t in tools if t.name == "search_pages")
    results = search.invoke({"query": "zzznomatch99999"})
    assert results == []


@pytest.mark.unit
def test_append_creates_separator_if_missing(kb_tools):
    tools, _ = kb_tools
    write = next(t for t in tools if t.name == "write_page")
    append = next(t for t in tools if t.name == "append_to_page")
    read = next(t for t in tools if t.name == "read_page")

    write.invoke({"rel_path": "notes/sep-test.md", "content": "first"})
    append.invoke({"rel_path": "notes/sep-test.md", "content": "second"})
    text = read.invoke({"rel_path": "notes/sep-test.md"})
    assert "first" in text
    assert "second" in text


@pytest.mark.unit
def test_update_index_section_roundtrip(kb_tools):
    tools, vault = kb_tools
    update = next(t for t in tools if t.name == "update_index")
    read = next(t for t in tools if t.name == "read_index")

    update.invoke({"category": "Notes", "line": "- 2026-05-04 — test"})
    update.invoke({"category": "Notes", "line": "- 2026-05-05 — second"})
    result = read.invoke({})
    assert "test" in result
    assert "second" in result
