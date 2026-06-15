"""Unit tests for atlasmind/version.py."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlasmind.version import format_version, get_version_info


def _init_repo(path: Path, subject: str = "feat: initial") -> None:
    """Create a git repo with one commit at path."""
    env_cmds = [
        ["git", "init"],
        ["git", "config", "user.email", "test@test.com"],
        ["git", "config", "user.name", "Test"],
    ]
    for cmd in env_cmds:
        subprocess.run(cmd, cwd=str(path), check=True, capture_output=True)
    (path / "README.md").write_text("hi", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", subject], cwd=str(path), check=True, capture_output=True)


@pytest.mark.unit
def test_get_version_info_reads_git(tmp_path: Path):
    _init_repo(tmp_path, subject="feat: add the thing")
    info = get_version_info(tmp_path)
    assert info["sha"] and len(info["sha"]) >= 7
    assert info["subject"] == "feat: add the thing"
    assert info["committed_at"] is not None
    assert info["deployed"] is None  # no stamp file


@pytest.mark.unit
def test_get_version_info_reads_deploy_stamp(tmp_path: Path):
    _init_repo(tmp_path)
    (tmp_path / ".deploy_stamp").write_text("abc1234 | deployed 2026-06-15T04:29:14Z\n", encoding="utf-8")
    info = get_version_info(tmp_path)
    assert info["deployed"] == "abc1234 | deployed 2026-06-15T04:29:14Z"


@pytest.mark.unit
def test_get_version_info_no_git(tmp_path: Path):
    """A non-git directory yields None sha (graceful, no crash)."""
    info = get_version_info(tmp_path)
    assert info["sha"] is None


@pytest.mark.unit
def test_format_version_includes_sha_and_subject(tmp_path: Path):
    _init_repo(tmp_path, subject="fix: a bug")
    out = format_version(tmp_path)
    assert "AtlasMind @" in out
    assert "fix: a bug" in out


@pytest.mark.unit
def test_format_version_unknown_without_git(tmp_path: Path):
    out = format_version(tmp_path)
    assert "unknown" in out.lower()


@pytest.mark.unit
def test_format_version_includes_deploy_stamp(tmp_path: Path):
    _init_repo(tmp_path)
    (tmp_path / ".deploy_stamp").write_text("deadbeef | deployed 2026-06-15T04:29:14Z", encoding="utf-8")
    out = format_version(tmp_path)
    assert "deployed 2026-06-15T04:29:14Z" in out
