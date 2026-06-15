"""Path conventions, slug generation, and collision handling.

All conventions defined here are deterministic: same input → same output.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


def slugify(text: str, max_words: int = 6) -> str:
    """Convert text to a kebab-case, ASCII-folded slug of at most max_words words."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
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
    base = Path(note_filename(received_at, title))
    stem = base.stem
    ext = base.suffix
    candidate = f"{kb_slug}/notes/{stem}{ext}"
    counter = 2
    while (vault_root / candidate).exists():
        candidate = f"{kb_slug}/notes/{stem}-{counter}{ext}"
        counter += 1
    return candidate


def validate_kb_slug(slug: str) -> bool:
    """Return True if slug is valid: kebab-case alphanumerics+dashes, ≤32 chars."""
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", slug))


def link_html_filename(received_at: datetime, url: str) -> str:
    """Build the raw/links HTML snapshot filename."""
    sha = hashlib.sha1(url.encode()).hexdigest()[:12]
    # Dashes in time component so the filename is safe on all filesystems
    ts = received_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"raw/links/{ts}__{sha}.html"


def raw_capture_filename(received_at: datetime, text: str) -> str:
    """Build the raw/captures filename for a verbatim text/voice input."""
    sha = hashlib.sha1(text.encode()).hexdigest()[:12]
    # Dashes in time component so the filename is safe on all filesystems
    ts = received_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"raw/captures/{ts}__{sha}.md"
