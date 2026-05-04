"""KB log tools: append_kb_log and finalize.

Bound to (vault_root, kb_slug) via make_kb_log_tools().
"""
from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from atlasmind.vault.fs import append_md


def make_kb_log_tools(vault_root: Path, kb_slug: str) -> list:
    """Return log tools bound to vault_root/kb_slug."""

    @tool
    def append_kb_log(entry: str) -> str:
        """Append a formatted entry to this KB's log.md."""
        append_md(vault_root, f"{kb_slug}/log.md", "\n" + entry + "\n")
        return "ok"

    @tool
    def finalize(summary_for_user: str) -> dict:
        """Signal that all batch items are ingested. Returns the Telegram reply text."""
        return {"done": True, "summary": summary_for_user}

    return [append_kb_log, finalize]
