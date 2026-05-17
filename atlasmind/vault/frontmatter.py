"""YAML frontmatter parse and serialize for vault markdown files.

Uses python-frontmatter under the hood. Also owns the general_log.md entry parser.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import frontmatter as fm

# ── compiled patterns ───────────────────────────────────────────────────────

_LOG_ENTRY_RE = re.compile(
    r"^## \[(?P<ts>[^\]]+)\] (?P<kind>\w+) \| (?P<rest>.+)$",
    re.MULTILINE,
)

_ROUTE_HEADER_RE = re.compile(
    r"^## \[(?P<ts>[^\]]+)\] route \| (?P<kb>[^|]+) \| (?P<conf>high|medium|low)$",
    re.MULTILINE,
)

_FIELD_RE = re.compile(r"^\*\*(?P<key>[^*:]+):\*\*\s*(?P<val>.+)$")


# ── frontmatter parse / serialize ───────────────────────────────────────────

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


# ── log entry parsing ────────────────────────────────────────────────────────

def parse_log_entries(text: str) -> list[dict[str, Any]]:
    """Parse all `## [timestamp] kind | ...` headings from a log file.

    Malformed entries are skipped with a warning.
    """
    return [
        {
            "timestamp": m.group("ts"),
            "kind": m.group("kind"),
            "rest": m.group("rest"),
            "raw_header": m.group(0),
        }
        for m in _LOG_ENTRY_RE.finditer(text)
    ]


def parse_routing_log_entries(text: str) -> list[dict[str, Any]]:
    """Parse general_log.md entries with full field extraction.

    Each entry has: timestamp, kb_slug, confidence, source, preview, rationale, file_path.
    Malformed entries are skipped with a warning.
    """
    entries: list[dict[str, Any]] = []
    matches = list(_ROUTE_HEADER_RE.finditer(text))
    for i, m in enumerate(matches):
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block_text = text[m.end():block_end]
        entry: dict[str, Any] = {
            "timestamp": m.group("ts"),
            "kb_slug": m.group("kb").strip(),
            "confidence": m.group("conf"),
        }
        for line in block_text.splitlines():
            field = _FIELD_RE.match(line.strip())
            if field:
                entry[field.group("key").lower().replace(" ", "_")] = field.group("val").strip()
        entries.append(entry)
    return entries


# ── entry formatters ─────────────────────────────────────────────────────────

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
