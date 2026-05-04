"""Unit tests for agents/tools/kb_meta.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from atlasmind.agents.tools.kb_meta import _parse_registry, _stratified_sample, make_kb_meta_tools
from atlasmind.bootstrap import run as bootstrap_run


@pytest.mark.unit
def test_parse_registry_empty_dir(tmp_path: Path):
    result = _parse_registry(tmp_path)
    assert result == []


@pytest.mark.unit
def test_parse_registry_reads_slugs(tmp_path: Path):
    bootstrap_run(vault_path=tmp_path)
    entries = _parse_registry(tmp_path)
    slugs = [e["slug"] for e in entries]
    assert "personal-diary" in slugs
    assert "reflections" in slugs


@pytest.mark.unit
def test_parse_registry_active_field(tmp_path: Path):
    bootstrap_run(vault_path=tmp_path)
    entries = _parse_registry(tmp_path)
    book = next(e for e in entries if e["slug"] == "book-readings")
    assert book.get("active") == "false"
    diary = next(e for e in entries if e["slug"] == "personal-diary")
    assert diary.get("active") == "true"


@pytest.mark.unit
def test_stratified_sample_empty():
    result = _stratified_sample([], set(), 10)
    assert result == []


@pytest.mark.unit
def test_stratified_sample_one_per_kb():
    entries = [
        {"timestamp": "2026-05-01T00:00:00Z", "kb_slug": "kb-a"},
        {"timestamp": "2026-05-02T00:00:00Z", "kb_slug": "kb-a"},
        {"timestamp": "2026-05-03T00:00:00Z", "kb_slug": "kb-b"},
    ]
    result = _stratified_sample(entries, {"kb-a", "kb-b"}, 2)
    assert len(result) == 2
    slugs = {e["kb_slug"] for e in result}
    assert slugs == {"kb-a", "kb-b"}


@pytest.mark.unit
def test_stratified_sample_fills_remaining():
    entries = [
        {"timestamp": f"2026-05-{i:02d}T00:00:00Z", "kb_slug": "kb-a"}
        for i in range(1, 6)
    ]
    # n=4, active_slugs={"kb-a"} — guaranteed: 1 (most recent), fill: 3 more
    result = _stratified_sample(entries, {"kb-a"}, 4)
    assert len(result) == 4


@pytest.mark.unit
def test_stratified_sample_respects_n():
    entries = [
        {"timestamp": f"2026-05-{i:02d}T00:00:00Z", "kb_slug": "kb-a"}
        for i in range(1, 11)
    ]
    result = _stratified_sample(entries, {"kb-a"}, 3)
    assert len(result) == 3


@pytest.mark.unit
def test_commit_route_writes_source_and_preview(tmp_path: Path):
    bootstrap_run(vault_path=tmp_path)
    tools = make_kb_meta_tools(tmp_path)
    commit = next(t for t in tools if t.name == "commit_route")
    commit.invoke({
        "kb_slug": "personal-diary",
        "rationale": "Real event.",
        "confidence": "high",
        "source": "voice",
        "preview": "Met Mateo today",
    })
    log = (tmp_path / "_meta" / "general_log.md").read_text()
    assert "voice" in log
    assert "Met Mateo today" in log
