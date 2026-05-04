"""YAML frontmatter parse and serialize for vault markdown files.

Uses python-frontmatter under the hood. Also owns the general_log.md entry parser.
"""
from __future__ import annotations

import re
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import frontmatter as fm


def parse(text: str) -> tuple[dict, str]:
    """Return (metadata_dict, body_text) from a markdown string."""
    post = fm.loads(text)
    return dict(post.metadata), post.content


def serialize(metadata: dict, body: str) -> str:
    """Return a markdown string with YAML frontmatter prepended."""
    post = fm.Post(body.strip() + "\n", **metadata)
    return fm.dumps(post)


def parse_file(path: Path) -> tuple[dict, str]:
    post = fm.load(str(path))
    return dict(post.metadata), post.content


def write_file(path: Path, metadata: dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize(metadata, body), encoding="utf-8")


# ── general_log.md / log.md entry parsing ──────────────────────────────────

_LOG_ENTRY_RE = re.compile(
    r"^## \[(?P<ts>[^\]]+)\] (?P<kind>\w+) \| (?P<rest>.+)$",
    re.MULTILINE,
)


def parse_log_entries(text: str) -> list[dict[str, Any]]:
    """Parse all `## [timestamp] kind | ...` headings from a log file.

    Malformed entries are skipped with a warning.
    """
    entries: list[dict[str, Any]] = []
    for m in _LOG_ENTRY_RE.finditer(text):
        try:
            entries.append(
                {
                    "timestamp": m.group("ts"),
                    "kind": m.group("kind"),
                    "rest": m.group("rest"),
                    "raw_header": m.group(0),
                }
            )
        except Exception as exc:  # noqa: BLE001
            warnings.warn(f"Skipping malformed log entry: {m.group(0)!r} — {exc}")
    return entries


def parse_routing_log_entries(text: str) -> list[dict[str, Any]]:
    """Parse general_log.md entries with full field extraction.

    Each entry has: timestamp, kb_slug, confidence, source, preview, rationale, file_path.
    Malformed entries are skipped with a warning.
    """
    entries: list[dict[str, Any]] = []

    _ROUTE_HEADER = re.compile(
        r"^## \[(?P<ts>[^\]]+)\] route \| (?P<kb>[^|]+) \| (?P<conf>high|medium|low)$",
        re.MULTILINE,
    )
    _FIELD = re.compile(r"^\*\*(?P<key>[^*]+)\*\*: ?(?P<val>.+)$")

    blocks = _ROUTE_HEADER.split(text)
    headers = _ROUTE_HEADER.findall(text)

    for i, header in enumerate(headers):
        ts, kb, conf = header
        block_text = blocks[i * 4 + 4] if len(blocks) > i * 4 + 4 else ""
        entry: dict[str, Any] = {"timestamp": ts, "kb_slug": kb.strip(), "confidence": conf}
        for line in block_text.splitlines():
            m = _FIELD.match(line.strip())
            if m:
                entry[m.group("key").lower().replace(" ", "_")] = m.group("val").strip()
        entries.append(entry)

    return entries


def format_routing_log_entry(
    *,
    ts: str,
    kb_slug: str,
    confidence: str,
    source: str,
    preview: str,
    rationale: str,
    file_path: str,
) -> str:
    return (
        f"## [{ts}] route | {kb_slug} | {confidence}\n"
        f"**Source:** {source}\n"
        f"**Preview:** {preview}\n"
        f"**Rationale:** {rationale}\n"
        f"**File:** {file_path}\n"
    )


def format_kb_log_entry(
    *,
    ts: str,
    note_slug: str,
    note_path: str,
    pages_updated: list[str],
    summary: str,
) -> str:
    pages = ", ".join(pages_updated) if pages_updated else "—"
    return (
        f"## [{ts}] ingest | {note_slug}\n"
        f"**Note:** [[{note_path}|{note_slug}]]\n"
        f"**Pages updated:** {pages}\n"
        f"**Summary:** {summary}\n"
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
