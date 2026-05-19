"""Router agent (L2).

Module-level singleton per vault_root. Routes NormalizedItems to KB slugs
by invoking a LangChain agent with kb_meta tools.
"""
from __future__ import annotations

from pathlib import Path

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from atlasmind.agents.tools.interaction import ask_user
from atlasmind.agents.tools.kb_meta import make_kb_meta_tools
from atlasmind.shared.types import NormalizedItem
from atlasmind.vault import frontmatter as fm

_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "router_system.md").read_text(
    encoding="utf-8"
)

_agent_cache: dict[str, object] = {}
_saver_cache: dict[str, InMemorySaver] = {}


def _cache_key(vault_root: Path) -> str:
    return str(vault_root.resolve())


def get_agent(vault_root: Path, model: BaseChatModel | None = None) -> object:
    """Return the cached router agent, creating it on first call for this vault_root."""
    key = _cache_key(vault_root)
    if key not in _agent_cache:
        if model is None:
            model = ChatOpenAI(model="gpt-4o", temperature=0)
        tools = make_kb_meta_tools(vault_root) + [ask_user]
        saver = InMemorySaver()
        _saver_cache[key] = saver
        _agent_cache[key] = create_agent(
            model,
            tools=tools,
            system_prompt=_SYSTEM_PROMPT,
            checkpointer=saver,
        )
    return _agent_cache[key]


def reset_cache() -> None:
    """Clear the agent and saver caches. Call in tests to isolate vault roots."""
    _agent_cache.clear()
    _saver_cache.clear()


def _last_route(vault_root: Path) -> dict:
    """Read the most recent routing entry from general_log.md."""
    log_path = vault_root / "_meta" / "general_log.md"
    entries = fm.parse_routing_log_entries(log_path.read_text(encoding="utf-8"))
    if not entries:
        raise RuntimeError("Router completed but general_log.md has no entries")
    last = entries[-1]
    return {
        "kb_slug": last["kb_slug"],
        "rationale": last.get("rationale", ""),
        "confidence": last["confidence"],
    }


async def route(
    item: NormalizedItem,
    vault_root: Path,
    thread_id: str,
    model: BaseChatModel | None = None,
) -> dict:
    """Route a NormalizedItem to a KB.

    Returns {"kb_slug": ..., "rationale": ..., "confidence": ...}
    or {"interrupt_question": ...} if the agent asked the user a question.
    """
    agent = get_agent(vault_root, model)
    config = {"configurable": {"thread_id": thread_id}}
    user_msg = (
        f"Source: {item.source_kind}\n"
        f"Received: {item.received_at.isoformat()}\n\n"
        f"{item.text[:1000]}"
    )
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": user_msg}]},
        config=config,
    )
    if "__interrupt__" in result:
        question = result["__interrupt__"][0].value.get("question", "")
        return {"interrupt_question": question}
    return _last_route(vault_root)


async def _resume_agent(agent: object, answer: str, config: dict) -> dict:
    """Inject a ToolMessage for the pending ask_user call instead of a HumanMessage.

    create_agent's Command(resume=...) injects the answer as a HumanMessage, which
    violates OpenAI's rule that every tool_call must be followed by a ToolMessage.
    """
    state = await agent.aget_state(config)
    messages = state.values.get("messages", [])

    pending_id = None
    for msg in reversed(messages):
        for tc in getattr(msg, "tool_calls", []):
            if tc.get("name") == "ask_user":
                pending_id = tc.get("id")
                break
        if pending_id:
            break

    if pending_id:
        tool_msg = ToolMessage(content=answer, tool_call_id=pending_id)
        await agent.aupdate_state(config, {"messages": [tool_msg]}, as_node="tools")
        result = await agent.ainvoke(None, config=config)
    else:
        result = await agent.ainvoke(Command(resume=answer), config=config)

    return result


async def resume_route(
    answer: str,
    vault_root: Path,
    thread_id: str,
    model: BaseChatModel | None = None,
) -> dict:
    """Resume a paused router after HITL answer. Same return shape as route()."""
    agent = get_agent(vault_root, model)
    config = {"configurable": {"thread_id": thread_id}}
    result = await _resume_agent(agent, answer, config)
    if "__interrupt__" in result:
        question = result["__interrupt__"][0].value.get("question", "")
        return {"interrupt_question": question}
    return _last_route(vault_root)
