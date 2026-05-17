"""Unit tests for agents/tools/kb_entities.py."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from atlasmind.agents.tools.kb_entities import make_kb_entity_tools


_ENTITIES_HEADER = textwrap.dedent("""\
    ---
    type: kb_entity_registry
    kb: test-kb
    ---

    # Entity Registry

    Each line: Canonical Name | alias1 | alias2 | ...

    ---
    """)


def _make_tools(tmp_path: Path, initial_content: str | None = None) -> list:
    kb_root = tmp_path / "test-kb"
    kb_root.mkdir(parents=True, exist_ok=True)
    if initial_content is not None:
        (kb_root / "entities.md").write_text(initial_content, encoding="utf-8")
    return make_kb_entity_tools(tmp_path, "test-kb")


def _get_tool(tools: list, name: str):
    return next(t for t in tools if t.name == name)


def _read_entities(tmp_path: Path) -> str:
    return (tmp_path / "test-kb" / "entities.md").read_text(encoding="utf-8")


@pytest.mark.unit
def test_register_new_entity_appends_line(tmp_path: Path):
    """Registering an entity not in the file appends a new pipe-separated line."""
    tools = _make_tools(tmp_path, _ENTITIES_HEADER)
    register = _get_tool(tools, "register_entity")

    result = register.invoke({"canonical_name": "Thomas Piketty", "aliases": ["Piketty", "T. Piketty"]})

    assert result == "Registered: Thomas Piketty"
    content = _read_entities(tmp_path)
    assert "Thomas Piketty | Piketty | T. Piketty" in content


@pytest.mark.unit
def test_register_new_entity_no_aliases(tmp_path: Path):
    """Registering with no aliases writes just the canonical name."""
    tools = _make_tools(tmp_path, _ENTITIES_HEADER)
    register = _get_tool(tools, "register_entity")

    register.invoke({"canonical_name": "Café Tortoni", "aliases": []})

    content = _read_entities(tmp_path)
    assert "Café Tortoni\n" in content


@pytest.mark.unit
def test_register_existing_entity_merges_aliases(tmp_path: Path):
    """Registering an already-present canonical name merges aliases without duplication."""
    initial = _ENTITIES_HEADER + "Thomas Piketty | Piketty\n"
    tools = _make_tools(tmp_path, initial)
    register = _get_tool(tools, "register_entity")

    register.invoke({"canonical_name": "Thomas Piketty", "aliases": ["T. Piketty", "Piketty"]})

    content = _read_entities(tmp_path)
    # Should appear exactly once
    assert content.count("Thomas Piketty") == 1
    # Both aliases merged
    assert "Piketty" in content
    assert "T. Piketty" in content


@pytest.mark.unit
def test_register_missing_entities_file_returns_message(tmp_path: Path):
    """Returns a graceful message if entities.md does not exist."""
    (tmp_path / "test-kb").mkdir(parents=True, exist_ok=True)
    tools = make_kb_entity_tools(tmp_path, "test-kb")
    register = _get_tool(tools, "register_entity")

    result = register.invoke({"canonical_name": "Ghost", "aliases": []})

    assert "not found" in result


@pytest.mark.unit
def test_register_multiple_distinct_entities(tmp_path: Path):
    """Multiple distinct entities are appended as separate lines."""
    tools = _make_tools(tmp_path, _ENTITIES_HEADER)
    register = _get_tool(tools, "register_entity")

    register.invoke({"canonical_name": "Entity A", "aliases": ["A"]})
    register.invoke({"canonical_name": "Entity B", "aliases": ["B"]})

    content = _read_entities(tmp_path)
    assert "Entity A | A" in content
    assert "Entity B | B" in content
