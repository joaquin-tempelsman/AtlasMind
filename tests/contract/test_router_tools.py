"""Contract tests: router tools (kb_meta + interaction).

Spec: dev_specs/05_agent_layer.md §2 — Router tools
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atlasmind.agents.tools.interaction import ask_user
from atlasmind.agents.tools.kb_meta import make_kb_meta_tools
from atlasmind.vault.frontmatter import format_routing_log_entry


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_tool(tools: list, name: str):
    return next(t for t in tools if t.name == name)


def _append_log_entry(vault: Path, **kwargs) -> None:
    entry = format_routing_log_entry(**kwargs)
    log = vault / "_meta" / "general_log.md"
    with log.open("a", encoding="utf-8") as f:
        f.write("\n" + entry)


# ── list_kbs ──────────────────────────────────────────────────────────────────

@pytest.mark.contract
def test_list_kbs_returns_active_kbs(bootstrapped_vault: Path):
    tools = make_kb_meta_tools(bootstrapped_vault)
    result = _get_tool(tools, "list_kbs").invoke({})
    assert isinstance(result, list)
    slugs = [kb["slug"] for kb in result]
    assert "personal-diary" in slugs
    assert "reflections" in slugs
    assert "econ-politics" in slugs


@pytest.mark.contract
def test_list_kbs_excludes_inactive(bootstrapped_vault: Path):
    tools = make_kb_meta_tools(bootstrapped_vault)
    result = _get_tool(tools, "list_kbs").invoke({})
    slugs = [kb["slug"] for kb in result]
    # book-readings and work-ml are active: false in kb_definitions.md
    assert "book-readings" not in slugs
    assert "work-ml" not in slugs


@pytest.mark.contract
def test_list_kbs_has_name_and_description(bootstrapped_vault: Path):
    tools = make_kb_meta_tools(bootstrapped_vault)
    result = _get_tool(tools, "list_kbs").invoke({})
    for kb in result:
        assert "slug" in kb
        assert "name" in kb
        assert "description" in kb


# ── commit_route ──────────────────────────────────────────────────────────────

@pytest.mark.contract
def test_commit_route_known_slug_succeeds(bootstrapped_vault: Path):
    tools = make_kb_meta_tools(bootstrapped_vault)
    result = _get_tool(tools, "commit_route").invoke(
        {"kb_slug": "personal-diary", "rationale": "Real event with a friend.", "confidence": "high"}
    )
    assert result["ok"] is True
    assert result["kb_slug"] == "personal-diary"


@pytest.mark.contract
def test_commit_route_appends_to_general_log(bootstrapped_vault: Path):
    tools = make_kb_meta_tools(bootstrapped_vault)
    _get_tool(tools, "commit_route").invoke(
        {"kb_slug": "reflections", "rationale": "Abstract idea.", "confidence": "medium"}
    )
    log_text = (bootstrapped_vault / "_meta" / "general_log.md").read_text()
    assert "reflections" in log_text
    assert "medium" in log_text
    assert "Abstract idea." in log_text


@pytest.mark.contract
def test_commit_route_unknown_slug_returns_error(bootstrapped_vault: Path):
    """Unknown slug must return error dict, not raise."""
    tools = make_kb_meta_tools(bootstrapped_vault)
    result = _get_tool(tools, "commit_route").invoke(
        {"kb_slug": "does-not-exist", "rationale": "test", "confidence": "high"}
    )
    assert result["ok"] is False
    assert "does-not-exist" in result["error"]


@pytest.mark.contract
def test_commit_route_invalid_confidence_returns_error(bootstrapped_vault: Path):
    tools = make_kb_meta_tools(bootstrapped_vault)
    result = _get_tool(tools, "commit_route").invoke(
        {"kb_slug": "personal-diary", "rationale": "test", "confidence": "very-sure"}
    )
    assert result["ok"] is False


# ── read_recent_routing (stratified sampling) ─────────────────────────────────

@pytest.mark.contract
def test_stratified_sampling_guarantees_one_per_kb(bootstrapped_vault: Path):
    """With n=2 and 2 active KBs that each have ≥1 entry, result has one entry per KB."""
    # 5 entries for personal-diary, 1 for reflections
    for i in range(5):
        _append_log_entry(
            vault=bootstrapped_vault,
            ts=f"2026-05-0{i + 1}T12:00:00Z",
            kb_slug="personal-diary",
            confidence="high",
            source="voice",
            preview=f"Entry {i}",
            rationale=f"Rationale {i}",
            file_path="",
        )
    _append_log_entry(
        vault=bootstrapped_vault,
        ts="2026-05-06T12:00:00Z",
        kb_slug="reflections",
        confidence="medium",
        source="text",
        preview="Reflection",
        rationale="Abstract",
        file_path="",
    )

    tools = make_kb_meta_tools(bootstrapped_vault)
    result = _get_tool(tools, "read_recent_routing").invoke({"n": 2})

    assert len(result) == 2
    slugs = [e["kb_slug"] for e in result]
    assert "personal-diary" in slugs
    assert "reflections" in slugs


@pytest.mark.contract
def test_stratified_sampling_does_not_exceed_n(bootstrapped_vault: Path):
    """Total results never exceed n."""
    for i in range(10):
        _append_log_entry(
            vault=bootstrapped_vault,
            ts=f"2026-05-{i + 1:02d}T12:00:00Z",
            kb_slug="personal-diary",
            confidence="high",
            source="voice",
            preview=f"Entry {i}",
            rationale="Rationale",
            file_path="",
        )

    tools = make_kb_meta_tools(bootstrapped_vault)
    result = _get_tool(tools, "read_recent_routing").invoke({"n": 3})
    assert len(result) <= 3


@pytest.mark.contract
def test_read_routing_rules_returns_string(bootstrapped_vault: Path):
    tools = make_kb_meta_tools(bootstrapped_vault)
    result = _get_tool(tools, "read_routing_rules").invoke({})
    assert isinstance(result, str)


# ── ask_user ──────────────────────────────────────────────────────────────────

@pytest.mark.contract
def test_ask_user_is_a_valid_tool():
    assert ask_user.name == "ask_user"
    assert ask_user.description
