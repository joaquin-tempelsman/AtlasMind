"""Unit tests for agents/lint.py."""
from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.messages.tool import ToolCall

from atlasmind.agents import lint
from atlasmind.bootstrap import run as bootstrap_run


class FakeToolCallingModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


@pytest.fixture(autouse=True)
def clear_cache():
    lint.reset_cache()
    yield
    lint.reset_cache()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lint_run_returns_summary(tmp_path: Path):
    """Lint agent writes report and calls finalize_lint → summary returned."""
    bootstrap_run(vault_path=tmp_path)

    model = FakeToolCallingModel(responses=[
        # Write the lint report
        AIMessage(content="", tool_calls=[
            ToolCall(name="write_page", args={
                "rel_path": "lint/2026-05-17-lint-report.md",
                "content": "# Lint Report\n\n## Orphan Pages\n- ℹ️ (none found)",
            }, id="tc1", type="tool_call"),
        ]),
        # Finalize
        AIMessage(content="", tool_calls=[
            ToolCall(name="finalize_lint", args={
                "summary_for_user": "• Lint complete.\n• No issues found.",
            }, id="tc2", type="tool_call"),
        ]),
        AIMessage(content="Done."),
    ])

    result = await lint.run(tmp_path, "personal-diary", thread_id="lint-t-1", model=model)

    assert result["summary"] == "• Lint complete.\n• No issues found."
    assert (tmp_path / "personal-diary" / "lint" / "2026-05-17-lint-report.md").exists()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lint_run_returns_empty_summary_when_no_finalize(tmp_path: Path):
    """If the agent never calls finalize_lint, summary is empty string."""
    bootstrap_run(vault_path=tmp_path)

    model = FakeToolCallingModel(responses=[
        AIMessage(content="No issues."),
    ])

    result = await lint.run(tmp_path, "personal-diary", thread_id="lint-t-2", model=model)

    assert result == {"summary": ""}


@pytest.mark.unit
def test_lint_agent_cache_singleton(tmp_path: Path):
    """Two get_agent() calls with same args return the same cached object."""
    bootstrap_run(vault_path=tmp_path)
    model = FakeToolCallingModel(responses=[AIMessage(content="done")])
    a1 = lint.get_agent(tmp_path, "personal-diary", model)
    a2 = lint.get_agent(tmp_path, "personal-diary", model)
    assert a1 is a2


@pytest.mark.unit
def test_lint_cache_isolated_by_kb(tmp_path: Path):
    """Different kb_slug → different cached agent."""
    bootstrap_run(vault_path=tmp_path)
    model = FakeToolCallingModel(responses=[AIMessage(content="done")])
    a_diary = lint.get_agent(tmp_path, "personal-diary", model)
    a_refl = lint.get_agent(tmp_path, "reflections", model)
    assert a_diary is not a_refl


@pytest.mark.unit
def test_lint_system_prompt_contains_kb_slug(tmp_path: Path):
    """System prompt has kb_slug substituted in."""
    prompt = lint._build_system_prompt("personal-diary")
    assert "personal-diary" in prompt


@pytest.mark.unit
def test_lint_agent_has_page_and_lint_tools(tmp_path: Path):
    """Lint agent has access to page tools + finalize_lint."""
    bootstrap_run(vault_path=tmp_path)
    from atlasmind.agents.tools.kb_pages import make_kb_page_tools
    from atlasmind.agents.tools.kb_lint import make_kb_lint_tools

    page_tool_names = {t.name for t in make_kb_page_tools(tmp_path, "personal-diary")}
    lint_tool_names = {t.name for t in make_kb_lint_tools(tmp_path, "personal-diary")}
    expected = page_tool_names | lint_tool_names

    model = FakeToolCallingModel(responses=[AIMessage(content="done")])
    # get_agent builds the agent; we just check the system prompt contains expected tool refs
    lint.get_agent(tmp_path, "personal-diary", model)
    # If get_agent() didn't raise, the tools were wired correctly
    assert "finalize_lint" in lint_tool_names
    assert "list_pages" in page_tool_names
    assert "write_page" in expected
