"""Lint agent — structural audit for a single KB.

Triggered by the /lint <kb_slug> Telegram command.
One agent per (vault_root, kb_slug), cached in a module-level dict.
No HITL, no checkpointer — lint is a one-shot read-heavy pass.
"""
from __future__ import annotations

import json
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_openai import ChatOpenAI

from atlasmind.agents.tools.kb_lint import make_kb_lint_tools
from atlasmind.agents.tools.kb_pages import make_kb_page_tools

_PROMPT_TEMPLATE = (
    Path(__file__).parent / "prompts" / "lint_system.md"
).read_text(encoding="utf-8")

_agent_cache: dict[str, object] = {}


def _cache_key(vault_root: Path, kb_slug: str) -> str:
    return f"{vault_root.resolve()}/{kb_slug}"


def _build_system_prompt(kb_slug: str) -> str:
    return _PROMPT_TEMPLATE.format(kb_slug=kb_slug)


def get_agent(
    vault_root: Path,
    kb_slug: str,
    model: BaseChatModel | None = None,
) -> object:
    """Return the cached lint agent for (vault_root, kb_slug)."""
    key = _cache_key(vault_root, kb_slug)
    if key not in _agent_cache:
        if model is None:
            model = ChatOpenAI(model="gpt-4o", temperature=0)

        tools = make_kb_page_tools(vault_root, kb_slug) + make_kb_lint_tools(vault_root, kb_slug)

        _agent_cache[key] = create_agent(
            model,
            tools=tools,
            system_prompt=_build_system_prompt(kb_slug),
        )
    return _agent_cache[key]


def reset_cache() -> None:
    """Clear agent cache. Call in tests to isolate vault roots."""
    _agent_cache.clear()


def _extract_finalize_summary(result: dict) -> str:
    for msg in reversed(result.get("messages", [])):
        if isinstance(msg, ToolMessage) and msg.name == "finalize_lint":
            try:
                data = json.loads(msg.content)
                return data.get("summary", "")
            except (json.JSONDecodeError, TypeError):
                return str(msg.content)
    return ""


async def run(
    vault_root: Path,
    kb_slug: str,
    thread_id: str,
    model: BaseChatModel | None = None,
) -> dict:
    """Run a lint audit on kb_slug. Returns {"summary": str}.

    No HITL — the agent runs autonomously to completion.
    thread_id is used only for the agent invocation config.
    """
    agent = get_agent(vault_root, kb_slug, model)
    config = {"configurable": {"thread_id": thread_id}}
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": f"Run lint on KB: {kb_slug}"}]},
        config=config,
    )
    return {"summary": _extract_finalize_summary(result)}
