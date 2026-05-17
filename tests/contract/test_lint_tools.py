"""Contract tests: lint tools (kb_lint.finalize_lint).

Spec: dev_specs/05_agent_layer.md §4 — Lint agent
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atlasmind.agents.tools.kb_lint import make_kb_lint_tools


def _get_tool(tools: list, name: str):
    return next(t for t in tools if t.name == name)


@pytest.mark.contract
def test_finalize_lint_returns_done_and_summary(tmp_path: Path):
    """finalize_lint returns {done: True, summary: ...}."""
    tools = make_kb_lint_tools(tmp_path, "personal-diary")
    finalize_lint = _get_tool(tools, "finalize_lint")

    result = finalize_lint.invoke({"summary_for_user": "• Lint complete.\n• 0 orphans found."})

    assert result["done"] is True
    assert result["summary"] == "• Lint complete.\n• 0 orphans found."


@pytest.mark.contract
def test_finalize_lint_empty_summary(tmp_path: Path):
    """finalize_lint accepts an empty summary string."""
    tools = make_kb_lint_tools(tmp_path, "personal-diary")
    finalize_lint = _get_tool(tools, "finalize_lint")

    result = finalize_lint.invoke({"summary_for_user": ""})

    assert result["done"] is True
    assert result["summary"] == ""
