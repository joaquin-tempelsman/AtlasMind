"""KB ingestion agent (L3).

One agent per (vault_root, kb_slug), cached in a module-level dict.
Invoked once per batch of RoutedItems for a given KB.
"""
from __future__ import annotations

import json
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from atlasmind.agents.tools.interaction import ask_user
from atlasmind.agents.tools.kb_log import make_kb_log_tools
from atlasmind.agents.tools.kb_meta import _parse_registry
from atlasmind.agents.tools.kb_pages import make_kb_page_tools
from atlasmind.shared.types import RoutedItem

_PROMPT_TEMPLATE = (
    Path(__file__).parent / "prompts" / "kb_ingestion_system.md"
).read_text(encoding="utf-8")

_STANDARD_WORKFLOW = """\
## Standard workflow (follow for EACH item in the batch)

1. Read the item carefully.
2. Search existing pages (search_pages) to find related entities.
3. Create a new note under notes/YYYY-MM-DD-<slug>.md with the required frontmatter.
4. Update entity pages for each named entity (create if absent, per agent.md schema).
5. Update index.md — add one line under the right category (update_index).
6. Append to log.md — use the ingest entry format (append_kb_log).
7. Produce a one-line summary for this item.

After ALL items are processed, call finalize(summary_for_user) exactly once.\
"""

_BREATHING_ADDON = """\

## Breathing step (enabled for this KB)

After filing each note, do ONE additional pass:
Scan the note and the entity pages you touched. If you notice a strong connection
to another existing page in this KB, append a `> [!note] Related` callout to the
new note pointing at it. If nothing notable, skip. Do NOT restructure anything.\
"""

_agent_cache: dict[str, object] = {}
_saver_cache: dict[str, InMemorySaver] = {}


def _cache_key(vault_root: Path, kb_slug: str) -> str:
    return f"{vault_root.resolve()}/{kb_slug}"


def _build_system_prompt(vault_root: Path, kb_slug: str) -> str:
    agent_md_path = vault_root / kb_slug / "agent.md"
    kb_agent_md = (
        agent_md_path.read_text(encoding="utf-8")
        if agent_md_path.exists()
        else f"# {kb_slug} — Ingestion Schema\n(agent.md not found)"
    )
    entries = _parse_registry(vault_root)
    kb_entry = next((e for e in entries if e["slug"] == kb_slug), {})
    breathing = kb_entry.get("breathing", "false") == "true"
    workflow = _STANDARD_WORKFLOW + (_BREATHING_ADDON if breathing else "")
    return _PROMPT_TEMPLATE.format(kb_agent_md=kb_agent_md, standard_workflow=workflow)


def get_agent(
    vault_root: Path, kb_slug: str, model: BaseChatModel | None = None
) -> object:
    """Return the cached KB ingestion agent for (vault_root, kb_slug)."""
    key = _cache_key(vault_root, kb_slug)
    if key not in _agent_cache:
        if model is None:
            model = ChatOpenAI(model="gpt-4o", temperature=0)
        tools = (
            make_kb_page_tools(vault_root, kb_slug)
            + make_kb_log_tools(vault_root, kb_slug)
            + [ask_user]
        )
        saver = InMemorySaver()
        _saver_cache[key] = saver
        _agent_cache[key] = create_agent(
            model,
            tools=tools,
            system_prompt=_build_system_prompt(vault_root, kb_slug),
            checkpointer=saver,
        )
    return _agent_cache[key]


def reset_cache() -> None:
    """Clear agent and saver caches. Call in tests to isolate vault roots."""
    _agent_cache.clear()
    _saver_cache.clear()


def _build_batch_message(vault_root: Path, kb_slug: str, items: list[RoutedItem]) -> str:
    index_path = vault_root / kb_slug / "index.md"
    kb_index = (
        index_path.read_text(encoding="utf-8") if index_path.exists() else "(no index)"
    )
    log_path = vault_root / kb_slug / "log.md"
    if log_path.exists():
        log_lines = log_path.read_text(encoding="utf-8").splitlines()
        kb_recent_log = "\n".join(log_lines[-30:])
    else:
        kb_recent_log = "(no log)"

    items_text = "\n\n---\n\n".join(
        f"**Item {i + 1}** (source: {item.normalized.source_kind}, "
        f"received: {item.normalized.received_at.isoformat()})\n\n{item.normalized.text}"
        for i, item in enumerate(items)
    )
    return (
        f"## Current KB Index\n\n{kb_index}\n\n"
        f"## Recent Log (last 30 lines)\n\n{kb_recent_log}\n\n"
        f"## Items to Ingest ({len(items)} item(s))\n\n{items_text}"
    )


def _extract_finalize_summary(result: dict) -> str:
    for msg in reversed(result.get("messages", [])):
        if isinstance(msg, ToolMessage) and msg.name == "finalize":
            try:
                data = json.loads(msg.content)
                return data.get("summary", "")
            except (json.JSONDecodeError, TypeError):
                return str(msg.content)
    return ""


async def ingest(
    items: list[RoutedItem],
    vault_root: Path,
    thread_id: str,
    model: BaseChatModel | None = None,
) -> dict:
    """Ingest a batch of RoutedItems into their KB.

    Returns {"summary": ...} or {"interrupt_question": ...}.
    All items must share the same kb_slug.
    """
    if not items:
        return {"summary": "No items to ingest."}
    kb_slug = items[0].kb_slug
    agent = get_agent(vault_root, kb_slug, model)
    config = {"configurable": {"thread_id": thread_id}}
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": _build_batch_message(vault_root, kb_slug, items)}]},
        config=config,
    )
    if "__interrupt__" in result:
        question = result["__interrupt__"][0].value.get("question", "")
        return {"interrupt_question": question}
    return {"summary": _extract_finalize_summary(result)}


async def resume_ingest(
    answer: str,
    vault_root: Path,
    kb_slug: str,
    thread_id: str,
    model: BaseChatModel | None = None,
) -> dict:
    """Resume a paused KB ingestion after HITL answer. Same return shape as ingest()."""
    agent = get_agent(vault_root, kb_slug, model)
    config = {"configurable": {"thread_id": thread_id}}
    result = await agent.ainvoke(Command(resume=answer), config=config)
    if "__interrupt__" in result:
        question = result["__interrupt__"][0].value.get("question", "")
        return {"interrupt_question": question}
    return {"summary": _extract_finalize_summary(result)}
