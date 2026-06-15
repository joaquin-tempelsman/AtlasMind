"""Unit tests for agents/kb_ingestion.py."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.messages.tool import ToolCall

from atlasmind.agents import kb_ingestion
from atlasmind.agents.kb_ingestion import _build_batch_message
from atlasmind.bootstrap import run as bootstrap_run
from atlasmind.shared.types import NormalizedItem, RoutedItem


class FakeToolCallingModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def _routed(
    text: str = "Met Mateo at Tortoni today.",
    kb_slug: str = "personal-diary",
    source_kind: str = "voice",
) -> RoutedItem:
    normalized = NormalizedItem(
        received_at=datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc),
        text=text,
        source_kind=source_kind,
        source_meta={},
        telegram_user_id=1,
    )
    return RoutedItem(
        normalized=normalized,
        kb_slug=kb_slug,
        routing_rationale="Real event.",
        confidence="high",
    )


@pytest.fixture(autouse=True)
def clear_cache():
    kb_ingestion.reset_cache()
    yield
    kb_ingestion.reset_cache()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_creates_note_file(tmp_path: Path):
    """Agent calls write_page → note file exists in vault."""
    bootstrap_run(vault_path=tmp_path)
    note_path = "notes/2026-05-04-test-note.md"

    model = FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[
            ToolCall(name="write_page", args={
                "rel_path": note_path,
                "content": "# Test Note\n\nMet Mateo today.",
                "frontmatter_data": {"type": "note", "kb": "personal-diary", "date": "2026-05-04"},
            }, id="tc1", type="tool_call"),
        ]),
        AIMessage(content="", tool_calls=[
            ToolCall(name="finalize", args={"summary_for_user": "Filed 1 note: test."}, id="tc2", type="tool_call"),
        ]),
        AIMessage(content="Done."),
    ])

    result = await kb_ingestion.ingest([_routed()], tmp_path, "t-1", model=model)

    assert result["summary"] == "Filed 1 note: test."
    assert (tmp_path / "personal-diary" / note_path).exists()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_calls_finalize(tmp_path: Path):
    """finalize() is called and its summary is returned."""
    bootstrap_run(vault_path=tmp_path)

    model = FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[
            ToolCall(name="finalize", args={"summary_for_user": "Ingested item."}, id="tc1", type="tool_call"),
        ]),
        AIMessage(content="Complete."),
    ])

    result = await kb_ingestion.ingest([_routed()], tmp_path, "t-2", model=model)
    assert result == {"summary": "Ingested item."}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_interrupt_returns_question(tmp_path: Path):
    """When agent calls ask_user, ingest() returns {interrupt_question: ...}."""
    bootstrap_run(vault_path=tmp_path)

    model = FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[
            ToolCall(name="ask_user", args={"question": "Is this Sofía P. or Sofía R.?"},
                     id="tc1", type="tool_call"),
        ]),
        AIMessage(content=""),
    ])

    result = await kb_ingestion.ingest([_routed()], tmp_path, "t-3", model=model)
    assert "interrupt_question" in result
    assert "Sofía" in result["interrupt_question"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_empty_list_returns_no_items():
    """Empty batch returns immediately with no-items message."""
    result = await kb_ingestion.ingest([], Path("/fake"), "t-4")
    assert result == {"summary": "No items to ingest."}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_breathing_disabled_by_default(tmp_path: Path):
    """System prompt does NOT include breathing instructions when breathing=false."""
    bootstrap_run(vault_path=tmp_path)
    prompt = kb_ingestion._build_system_prompt(tmp_path, "personal-diary")
    assert "Breathing step" not in prompt


@pytest.mark.unit
def test_breathing_enabled_when_flag_set(tmp_path: Path):
    """System prompt DOES include breathing instructions when breathing=true."""
    bootstrap_run(vault_path=tmp_path)

    # Manually patch the registry to set breathing=true for personal-diary
    registry_path = tmp_path / "_meta" / "kb_registry.md"
    text = registry_path.read_text()
    # Replace "- **Breathing:** false" only in the personal-diary section
    lines = text.splitlines()
    in_diary = False
    patched = []
    for line in lines:
        if line.strip() == "## personal-diary":
            in_diary = True
        elif line.startswith("## ") and in_diary:
            in_diary = False
        if in_diary and "**Breathing:** false" in line:
            line = line.replace("**Breathing:** false", "**Breathing:** true")
        patched.append(line)
    registry_path.write_text("\n".join(patched), encoding="utf-8")

    prompt = kb_ingestion._build_system_prompt(tmp_path, "personal-diary")
    assert "Breathing step" in prompt


@pytest.mark.unit
def test_language_addon_absent_when_unset(tmp_path: Path):
    """No output-language instruction when the KB has no language set."""
    bootstrap_run(vault_path=tmp_path)
    # personal-diary has no language in the CI fixture
    prompt = kb_ingestion._build_system_prompt(tmp_path, "personal-diary")
    assert "Output language" not in prompt


@pytest.mark.unit
def test_language_addon_present_when_set(tmp_path: Path):
    """Output-language instruction names the configured language when set."""
    bootstrap_run(vault_path=tmp_path)
    # econ-politics is configured with language: English in the CI fixture
    prompt = kb_ingestion._build_system_prompt(tmp_path, "econ-politics")
    assert "Output language" in prompt
    assert "English" in prompt
    # finalize summary carve-out is included
    assert "finalize() summary" in prompt


@pytest.mark.unit
@pytest.mark.asyncio
async def test_kb_agent_is_cached(tmp_path: Path):
    """Two calls to get_agent with same (vault_root, kb_slug) return same object."""
    bootstrap_run(vault_path=tmp_path)
    model = FakeToolCallingModel(responses=[AIMessage(content="done")])
    a1 = kb_ingestion.get_agent(tmp_path, "personal-diary", model)
    a2 = kb_ingestion.get_agent(tmp_path, "personal-diary", model)
    assert a1 is a2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_kb_agent_scoped_to_kb(tmp_path: Path):
    """Agents for different KBs are different cached objects."""
    bootstrap_run(vault_path=tmp_path)
    model = FakeToolCallingModel(responses=[AIMessage(content="done")])
    a_diary = kb_ingestion.get_agent(tmp_path, "personal-diary", model)
    a_refl = kb_ingestion.get_agent(tmp_path, "reflections", model)
    assert a_diary is not a_refl


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_multi_tool_calls(tmp_path: Path):
    """Agent can chain multiple tool calls before finalize."""
    bootstrap_run(vault_path=tmp_path)

    model = FakeToolCallingModel(responses=[
        # Search for existing pages
        AIMessage(content="", tool_calls=[
            ToolCall(name="search_pages", args={"query": "Mateo"}, id="tc1", type="tool_call"),
        ]),
        # Write note
        AIMessage(content="", tool_calls=[
            ToolCall(name="write_page", args={
                "rel_path": "notes/2026-05-04-coffee.md",
                "content": "# Coffee with Mateo",
            }, id="tc2", type="tool_call"),
        ]),
        # Finalize
        AIMessage(content="", tool_calls=[
            ToolCall(name="finalize", args={"summary_for_user": "Filed coffee note."}, id="tc3", type="tool_call"),
        ]),
        AIMessage(content="Done."),
    ])

    result = await kb_ingestion.ingest([_routed()], tmp_path, "t-5", model=model)
    assert result["summary"] == "Filed coffee note."
    assert (tmp_path / "personal-diary" / "notes" / "2026-05-04-coffee.md").exists()


@pytest.mark.unit
def test_batch_message_includes_entity_registry(tmp_path: Path):
    """_build_batch_message includes entity registry content when entities.md exists."""
    bootstrap_run(vault_path=tmp_path)
    # Add an entity to the registry
    entities_path = tmp_path / "personal-diary" / "entities.md"
    with entities_path.open("a", encoding="utf-8") as f:
        f.write("Thomas Piketty | Piketty\n")

    msg = _build_batch_message(tmp_path, "personal-diary", [_routed()])

    assert "Entity Registry" in msg
    assert "Thomas Piketty" in msg


@pytest.mark.unit
def test_batch_message_no_entity_registry_section_when_missing(tmp_path: Path):
    """_build_batch_message omits entity registry section when entities.md absent."""
    bootstrap_run(vault_path=tmp_path)
    (tmp_path / "personal-diary" / "entities.md").unlink()

    msg = _build_batch_message(tmp_path, "personal-diary", [_routed()])

    assert "Entity Registry" not in msg


@pytest.mark.unit
def test_batch_message_surfaces_raw_capture_path(tmp_path: Path):
    """_build_batch_message surfaces the raw_capture pointer so the agent can
    record it in note frontmatter."""
    bootstrap_run(vault_path=tmp_path)
    routed = _routed()
    routed.normalized.source_meta["raw_capture_path"] = "raw/captures/2026-05-04T12-00-00Z__abc123.md"

    msg = _build_batch_message(tmp_path, "personal-diary", [routed])

    assert "raw/captures/2026-05-04T12-00-00Z__abc123.md" in msg
    assert "raw_capture" in msg


@pytest.mark.unit
def test_batch_message_no_raw_capture_line_when_absent(tmp_path: Path):
    """No raw capture line when source_meta lacks raw_capture_path."""
    bootstrap_run(vault_path=tmp_path)
    msg = _build_batch_message(tmp_path, "personal-diary", [_routed()])
    assert "Raw capture" not in msg
