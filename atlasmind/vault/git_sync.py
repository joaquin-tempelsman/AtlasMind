"""Git operations for the vault repo.

Synchronous by design — concurrent writes to the same vault would be a footgun,
and asyncio.Lock in pipeline.py serialises ingests at a higher level.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


class GitSyncError(RuntimeError):
    """Raised when a git operation fails unrecoverably."""


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0:
        raise GitSyncError(
            f"git command failed: {' '.join(cmd)}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
    return result


def _has_remote(vault_root: Path) -> bool:
    result = subprocess.run(
        ["git", "remote"],
        cwd=str(vault_root),
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def pull(vault_root: Path) -> None:
    """Pull latest changes. Stashes unstaged work so --rebase doesn't refuse."""
    if not _has_remote(vault_root):
        return
    stashed = False
    if is_dirty(vault_root):
        _run(["git", "stash", "--include-untracked"], vault_root)
        stashed = True
    try:
        _run(["git", "pull", "--rebase"], vault_root)
    finally:
        if stashed:
            _run(["git", "stash", "pop"], vault_root)


def commit(vault_root: Path, message: str, paths: list[str] | None = None) -> str | None:
    """Stage and commit. Returns the commit SHA, or None if there was nothing to commit."""
    if paths:
        for p in paths:
            _run(["git", "add", p], vault_root)
    else:
        _run(["git", "add", "-A"], vault_root)

    status = _run(["git", "status", "--porcelain"], vault_root)
    if not status.stdout.strip():
        return None

    _run(["git", "commit", "-m", message], vault_root)
    return _run(["git", "rev-parse", "HEAD"], vault_root).stdout.strip()


def push(vault_root: Path) -> None:
    """Push to origin. Retries once after pull --rebase on rejection."""
    if not _has_remote(vault_root):
        return

    push_result = subprocess.run(
        ["git", "push"],
        cwd=str(vault_root),
        capture_output=True,
        text=True,
    )
    if push_result.returncode == 0:
        return

    # Remote moved ahead — pull --rebase then retry once
    _run(["git", "pull", "--rebase"], vault_root)
    _run(["git", "push"], vault_root)


def is_dirty(vault_root: Path) -> bool:
    """Return True if there are uncommitted changes in the working tree."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(vault_root),
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())
