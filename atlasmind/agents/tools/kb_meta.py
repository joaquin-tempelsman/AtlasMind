"""Router tools: list_kbs, read_recent_routing, read_routing_rules, commit_route.

All tools are bound to a vault_root at construction via make_kb_meta_tools().
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from atlasmind.vault import frontmatter as fm
from atlasmind.vault.fs import append_md, read_md, exists


# ── registry parsing ──────────────────────────────────────────────────────────

_SECTION_RE = re.compile(r"^## ([a-z0-9][a-z0-9-]*)$", re.MULTILINE)
_FIELD_RE = re.compile(r"^\s*-\s*\*\*([^*:]+):\*\*\s*(.+)$")


def _parse_registry(vault_root: Path) -> list[dict[str, Any]]:
    registry_path = vault_root / "_meta" / "kb_registry.md"
    if not registry_path.exists():
        return []
    text = registry_path.read_text(encoding="utf-8")
    _, body = fm.parse(text)

    entries: list[dict[str, Any]] = []
    matches = list(_SECTION_RE.finditer(body))
    for i, m in enumerate(matches):
        slug = m.group(1)
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        block = body[m.end():block_end]

        entry: dict[str, Any] = {"slug": slug}
        for line in block.splitlines():
            field = _FIELD_RE.match(line)
            if field:
                key = field.group(1).lower().strip().replace(" ", "_")
                entry[key] = field.group(2).strip()
        entries.append(entry)
    return entries


def _active_entries(vault_root: Path) -> list[dict[str, Any]]:
    return [e for e in _parse_registry(vault_root) if e.get("active", "true") == "true"]


# ── stratified sampling ───────────────────────────────────────────────────────

def _stratified_sample(
    entries: list[dict[str, Any]],
    active_slugs: set[str],
    n: int,
) -> list[dict[str, Any]]:
    selected_keys: set[tuple[str, str]] = set()
    guaranteed: list[dict[str, Any]] = []

    # Step 1: most recent entry per active KB (reverse iteration = most recent first)
    guaranteed_slugs: set[str] = set()
    for entry in reversed(entries):
        slug = entry.get("kb_slug", "")
        if slug in active_slugs and slug not in guaranteed_slugs:
            guaranteed.append(entry)
            guaranteed_slugs.add(slug)
            selected_keys.add((entry.get("timestamp", ""), slug))

    # Step 2: fill remaining slots from reverse-chron, skipping already-selected
    result = list(guaranteed)
    for entry in reversed(entries):
        if len(result) >= n:
            break
        key = (entry.get("timestamp", ""), entry.get("kb_slug", ""))
        if key not in selected_keys:
            result.append(entry)
            selected_keys.add(key)

    return result[:n]


# ── tool factory ──────────────────────────────────────────────────────────────

def make_kb_meta_tools(vault_root: Path) -> list:
    """Return the router's four kb_meta tools bound to vault_root."""

    @tool
    def list_kbs() -> list[dict]:
        """List active knowledge bases from the registry. Always call this first."""
        return [
            {"slug": e["slug"], "name": e.get("name", e["slug"]), "description": e.get("description", "")}
            for e in _active_entries(vault_root)
        ]

    @tool
    def read_recent_routing(n: int = 20) -> list[dict]:
        """Return up to n recent routing log entries using stratified sampling."""
        log_path = vault_root / "_meta" / "general_log.md"
        if not log_path.exists():
            return []
        text = log_path.read_text(encoding="utf-8")
        entries = fm.parse_routing_log_entries(text)
        active_slugs = {e["slug"] for e in _active_entries(vault_root)}
        return _stratified_sample(entries, active_slugs, n)

    @tool
    def read_routing_rules() -> str:
        """Return the contents of _meta/routing_rules.md (human-written routing hints)."""
        rules_path = vault_root / "_meta" / "routing_rules.md"
        if not rules_path.exists():
            return ""
        return rules_path.read_text(encoding="utf-8")

    @tool
    def commit_route(
        kb_slug: str,
        rationale: str,
        confidence: str,
        source: str = "",
        preview: str = "",
        file_path: str = "",
    ) -> dict:
        """Commit a routing decision to _meta/general_log.md.

        kb_slug must match an active KB in the registry.
        confidence must be 'high', 'medium', or 'low'.
        Returns {"ok": true, ...} on success or {"ok": false, "error": "..."} on failure.
        """
        active = _active_entries(vault_root)
        active_slugs = {e["slug"] for e in active}

        if kb_slug not in active_slugs:
            known = ", ".join(sorted(active_slugs))
            return {"ok": False, "error": f"Unknown or inactive kb_slug {kb_slug!r}. Known: {known}"}

        if confidence not in ("high", "medium", "low"):
            return {"ok": False, "error": f"confidence must be high/medium/low, got {confidence!r}"}

        ts = fm.utc_now_iso()
        log_entry = fm.format_routing_log_entry(
            ts=ts,
            kb_slug=kb_slug,
            confidence=confidence,
            source=source,
            preview=preview,
            rationale=rationale,
            file_path=file_path,
        )
        append_md(vault_root, "_meta/general_log.md", "\n" + log_entry)
        return {"ok": True, "kb_slug": kb_slug, "log_entry": log_entry}

    return [list_kbs, read_recent_routing, read_routing_rules, commit_route]
