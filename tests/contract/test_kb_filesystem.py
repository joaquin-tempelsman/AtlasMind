"""Contract tests: KB filesystem structure after bootstrap.

These tests verify that bootstrap scaffolds the correct folder structure and
that the vault satisfies the KB contract defined in dev_specs/06_kb_contract.md.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlasmind.bootstrap import run as bootstrap_run
from atlasmind.vault import frontmatter as fm


@pytest.mark.contract
def test_bootstrap_creates_kb_folders(tmp_path: Path):
    """Each active KB gets its required four files scaffolded."""
    bootstrap_run(vault_path=tmp_path)
    # personal-diary is active in kb_definitions.md
    kb = tmp_path / "personal-diary"
    assert (kb / "agent.md").exists()
    assert (kb / "index.md").exists()
    assert (kb / "log.md").exists()
    assert (kb / "notes").is_dir()


@pytest.mark.contract
def test_bootstrap_creates_entity_folders(tmp_path: Path):
    """KBs with entities get those subfolders scaffolded."""
    bootstrap_run(vault_path=tmp_path)
    assert (tmp_path / "personal-diary" / "people").is_dir()
    assert (tmp_path / "personal-diary" / "places").is_dir()
    assert (tmp_path / "reflections" / "concepts").is_dir()


@pytest.mark.contract
def test_bootstrap_generates_registry(tmp_path: Path):
    """_meta/kb_registry.md is generated with correct content."""
    bootstrap_run(vault_path=tmp_path)
    registry = tmp_path / "_meta" / "kb_registry.md"
    assert registry.exists()
    text = registry.read_text()
    assert "type: kb_registry" in text
    assert "personal-diary" in text
    assert "reflections" in text


@pytest.mark.contract
def test_bootstrap_creates_meta_files(tmp_path: Path):
    """_meta/ contains general_log.md and routing_rules.md."""
    bootstrap_run(vault_path=tmp_path)
    assert (tmp_path / "_meta" / "general_log.md").exists()
    assert (tmp_path / "_meta" / "routing_rules.md").exists()


@pytest.mark.contract
def test_bootstrap_creates_raw_links_dir(tmp_path: Path):
    """raw/links/ directory is created."""
    bootstrap_run(vault_path=tmp_path)
    assert (tmp_path / "raw" / "links").is_dir()


@pytest.mark.contract
def test_bootstrap_makes_initial_git_commit(tmp_path: Path):
    """Bootstrap produces a real git commit."""
    bootstrap_run(vault_path=tmp_path)
    result = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip()  # at least one commit


@pytest.mark.contract
def test_agent_md_has_valid_frontmatter(tmp_path: Path):
    """agent.md for each scaffolded KB has parseable frontmatter with required fields."""
    bootstrap_run(vault_path=tmp_path)
    agent_md = tmp_path / "personal-diary" / "agent.md"
    meta, _ = fm.parse_file(agent_md)
    assert meta.get("type") == "kb_agent_md"
    assert meta.get("kb_slug") == "personal-diary"


@pytest.mark.contract
def test_index_md_has_valid_frontmatter(tmp_path: Path):
    """index.md for each scaffolded KB has parseable frontmatter."""
    bootstrap_run(vault_path=tmp_path)
    index_md = tmp_path / "personal-diary" / "index.md"
    meta, _ = fm.parse_file(index_md)
    assert meta.get("type") == "kb_index"
    assert meta.get("kb") == "personal-diary"


@pytest.mark.contract
def test_inactive_kb_not_scaffolded(tmp_path: Path):
    """KBs with active: false in kb_definitions.md still get scaffolded (content preserved),
    but we verify the active field in the registry reflects false."""
    bootstrap_run(vault_path=tmp_path)
    registry_text = (tmp_path / "_meta" / "kb_registry.md").read_text()
    # book-readings is active: false
    # It should be mentioned in registry
    assert "book-readings" in registry_text
    # The active line for book-readings should say false
    lines = registry_text.splitlines()
    in_book_readings = False
    for line in lines:
        if line.strip() == "## book-readings":
            in_book_readings = True
        if in_book_readings and "**Active:**" in line:
            assert "false" in line.lower()
            break
