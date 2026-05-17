"""
Reads kb_definitions/kb_definitions.md, initialises the vault at VAULT_REPO_PATH,
scaffolds KB folders, and generates _meta/kb_registry.md.

Run as: python -m atlasmind.bootstrap
"""
from __future__ import annotations

import subprocess
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import yaml

from atlasmind.config import KB_DEFINITIONS_PATH, VAULT_REPO_PATH


def _load_kb_definitions() -> list[dict]:
    text = KB_DEFINITIONS_PATH.read_text(encoding="utf-8")
    # Extract the outermost ```yaml ... ``` block.
    # Only match fences at column 0 to avoid matching nested fences inside agent_md literals.
    lines = text.splitlines()
    yaml_lines: list[str] = []
    in_yaml = False
    for line in lines:
        if not in_yaml and line == "```yaml":
            in_yaml = True
            continue
        if in_yaml and line == "```":
            break  # end of outer fence — done
        if in_yaml:
            yaml_lines.append(line)
    data = yaml.safe_load("\n".join(yaml_lines))
    return data.get("kbs", [])


def _git_init(path: Path) -> None:
    if not (path / ".git").exists():
        subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "chore: init vault"],
            check=True,
            capture_output=True,
            cwd=str(path),
        )


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def _scaffold_kb(vault: Path, kb: dict) -> None:
    slug = kb["slug"]
    name = kb.get("name", slug)
    kb_root = vault / slug

    agent_md = kb.get("agent_md") or textwrap.dedent(f"""\
        ---
        type: kb_agent_md
        kb_slug: {slug}
        version: 1
        ---

        # {name} — Ingestion Schema

        ## What belongs here
        (Edit this section to describe what belongs in this KB.)

        ## Folder layout
        - notes/    — one file per ingestion event
        """)

    _write_file(
        kb_root / "agent.md",
        agent_md.strip() + "\n",
    )

    _write_file(
        kb_root / "index.md",
        textwrap.dedent(f"""\
            ---
            type: kb_index
            kb: {slug}
            last_updated: {datetime.now(timezone.utc).date().isoformat()}
            ---

            # {name} — Index

            ## Notes
            """),
    )

    _write_file(
        kb_root / "log.md",
        textwrap.dedent(f"""\
            ---
            type: kb_log
            kb: {slug}
            ---

            # {name} — Log

            """),
    )

    _write_file(
        kb_root / "entities.md",
        textwrap.dedent(f"""\
            ---
            type: kb_entity_registry
            kb: {slug}
            ---

            # Entity Registry

            Each line: Canonical Name | alias1 | alias2 | ...
            Edit this file in Obsidian or via the vault repo to pre-define entities.
            The ingestion agent uses canonical names when creating entity pages.

            ---
            """),
    )

    (kb_root / "notes").mkdir(parents=True, exist_ok=True)
    (kb_root / "notes" / ".gitkeep").touch()

    for entity_folder in kb.get("entities", []):
        folder = kb_root / entity_folder
        folder.mkdir(parents=True, exist_ok=True)
        (folder / ".gitkeep").touch()


def _generate_registry(vault: Path, kbs: list[dict]) -> None:
    lines = [
        "---",
        "type: kb_registry",
        "version: 1",
        "generated_from: kb_definitions/kb_definitions.md",
        "---",
        "",
        "# KB Registry",
        "",
    ]
    for kb in kbs:
        slug = kb["slug"]
        lines.append(f"## {slug}")
        lines.append(f"- **Name:** {kb.get('name', slug)}")
        desc = kb.get("description", "").strip().replace("\n", " ")
        lines.append(f"- **Description:** {desc}")
        entities = ", ".join(kb.get("entities", []))
        if entities:
            lines.append(f"- **Entities:** {entities}")
        lines.append(f"- **Active:** {str(kb.get('active', True)).lower()}")
        lines.append(f"- **Breathing:** {str(kb.get('breathing', False)).lower()}")
        lines.append(f"- **Ingest delay (min):** {kb.get('ingest_delay_minutes', 5)}")
        url_fields = kb.get("url_metadata_fields") or []
        lines.append(f"- **URL metadata fields:** {', '.join(url_fields)}")
        lines.append(f"- **Include article content:** {str(kb.get('include_article_content', False)).lower()}")
        lines.append("")

    meta = vault / "_meta"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "kb_registry.md").write_text("\n".join(lines), encoding="utf-8")

    for fname, content in [
        ("general_log.md", "# General Routing Log\n\n"),
        ("routing_rules.md", "# Routing Rules\n\n"),
    ]:
        _write_file(meta / fname, content)


def _scaffold_raw(vault: Path) -> None:
    links_dir = vault / "raw" / "links"
    links_dir.mkdir(parents=True, exist_ok=True)
    (links_dir / ".gitkeep").touch()


def _initial_commit(vault: Path) -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=str(vault),
    )
    if result.stdout.strip():
        subprocess.run(["git", "add", "-A"], check=True, cwd=str(vault))
        subprocess.run(
            ["git", "commit", "-m", "chore: scaffold vault from kb_definitions"],
            check=True,
            cwd=str(vault),
        )


def run(vault_path: Path | None = None) -> None:
    vault = vault_path or VAULT_REPO_PATH
    vault.mkdir(parents=True, exist_ok=True)

    kbs = _load_kb_definitions()
    _git_init(vault)
    for kb in kbs:
        _scaffold_kb(vault, kb)
    _generate_registry(vault, kbs)
    _scaffold_raw(vault)
    _initial_commit(vault)

    active = [kb["slug"] for kb in kbs if kb.get("active", True)]
    print(f"Vault bootstrapped at {vault}")
    print(f"Active KBs: {', '.join(active)}")


if __name__ == "__main__":
    run()
