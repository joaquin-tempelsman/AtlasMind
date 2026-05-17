"""Unit tests for vault/git_sync.py — uses a real temp git repo."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlasmind.vault.git_sync import commit, is_dirty, pull, push


def _configure_git(path: Path) -> None:
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(path), check=True, capture_output=True)


@pytest.mark.unit
def test_commit_creates_real_commit(vault: Path):
    _configure_git(vault)
    (vault / "notes.md").write_text("# Notes\n")
    sha = commit(vault, "test: add notes")
    assert sha is not None
    assert len(sha) == 40

    log = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=str(vault), capture_output=True, text=True,
    )
    assert "test: add notes" in log.stdout


@pytest.mark.unit
def test_commit_returns_none_when_nothing_to_commit(vault: Path):
    _configure_git(vault)
    sha = commit(vault, "empty commit")
    assert sha is None


@pytest.mark.unit
def test_commit_specific_paths(vault: Path):
    _configure_git(vault)
    (vault / "a.md").write_text("a")
    (vault / "b.md").write_text("b")
    sha = commit(vault, "add a only", paths=["a.md"])
    assert sha is not None

    # b.md should still be unstaged
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(vault), capture_output=True, text=True,
    )
    assert "b.md" in status.stdout


@pytest.mark.unit
def test_is_dirty_false_after_clean_commit(vault: Path):
    _configure_git(vault)
    (vault / "file.md").write_text("content")
    commit(vault, "add file")
    assert is_dirty(vault) is False


@pytest.mark.unit
def test_is_dirty_true_with_uncommitted_changes(vault: Path):
    _configure_git(vault)
    (vault / "file.md").write_text("content")
    assert is_dirty(vault) is True


@pytest.mark.unit
def test_pull_noop_without_remote(vault: Path):
    _configure_git(vault)
    # Should not raise even with no remote configured
    pull(vault)


@pytest.mark.unit
def test_push_noop_without_remote(vault: Path):
    _configure_git(vault)
    # Should not raise even with no remote configured
    push(vault)
