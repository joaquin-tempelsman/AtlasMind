"""Unit tests for agents/tools/kb_log.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from atlasmind.agents.tools.kb_log import make_kb_log_tools
from atlasmind.bootstrap import run as bootstrap_run


@pytest.fixture()
def log_tools(tmp_path: Path):
    bootstrap_run(vault_path=tmp_path)
    return make_kb_log_tools(tmp_path, "personal-diary"), tmp_path


@pytest.mark.unit
def test_append_kb_log_content(log_tools):
    tools, vault = log_tools
    append = next(t for t in tools if t.name == "append_kb_log")

    entry = "## [2026-05-04T10:00:00Z] ingest | test-slug\n**Summary:** A note.\n"
    append.invoke({"entry": entry})

    text = (vault / "personal-diary" / "log.md").read_text()
    assert "test-slug" in text
    assert "A note." in text


@pytest.mark.unit
def test_append_kb_log_idempotent_multiple(log_tools):
    tools, vault = log_tools
    append = next(t for t in tools if t.name == "append_kb_log")

    append.invoke({"entry": "## [2026-05-04T10:00:00Z] ingest | first\n"})
    append.invoke({"entry": "## [2026-05-04T11:00:00Z] ingest | second\n"})

    text = (vault / "personal-diary" / "log.md").read_text()
    assert "first" in text
    assert "second" in text


@pytest.mark.unit
def test_finalize_returns_dict(log_tools):
    tools, _ = log_tools
    finalize = next(t for t in tools if t.name == "finalize")

    result = finalize.invoke({"summary_for_user": "Done. Filed 1 note."})
    assert result == {"done": True, "summary": "Done. Filed 1 note."}


@pytest.mark.unit
def test_finalize_preserves_multiline_summary(log_tools):
    tools, _ = log_tools
    finalize = next(t for t in tools if t.name == "finalize")

    summary = "Note 1: filed.\nNote 2: updated entity pages."
    result = finalize.invoke({"summary_for_user": summary})
    assert result["summary"] == summary
