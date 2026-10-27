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


@pytest.mark.contract
@pytest.mark.asyncio
async def test_kb_agent_recovers_from_rejected_tool_call(bootstrapped_vault: Path):
    """A raising tool becomes an error ToolMessage; the agent retries and the batch completes."""
    from langchain_core.messages import ToolMessage

    good_path = "notes/2026-05-04-walk.md"
    model = FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[
            ToolCall(name="write_page", args={"rel_path": "../_meta/kb_registry.md",
                                              "content": "pwned"}, id="tc1", type="tool_call"),
        ]),
        AIMessage(content="", tool_calls=[
            ToolCall(name="write_page", args={"rel_path": good_path, "content": "# Walk"},
                     id="tc2", type="tool_call"),
        ]),
        AIMessage(content="", tool_calls=[
            ToolCall(name="finalize", args={"summary_for_user": "Filed walk."},
                     id="tc3", type="tool_call"),
        ]),
        AIMessage(content="Done."),
    ])

    result = await kb_ingestion.ingest([_routed()], bootstrapped_vault, "t-err", model=model)

    assert result["summary"] == "Filed walk."
    assert "pwned" not in (bootstrapped_vault / "_meta" / "kb_registry.md").read_text()
    assert (bootstrapped_vault / "personal-diary" / good_path).exists()

    agent = kb_ingestion.get_agent(bootstrapped_vault, "personal-diary")
    state = await agent.aget_state({"configurable": {"thread_id": "t-err"}})
    errors = [m for m in state.values["messages"]
              if isinstance(m, ToolMessage) and m.status == "error"]
    assert len(errors) == 1
    assert "escapes KB root" in errors[0].content


@pytest.mark.contract
@pytest.mark.asyncio
async def test_lint_agent_recovers_from_rejected_tool_call(bootstrapped_vault: Path):
    """The lint agent shares the tool-error contract with the ingestion agent."""
    from atlasmind.agents import lint

    lint.reset_cache()
    model = FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[
            ToolCall(name="read_page", args={"rel_path": "../../etc/passwd"},
                     id="tc1", type="tool_call"),
        ]),
        AIMessage(content="", tool_calls=[
            ToolCall(name="finalize_lint", args={"summary_for_user": "Lint clean."},
                     id="tc2", type="tool_call"),
        ]),
        AIMessage(content="Done."),
    ])
    result = await lint.run(
        vault_root=bootstrapped_vault, kb_slug="personal-diary", thread_id="t-lint-err",
        model=model,
    )
    lint.reset_cache()

    assert result["summary"] == "Lint clean."


def _commit(kb_slug: str, rationale: str, confidence: str, tc_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[
        ToolCall(name="commit_route", args={
            "kb_slug": kb_slug, "rationale": rationale, "confidence": confidence,
        }, id=tc_id, type="tool_call"),
    ])


@pytest.mark.contract
@pytest.mark.asyncio
async def test_router_without_commit_raises_instead_of_reusing_stale_log(
    bootstrapped_vault: Path,
):
    """A router run that never commits must not inherit the previous message's route."""
    model = FakeToolCallingModel(responses=[
        _commit("econ-politics", "Article.", "high", "tc1"),
        AIMessage(content="Routed."),
        # Second message: the model answers in prose and never calls commit_route.
        AIMessage(content="I think this is diary."),
    ])
    first = await router.route(_item("FT on rates"), bootstrapped_vault, "r-a", model=model)
    assert first["kb_slug"] == "econ-politics"

    with pytest.raises(router.RouterNoDecisionError):
        await router.route(_item("Went to the dentist"), bootstrapped_vault, "r-b", model=model)


@pytest.mark.contract
@pytest.mark.asyncio
async def test_router_decision_comes_from_this_runs_commit(bootstrapped_vault: Path):
    """The returned route mirrors this run's commit_route args (slug, rationale, confidence)."""
    model = FakeToolCallingModel(responses=[
        _commit("personal-diary", "Dinner with friends.", "medium", "tc1"),
        AIMessage(content="Routed."),
    ])
    result = await router.route(_item(), bootstrapped_vault, "r-c", model=model)

    assert result == {
        "kb_slug": "personal-diary", "rationale": "Dinner with friends.", "confidence": "medium",
    }


@pytest.mark.contract
@pytest.mark.asyncio
async def test_router_rejected_commit_then_valid_commit_uses_valid_one(bootstrapped_vault: Path):
    """A failed commit_route (unknown KB) is not a decision; the later valid one is."""
    model = FakeToolCallingModel(responses=[
        _commit("not-a-kb", "Idea.", "high", "tc1"),
        _commit("personal-diary", "Actually an event.", "high", "tc2"),
        AIMessage(content="Routed."),
    ])
    result = await router.route(_item(), bootstrapped_vault, "r-d", model=model)

    assert result["kb_slug"] == "personal-diary"
