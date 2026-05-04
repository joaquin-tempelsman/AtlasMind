"""KB ingestion tools scoped to a single KB folder.

All tools are bound to (vault_root, kb_slug) at construction via make_kb_page_tools().
Paths are validated against the KB root — reads and writes outside the KB raise PathEscapeError.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from atlasmind.vault import frontmatter as fm
from atlasmind.vault.fs import PathEscapeError


# ── path safety ───────────────────────────────────────────────────────────────

def _kb_resolve(kb_root: Path, rel_path: str) -> Path:
    """Resolve rel_path inside kb_root, raising PathEscapeError if it escapes."""
    resolved = (kb_root / rel_path).resolve()
    try:
        resolved.relative_to(kb_root.resolve())
    except ValueError:
        raise PathEscapeError(f"Path {rel_path!r} escapes KB root {kb_root}")
    return resolved


# ── index helpers ─────────────────────────────────────────────────────────────

def _update_index_text(text: str, category: str, line: str) -> str:
    """Insert line under ## category in text, creating the section if absent."""
    header = f"## {category}"
    lines = text.splitlines(keepends=True)

    section_start: int | None = None
    for i, ln in enumerate(lines):
        if ln.rstrip("\n\r") == header:
            section_start = i
            break

    if section_start is None:
        # Append new section
        suffix = "" if text.endswith("\n") else "\n"
        return text + f"{suffix}\n{header}\n{line}\n"

    # Find end of section (next ## heading or EOF)
    section_end = len(lines)
    for i in range(section_start + 1, len(lines)):
        if lines[i].startswith("## "):
            section_end = i
            break

    # Insert before the blank lines that precede the next section
    insert_pos = section_end
    for i in range(section_end - 1, section_start, -1):
        if lines[i].strip():
            insert_pos = i + 1
            break

    lines.insert(insert_pos, f"{line}\n")
    return "".join(lines)


# ── tool factory ──────────────────────────────────────────────────────────────

def make_kb_page_tools(vault_root: Path, kb_slug: str) -> list:
    """Return KB ingestion page tools bound to vault_root/kb_slug."""
    kb_root = vault_root / kb_slug

    @tool
    def list_pages(folder: str = "") -> list[str]:
        """List markdown files in this KB, optionally filtered to a subfolder."""
        base = _kb_resolve(kb_root, folder) if folder else kb_root
        if not base.exists():
            return []
        return [
            str(p.relative_to(kb_root))
            for p in sorted(base.rglob("*.md"))
        ]

    @tool
    def read_page(rel_path: str) -> str:
        """Read a page within this KB. Raises if path escapes the KB root."""
        full = _kb_resolve(kb_root, rel_path)
        if not full.exists():
            return f"(file not found: {rel_path})"
        return full.read_text(encoding="utf-8")

    @tool
    def write_page(rel_path: str, content: str, frontmatter_data: dict[str, Any] | None = None) -> str:
        """Create or overwrite a page. If frontmatter_data is given, it is merged with KB defaults."""
        full = _kb_resolve(kb_root, rel_path)
        full.parent.mkdir(parents=True, exist_ok=True)
        if frontmatter_data:
            defaults: dict[str, Any] = {"type": "note", "kb": kb_slug}
            merged = {**defaults, **frontmatter_data}
            text = fm.serialize(merged, content)
        else:
            text = content
        full.write_text(text, encoding="utf-8")
        return f"written: {rel_path}"

    @tool
    def append_to_page(rel_path: str, content: str) -> str:
        """Append content to an existing page within this KB."""
        full = _kb_resolve(kb_root, rel_path)
        if not full.exists():
            return f"(file not found: {rel_path})"
        existing = full.read_text(encoding="utf-8")
        sep = "" if existing.endswith("\n") else "\n"
        full.write_text(existing + sep + content, encoding="utf-8")
        return f"appended: {rel_path}"

    @tool
    def search_pages(query: str) -> list[dict]:
        """Case-insensitive substring search across all markdown files in this KB."""
        query_lower = query.lower()
        results: list[dict] = []
        for md_path in sorted(kb_root.rglob("*.md")):
            try:
                text = md_path.read_text(encoding="utf-8")
            except OSError:
                continue
            if query_lower in text.lower():
                # Return first matching line as excerpt
                for ln in text.splitlines():
                    if query_lower in ln.lower():
                        excerpt = ln.strip()[:120]
                        break
                else:
                    excerpt = ""
                results.append({"path": str(md_path.relative_to(kb_root)), "excerpt": excerpt})
        return results

    @tool
    def read_index() -> str:
        """Return the KB's index.md contents."""
        idx = kb_root / "index.md"
        if not idx.exists():
            return "(index.md not found)"
        return idx.read_text(encoding="utf-8")

    @tool
    def update_index(category: str, line: str) -> str:
        """Append a one-line entry under ## category in index.md, creating the section if needed."""
        idx = kb_root / "index.md"
        if not idx.exists():
            return "(index.md not found)"
        text = idx.read_text(encoding="utf-8")
        updated = _update_index_text(text, category, line)
        idx.write_text(updated, encoding="utf-8")
        return f"index updated: {category}"

    return [list_pages, read_page, write_page, append_to_page, search_pages, read_index, update_index]
