"""Path conventions, slug generation, and collision handling.

All conventions defined here are deterministic: same input → same output.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


def slugify(text: str, max_words: int = 6) -> str:
    """Convert text to a kebab-case, ASCII-folded slug of at most max_words words."""
    # Normalize unicode to ASCII
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    # Lowercase and replace non-alphanumeric with spaces
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    # Split, take first max_words, join with dashes
    words = text.split()[:max_words]
    slug = "-".join(w for w in words if w)
    return slug or "untitled"


def note_filename(received_at: datetime, title: str) -> str:
    """Build a note filename: YYYY-MM-DD-<slug>.md"""
    date_str = received_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
    slug = slugify(title)
    return f"{date_str}-{slug}.md"


def entity_filename(name: str) -> str:
    """Build an entity page filename: <slug>.md"""
    return f"{slugify(name, max_words=8)}.md"


def note_path(kb_slug: str, received_at: datetime, title: str) -> str:
    """Repo-relative path for a new note (no collision check — use resolve_note_path for writes)."""
    return f"{kb_slug}/notes/{note_filename(received_at, title)}"


def entity_path(kb_slug: str, entity_folder: str, name: str) -> str:
    """Repo-relative path for an entity page."""
    return f"{kb_slug}/{entity_folder}/{entity_filename(name)}"


def resolve_note_path(vault_root: Path, kb_slug: str, received_at: datetime, title: str) -> str:
    """Return the final note path, appending -2/-3/... to avoid collisions."""
    base = note_filename(received_at, title)
    stem, ext = base.rsplit(".", 1)
    candidate = f"{kb_slug}/notes/{stem}.{ext}"
    counter = 2
    while (vault_root / candidate).exists():
        candidate = f"{kb_slug}/notes/{stem}-{counter}.{ext}"
        counter += 1
    return candidate


def validate_kb_slug(slug: str) -> bool:
    """Return True if slug is valid: kebab-case alphanumerics+dashes, ≤32 chars."""
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", slug))


def link_html_filename(received_at: datetime, url: str) -> str:
    """Build the raw/links HTML snapshot filename."""
    import hashlib
    sha = hashlib.sha1(url.encode()).hexdigest()[:12]
    ts = received_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"raw/links/{ts}__{sha}.html"
