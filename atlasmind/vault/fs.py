"""Safe markdown read/write operations under VAULT_REPO_PATH.

Every path that enters or exits this module is validated to be inside the vault root.
Callers outside this module must never touch the vault filesystem directly.
"""
from __future__ import annotations

from pathlib import Path


class PathEscapeError(ValueError):
    """Raised when a requested path escapes the vault root."""


def _resolve(vault_root: Path, rel_path: str) -> Path:
    """Resolve rel_path inside vault_root, rejecting any traversal attempt."""
    resolved = (vault_root / rel_path).resolve()
    try:
        resolved.relative_to(vault_root.resolve())
    except ValueError:
        raise PathEscapeError(f"Path {rel_path!r} escapes vault root {vault_root}")
    return resolved


def read_md(vault_root: Path, rel_path: str) -> str:
    path = _resolve(vault_root, rel_path)
    return path.read_text(encoding="utf-8")


def write_md(vault_root: Path, rel_path: str, content: str) -> None:
    path = _resolve(vault_root, rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def append_md(vault_root: Path, rel_path: str, content: str) -> None:
    path = _resolve(vault_root, rel_path)
    if not path.exists():
        raise FileNotFoundError(f"Cannot append — {rel_path!r} does not exist in vault.")
    with path.open("a", encoding="utf-8") as f:
        f.write(content)


def exists(vault_root: Path, rel_path: str) -> bool:
    try:
        path = _resolve(vault_root, rel_path)
    except PathEscapeError:
        return False
    return path.exists()


def list_md(vault_root: Path, rel_dir: str = "") -> list[str]:
    """Return repo-relative paths of all .md files under rel_dir."""
    base = _resolve(vault_root, rel_dir) if rel_dir else vault_root.resolve()
    vault_resolved = vault_root.resolve()
    return [
        str(p.relative_to(vault_resolved))
        for p in sorted(base.rglob("*.md"))
    ]
