"""Entity registry tools for a KB.

Provides register_entity — bound to a specific (vault_root, kb_slug) pair.
The entity registry lives at <kb_slug>/entities.md (scaffolded by bootstrap).
"""
from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool


def make_kb_entity_tools(vault_root: Path, kb_slug: str) -> list:
    """Return entity registry tools bound to vault_root/kb_slug."""
    entities_path = vault_root / kb_slug / "entities.md"

    @tool
    def register_entity(canonical_name: str, aliases: list[str]) -> str:
        """Add or update an entity in the KB entity registry.

        canonical_name is the authoritative page name (e.g. 'Thomas Piketty').
        aliases is a list of alternate references (e.g. ['Piketty', 'T. Piketty']).
        Call this after creating a new entity page not already in the registry.
        """
        if not entities_path.exists():
            return "(entities.md not found; skipping registration)"

        text = entities_path.read_text(encoding="utf-8")
        canonical_lower = canonical_name.strip().lower()
        lines = text.splitlines(keepends=True)

        new_lines: list[str] = []
        found = False

        for line in lines:
            stripped = line.rstrip("\n\r")
            parts = [p.strip() for p in stripped.split("|")]
            if parts and parts[0].lower() == canonical_lower and parts[0].strip():
                # Merge aliases into existing entry
                existing_aliases = {p for p in parts[1:] if p}
                merged = sorted(existing_aliases | set(aliases))
                entry = canonical_name if not merged else f"{canonical_name} | {' | '.join(merged)}"
                new_lines.append(entry + "\n")
                found = True
            else:
                new_lines.append(line)

        if not found:
            content = "".join(new_lines)
            sep = "" if content.endswith("\n") else "\n"
            alias_part = f" | {' | '.join(aliases)}" if aliases else ""
            entities_path.write_text(
                content + sep + canonical_name + alias_part + "\n",
                encoding="utf-8",
            )
        else:
            entities_path.write_text("".join(new_lines), encoding="utf-8")

        return f"Registered: {canonical_name}"

    return [register_entity]
