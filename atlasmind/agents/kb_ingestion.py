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
from atlasmind.agents.tools.kb_entities import make_kb_entity_tools
from atlasmind.agents.tools.kb_log import make_kb_log_tools
from atlasmind.agents.tools.kb_meta import _parse_registry
from atlasmind.agents.tools.kb_pages import make_kb_page_tools
from atlasmind.agents.tools.url_metadata import make_extract_url_metadata_tool
from atlasmind.ingestion.link_fetcher import ReadabilityLinkFetcher
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

_ENTITY_RESOLUTION_ADDON = """\

## Entity Resolution

Before creating or updating any entity page:
1. Check the "Entity Registry" section in your context.
2. If a referenced name matches a known alias, use the canonical name for the
   page path and title (e.g., if "Piketty" maps to "Thomas Piketty", create
   or update people/thomas-piketty.md — not people/piketty.md).
3. After creating a new entity page not already in the registry, call
   register_entity() to log the canonical name and any aliases you observed.\
"""

_BREATHING_ADDON = """\

## Breathing step (enabled for this KB)

After filing each note, do ONE additional pass:
Scan the note and the entity pages you touched. If you notice a strong connection
to another existing page in this KB, append a `> [!note] Related` callout to the
new note pointing at it. If nothing notable, skip. Do NOT restructure anything.\
"""

_URL_METADATA_ADDON = """\

## URL metadata extraction (enabled for this KB)

This KB is configured to extract structured metadata from linked articles.
Metadata fields to extract: {fields}.

For any item where source_kind="link", OR any voice/text item whose batch entry
notes "linked_url", call extract_url_metadata(url=<url>, fields={fields_repr})
BEFORE creating the note. Include the returned values in the note's frontmatter
under the appropriate field names. Do not guess metadata — only use what the tool returns.\
"""

_agent_cache: dict[str, object] = {}
_saver_cache: dict[str, InMemorySaver] = {}


def _parse_url_metadata_fields(kb_entry: dict) -> list[str]:
    """Return the list of URL metadata fields from a registry KB entry."""
    raw = kb_entry.get("url_metadata_fields", "")
    return [f.strip() for f in raw.split(",") if f.strip()]


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
    url_fields = _parse_url_metadata_fields(kb_entry)

    workflow = _STANDARD_WORKFLOW + _ENTITY_RESOLUTION_ADDON + (_BREATHING_ADDON if breathing else "")
    if url_fields:
        fields_repr = str(url_fields)
        workflow += _URL_METADATA_ADDON.format(
            fields=", ".join(url_fields),
            fields_repr=fields_repr,
        )

    return _PROMPT_TEMPLATE.format(kb_agent_md=kb_agent_md, standard_workflow=workflow)


def get_agent(
    vault_root: Path,
    kb_slug: str,
    model: BaseChatModel | None = None,
    link_fetcher=None,
) -> object:
    """Return the cached KB ingestion agent for (vault_root, kb_slug)."""
    key = _cache_key(vault_root, kb_slug)
    if key not in _agent_cache:
        if model is None:
            model = ChatOpenAI(model="gpt-4o", temperature=0)

        entries = _parse_registry(vault_root)
        kb_entry = next((e for e in entries if e["slug"] == kb_slug), {})
        url_fields = _parse_url_metadata_fields(kb_entry)

        tools = (
            make_kb_page_tools(vault_root, kb_slug)
            + make_kb_log_tools(vault_root, kb_slug)
            + make_kb_entity_tools(vault_root, kb_slug)
            + [ask_user]
        )
        if url_fields:
            fetcher = link_fetcher or ReadabilityLinkFetcher()
            tools = tools + [make_extract_url_metadata_tool(fetcher)]

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

    entries = _parse_registry(vault_root)
    kb_entry = next((e for e in entries if e["slug"] == kb_slug), {})
    include_content = kb_entry.get("include_article_content", "false") == "true"

    item_blocks: list[str] = []
    for i, item in enumerate(items):
        n = item.normalized
        header = (
            f"**Item {i + 1}** (source: {n.source_kind}, "
            f"received: {n.received_at.isoformat()})"
        )
        body = n.text

        if n.source_kind == "link" and include_content:
            raw_text = n.source_meta.get("raw_article_text", "")
            if raw_text:
                body = body + f"\n\n**Full article content:**\n\n{raw_text}"

        linked_url = n.source_meta.get("linked_url")
        if linked_url:
            body = body + f"\n\n_This item is commentary on: {linked_url}_"

        item_blocks.append(f"{header}\n\n{body}")

    entities_path = vault_root / kb_slug / "entities.md"
    entities_section = (
        f"\n\n## Entity Registry\n\n{entities_path.read_text(encoding='utf-8')}"
        if entities_path.exists()
        else ""
    )

    items_text = "\n\n---\n\n".join(item_blocks)
    return (
        f"## Current KB Index\n\n{kb_index}\n\n"
        f"## Recent Log (last 30 lines)\n\n{kb_recent_log}"
        + entities_section
        + f"\n\n## Items to Ingest ({len(items)} item(s))\n\n{items_text}"
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
    link_fetcher=None,
) -> dict:
    """Ingest a batch of RoutedItems into their KB.

    Returns {"summary": ...} or {"interrupt_question": ...}.
    All items must share the same kb_slug.
    """
    if not items:
        return {"summary": "No items to ingest."}
    kb_slug = items[0].kb_slug
    agent = get_agent(vault_root, kb_slug, model, link_fetcher=link_fetcher)
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
