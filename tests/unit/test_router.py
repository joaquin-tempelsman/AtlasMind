"""Unit tests for agents/router.py."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.messages.tool import ToolCall

from atlasmind.agents import router
from atlasmind.bootstrap import run as bootstrap_run
from atlasmind.shared.types import NormalizedItem


class FakeToolCallingModel(FakeMessagesListChatModel):
    """Fake chat model that supports bind_tools (ignores tools, returns canned responses)."""

    def bind_tools(self, tools, **kwargs):
        return self


def _item(text: str = "Met a friend at a café.") -> NormalizedItem:
    return NormalizedItem(
        received_at=datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc),
        text=text,
        source_kind="voice",
        source_meta={},
        telegram_user_id=1,
    )


@pytest.fixture(autouse=True)
def clear_cache():
    router.reset_cache()
    yield
    router.reset_cache()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_happy_path(tmp_path: Path):
    """Router commits a route and returns kb_slug/rationale/confidence."""
    bootstrap_run(vault_path=tmp_path)

    model = FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[
            ToolCall(name="list_kbs", args={}, id="tc1", type="tool_call"),
        ]),
        AIMessage(content="", tool_calls=[
            ToolCall(name="commit_route", args={
                "kb_slug": "personal-diary",
                "rationale": "Real-world encounter.",
                "confidence": "high",
            }, id="tc2", type="tool_call"),
        ]),
        AIMessage(content="Routed to personal-diary."),
    ])

    result = await router.route(_item(), tmp_path, "thread-1", model=model)

    assert result["kb_slug"] == "personal-diary"
    assert result["confidence"] == "high"
    assert "encounter" in result["rationale"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_writes_to_general_log(tmp_path: Path):
    """commit_route side-effect: general_log.md gets a new entry."""
    bootstrap_run(vault_path=tmp_path)

    model = FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[
            ToolCall(name="commit_route", args={
                "kb_slug": "reflections",
                "rationale": "Abstract idea.",
                "confidence": "medium",
            }, id="tc1", type="tool_call"),
        ]),
        AIMessage(content="Done."),
    ])

    await router.route(_item("Deep thoughts about life."), tmp_path, "thread-2", model=model)

    log = (tmp_path / "_meta" / "general_log.md").read_text()
    assert "reflections" in log
    assert "medium" in log


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_returns_interrupt_question(tmp_path: Path):
    """When agent calls ask_user, route() returns {interrupt_question: ...}."""
    bootstrap_run(vault_path=tmp_path)

    model = FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[
            ToolCall(name="ask_user", args={"question": "Is this diary or reflections?"},
                     id="tc1", type="tool_call"),
        ]),
        # This response would be returned after resume, not checked here
        AIMessage(content=""),
    ])

    result = await router.route(_item(), tmp_path, "thread-3", model=model)

    assert "interrupt_question" in result
    assert "diary or reflections" in result["interrupt_question"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resume_route_completes(tmp_path: Path):
    """After HITL, resume_route() completes the routing."""
    bootstrap_run(vault_path=tmp_path)
    thread_id = "thread-4"

    # First call: interrupt
    interrupt_model = FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[
            ToolCall(name="ask_user", args={"question": "Diary or reflections?"},
                     id="tc1", type="tool_call"),
        ]),
    ])
    await router.route(_item(), tmp_path, thread_id, model=interrupt_model)

    # resume_route uses the cached agent (which has the InMemorySaver state)
    # The model now returns a commit_route after resume
    # We need to update the model's responses for the resume call
    router.get_agent(tmp_path)
    # Re-inject responses into the underlying model — get it from the agent graph
    # Simpler: just provide a fresh model bound to the same cached agent
    # Actually the cached agent holds a reference to the original model.
    # For this test, pre-seed with enough responses including the resume path.
    router.reset_cache()

    model = FakeToolCallingModel(responses=[
        # First invoke (route call): interrupt
        AIMessage(content="", tool_calls=[
            ToolCall(name="ask_user", args={"question": "Which KB?"}, id="tc1", type="tool_call"),
        ]),
        # After resume: commit
        AIMessage(content="", tool_calls=[
            ToolCall(name="commit_route", args={
                "kb_slug": "personal-diary",
                "rationale": "User confirmed.",
                "confidence": "high",
            }, id="tc2", type="tool_call"),
        ]),
        AIMessage(content="Routed."),
    ])

    await router.route(_item(), tmp_path, thread_id, model=model)
    result = await router.resume_route("personal-diary", tmp_path, thread_id, model=model)

    assert result["kb_slug"] == "personal-diary"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_router_agent_is_cached(tmp_path: Path):
    """Two calls to get_agent with the same vault_root return the same object."""
    bootstrap_run(vault_path=tmp_path)
    model = FakeToolCallingModel(responses=[AIMessage(content="done")])
    a1 = router.get_agent(tmp_path, model)
    a2 = router.get_agent(tmp_path, model)
    assert a1 is a2
