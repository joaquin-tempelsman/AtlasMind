"""Shared pytest fixtures."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlasmind.bootstrap import run as bootstrap_run


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    """An empty git-initialised vault directory."""
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        check=True, capture_output=True, cwd=str(tmp_path),
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        check=True, capture_output=True, cwd=str(tmp_path),
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        check=True, capture_output=True, cwd=str(tmp_path),
    )
    return tmp_path


@pytest.fixture()
def bootstrapped_vault(tmp_path: Path) -> Path:
    """A fully bootstrapped vault with all KBs from kb_definitions.md scaffolded."""
    bootstrap_run(vault_path=tmp_path)
    return tmp_path
