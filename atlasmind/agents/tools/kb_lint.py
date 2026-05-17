"""Lint-specific terminal tool for the lint agent."""
from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool


def make_kb_lint_tools(vault_root: Path, kb_slug: str) -> list:
    """Return lint tools bound to vault_root/kb_slug."""

    @tool
    def finalize_lint(summary_for_user: str) -> dict:
        """Terminal tool. Signal lint complete.

        summary_for_user is a 3–5 bullet Telegram-friendly summary of findings.
        Call exactly once, after writing the full report with write_page().
        """
        return {"done": True, "summary": summary_for_user}

    return [finalize_lint]
