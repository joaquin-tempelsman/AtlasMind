"""Contract tests: router and KB ingestion agents.

Spec: dev_specs/05_agent_layer.md §2, §3
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.messages.tool import ToolCall

from atlasmind.agents import kb_ingestion, router
from atlasmind.bootstrap import run as bootstrap_run
from atlasmind.shared.types import NormalizedItem, RoutedItem


class FakeToolCallingModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def _item(text: str = "Had coffee with Mateo.") -> NormalizedItem:
    return NormalizedItem(
        received_at=datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc),
        text=text,
        source_kind="voice",
        source_meta={},
        telegram_user_id=1,
    )


def _routed(text: str = "Had coffee with Mateo.", kb_slug: str = "personal-diary") -> RoutedItem:
    return RoutedItem(
        normalized=_item(text),
        kb_slug=kb_slug,
        routing_rationale="Real event.",
        confidence="high",
    )


@pytest.fixture(autouse=True)
def reset_caches():
    router.reset_cache()
    kb_ingestion.reset_cache()
    yield
    router.reset_cache()
    kb_ingestion.reset_cache()


# ── router contract ────────────────────────────────────────────────────────────

@pytest.mark.contract
@pytest.mark.asyncio
async def test_router_commits_route_to_log(bootstrapped_vault: Path):
    """Router agent's commit_route call persists to general_log.md."""
    model = FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[
            ToolCall(name="commit_route", args={
                "kb_slug": "personal-diary",
                "rationale": "Real event with a friend.",
                "confidence": "high",
            }, id="tc1", type="tool_call"),
        ]),
        AIMessage(content="Routed."),
    ])
    result = await router.route(_item(), bootstrapped_vault, "contract-r1", model=model)

    assert result["kb_slug"] == "personal-diary"
    log = (bootstrapped_vault / "_meta" / "general_log.md").read_text()
    assert "personal-diary" in log
    assert "Real event with a friend." in log


@pytest.mark.contract
@pytest.mark.asyncio
async def test_router_interrupt_flow(bootstrapped_vault: Path):
    """Router HITL: interrupt → resume → commit_route."""
    thread_id = "contract-r-hitl"
    model = FakeToolCallingModel(responses=[
        # First turn: interrupt
        AIMessage(content="", tool_calls=[
            ToolCall(name="ask_user", args={"question": "Diary or reflections?"},
                     id="tc1", type="tool_call"),
        ]),
        # After resume: commit
        AIMessage(content="", tool_calls=[
            ToolCall(name="commit_route", args={
                "kb_slug": "reflections",
                "rationale": "User confirmed reflective.",
                "confidence": "high",
            }, id="tc2", type="tool_call"),
        ]),
        AIMessage(content="Done."),
    ])

    r1 = await router.route(_item(), bootstrapped_vault, thread_id, model=model)
    assert "interrupt_question" in r1

    r2 = await router.resume_route("reflections", bootstrapped_vault, thread_id, model=model)
    assert r2["kb_slug"] == "reflections"


# ── KB ingestion contract ──────────────────────────────────────────────────────

@pytest.mark.contract
@pytest.mark.asyncio
async def test_kb_ingestion_creates_note_and_calls_finalize(bootstrapped_vault: Path):
    """KB agent writes a note file and calls finalize."""
    model = FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[
            ToolCall(name="write_page", args={
                "rel_path": "notes/2026-05-04-coffee.md",
                "content": "# Coffee with Mateo",
                "frontmatter_data": {"type": "note", "kb": "personal-diary", "date": "2026-05-04"},
            }, id="tc1", type="tool_call"),
        ]),
        AIMessage(content="", tool_calls=[
            ToolCall(name="finalize", args={"summary_for_user": "Ingested coffee note."},
                     id="tc2", type="tool_call"),
        ]),
        AIMessage(content="Done."),
    ])

    result = await kb_ingestion.ingest(
        [_routed()], bootstrapped_vault, "contract-kb1", model=model
    )

    assert result["summary"] == "Ingested coffee note."
    assert (bootstrapped_vault / "personal-diary" / "notes" / "2026-05-04-coffee.md").exists()


@pytest.mark.contract
@pytest.mark.asyncio
async def test_kb_agent_cannot_write_outside_kb(bootstrapped_vault: Path):
    """KB agent tool raises PathEscapeError for paths outside the KB folder."""
    from atlasmind.agents.tools.kb_pages import make_kb_page_tools
    from atlasmind.vault.fs import PathEscapeError

    tools = make_kb_page_tools(bootstrapped_vault, "personal-diary")
    write_page = next(t for t in tools if t.name == "write_page")
    with pytest.raises(PathEscapeError):
        write_page.invoke({"rel_path": "../../reflections/notes/bad.md", "content": "bad"})


@pytest.mark.contract
@pytest.mark.asyncio
async def test_breathing_skipped_when_false(bootstrapped_vault: Path):
    """When breathing=false (default), system prompt has no breathing instructions."""
    prompt = kb_ingestion._build_system_prompt(bootstrapped_vault, "personal-diary")
    assert "Breathing step" not in prompt


@pytest.mark.contract
@pytest.mark.asyncio
async def test_kb_ingestion_interrupt_flow(bootstrapped_vault: Path):
    """KB agent HITL: interrupt → resume → finalize."""
    thread_id = "contract-kb-hitl"
    model = FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[
            ToolCall(name="ask_user", args={"question": "Is this Sofía P. or R.?"},
                     id="tc1", type="tool_call"),
        ]),
        AIMessage(content="", tool_calls=[
            ToolCall(name="finalize", args={"summary_for_user": "Filed after clarification."},
                     id="tc2", type="tool_call"),
        ]),
        AIMessage(content="Done."),
    ])

    r1 = await kb_ingestion.ingest(
        [_routed()], bootstrapped_vault, thread_id, model=model
    )
    assert "interrupt_question" in r1

    r2 = await kb_ingestion.resume_ingest(
        "Sofía P.", bootstrapped_vault, "personal-diary", thread_id, model=model
    )
    assert r2["summary"] == "Filed after clarification."
