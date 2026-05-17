"""Contract tests: KB ingestion tools (kb_pages + kb_log + url_metadata).

Spec: dev_specs/05_agent_layer.md §3 — KB ingestion agent tools
Spec: dev_specs/06_kb_contract.md §2 — url_metadata_fields
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from atlasmind.agents.tools.kb_log import make_kb_log_tools
from atlasmind.agents.tools.kb_pages import make_kb_page_tools
from atlasmind.agents.tools.url_metadata import make_extract_url_metadata_tool
from atlasmind.vault.fs import PathEscapeError


def _get_tool(tools: list, name: str):
    return next(t for t in tools if t.name == name)


# ── read_page path escape ─────────────────────────────────────────────────────

@pytest.mark.contract
def test_read_page_escape_raises(bootstrapped_vault: Path):
    """read_page with a path escaping the KB root must raise PathEscapeError."""
    tools = make_kb_page_tools(bootstrapped_vault, "personal-diary")
    read_page = _get_tool(tools, "read_page")
    with pytest.raises(PathEscapeError):
        read_page.invoke({"rel_path": "../../_meta/kb_registry.md"})


@pytest.mark.contract
def test_write_page_escape_raises(bootstrapped_vault: Path):
    """write_page with an escaping path must raise PathEscapeError."""
    tools = make_kb_page_tools(bootstrapped_vault, "personal-diary")
    write_page = _get_tool(tools, "write_page")
    with pytest.raises(PathEscapeError):
        write_page.invoke({"rel_path": "../../secret.md", "content": "bad"})


# ── list_pages ────────────────────────────────────────────────────────────────

@pytest.mark.contract
def test_list_pages_returns_md_files(bootstrapped_vault: Path):
    tools = make_kb_page_tools(bootstrapped_vault, "personal-diary")
    result = _get_tool(tools, "list_pages").invoke({})
    assert isinstance(result, list)
    # agent.md, index.md, log.md should be present
    assert any("agent.md" in p for p in result)
    assert any("index.md" in p for p in result)


@pytest.mark.contract
def test_list_pages_subfolder_filter(bootstrapped_vault: Path):
    tools = make_kb_page_tools(bootstrapped_vault, "personal-diary")
    result = _get_tool(tools, "list_pages").invoke({"folder": "notes"})
    # Only files inside notes/ should be returned
    for p in result:
        assert p.startswith("notes/")


# ── write_page + read_page roundtrip ─────────────────────────────────────────

@pytest.mark.contract
def test_write_read_page_roundtrip(bootstrapped_vault: Path):
    tools = make_kb_page_tools(bootstrapped_vault, "personal-diary")
    write_page = _get_tool(tools, "write_page")
    read_page = _get_tool(tools, "read_page")

    content = "# Test Note\n\nHello world."
    write_page.invoke({"rel_path": "notes/test-note.md", "content": content})
    result = read_page.invoke({"rel_path": "notes/test-note.md"})
    assert "Hello world." in result


@pytest.mark.contract
def test_write_page_with_frontmatter(bootstrapped_vault: Path):
    tools = make_kb_page_tools(bootstrapped_vault, "personal-diary")
    write_page = _get_tool(tools, "write_page")
    read_page = _get_tool(tools, "read_page")

    write_page.invoke({
        "rel_path": "notes/fm-note.md",
        "content": "Note body.",
        "frontmatter_data": {"type": "note", "kb": "personal-diary", "date": "2026-05-04"},
    })
    result = read_page.invoke({"rel_path": "notes/fm-note.md"})
    assert "type: note" in result
    assert "Note body." in result


# ── append_to_page ────────────────────────────────────────────────────────────

@pytest.mark.contract
def test_append_to_page(bootstrapped_vault: Path):
    tools = make_kb_page_tools(bootstrapped_vault, "personal-diary")
    write_page = _get_tool(tools, "write_page")
    append_to_page = _get_tool(tools, "append_to_page")
    read_page = _get_tool(tools, "read_page")

    write_page.invoke({"rel_path": "notes/append-test.md", "content": "Line 1."})
    append_to_page.invoke({"rel_path": "notes/append-test.md", "content": "Line 2."})
    result = read_page.invoke({"rel_path": "notes/append-test.md"})
    assert "Line 1." in result
    assert "Line 2." in result


# ── search_pages ──────────────────────────────────────────────────────────────

@pytest.mark.contract
def test_search_pages_finds_content(bootstrapped_vault: Path):
    tools = make_kb_page_tools(bootstrapped_vault, "personal-diary")
    write_page = _get_tool(tools, "write_page")
    search_pages = _get_tool(tools, "search_pages")

    write_page.invoke({"rel_path": "notes/search-test.md", "content": "Unique phrase xq9z."})
    results = search_pages.invoke({"query": "xq9z"})
    assert len(results) == 1
    assert "notes/search-test.md" in results[0]["path"]


@pytest.mark.contract
def test_search_pages_case_insensitive(bootstrapped_vault: Path):
    tools = make_kb_page_tools(bootstrapped_vault, "personal-diary")
    write_page = _get_tool(tools, "write_page")
    search_pages = _get_tool(tools, "search_pages")

    write_page.invoke({"rel_path": "notes/case-test.md", "content": "Hello World."})
    results = search_pages.invoke({"query": "hello world"})
    assert any("case-test.md" in r["path"] for r in results)


# ── read_index + update_index ─────────────────────────────────────────────────

@pytest.mark.contract
def test_read_index_returns_index_contents(bootstrapped_vault: Path):
    tools = make_kb_page_tools(bootstrapped_vault, "personal-diary")
    result = _get_tool(tools, "read_index").invoke({})
    assert "kb_index" in result or "Index" in result


@pytest.mark.contract
def test_update_index_appends_to_existing_section(bootstrapped_vault: Path):
    tools = make_kb_page_tools(bootstrapped_vault, "personal-diary")
    update_index = _get_tool(tools, "update_index")
    read_index = _get_tool(tools, "read_index")

    update_index.invoke({"category": "Notes", "line": "- 2026-05-04 — test entry"})
    result = read_index.invoke({})
    assert "test entry" in result


@pytest.mark.contract
def test_update_index_creates_new_section(bootstrapped_vault: Path):
    tools = make_kb_page_tools(bootstrapped_vault, "personal-diary")
    update_index = _get_tool(tools, "update_index")
    read_index = _get_tool(tools, "read_index")

    update_index.invoke({"category": "Projects", "line": "- My project"})
    result = read_index.invoke({})
    assert "## Projects" in result
    assert "My project" in result


# ── append_kb_log + finalize ──────────────────────────────────────────────────

@pytest.mark.contract
def test_append_kb_log_writes_to_log(bootstrapped_vault: Path):
    tools = make_kb_log_tools(bootstrapped_vault, "personal-diary")
    append_kb_log = _get_tool(tools, "append_kb_log")

    entry = "## [2026-05-04T12:00:00Z] ingest | test-note\n**Note:** test\n"
    append_kb_log.invoke({"entry": entry})

    log_text = (bootstrapped_vault / "personal-diary" / "log.md").read_text()
    assert "test-note" in log_text


@pytest.mark.contract
def test_finalize_returns_done_and_summary(bootstrapped_vault: Path):
    tools = make_kb_log_tools(bootstrapped_vault, "personal-diary")
    finalize = _get_tool(tools, "finalize")

    result = finalize.invoke({"summary_for_user": "Ingested 2 notes."})
    assert result["done"] is True
    assert result["summary"] == "Ingested 2 notes."


# ── extract_url_metadata ──────────────────────────────────────────────────────

@pytest.mark.contract
@pytest.mark.asyncio
async def test_extract_url_metadata_returns_requested_fields():
    """extract_url_metadata must return a dict with exactly the requested fields.

    Spec: dev_specs/06_kb_contract.md §2 — url_metadata_fields
    """
    fake_article_text = "CNN article by John Smith about economics."
    fake_meta = {"url": "https://cnn.com/article", "title": "Economics Today", "fetched_at": "2026-01-01T00:00:00Z"}
    expected = {"media_source": "CNN", "article_writer": "John Smith"}

    mock_link_fetcher = AsyncMock()
    mock_link_fetcher.fetch.return_value = (fake_article_text, fake_meta)

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(expected))]
    mock_anthropic_response = mock_message

    tool = make_extract_url_metadata_tool(mock_link_fetcher)

    with patch("atlasmind.agents.tools.url_metadata.anthropic.AsyncAnthropic") as MockClient:
        mock_client_instance = AsyncMock()
        MockClient.return_value = mock_client_instance
        mock_client_instance.messages.create = AsyncMock(return_value=mock_anthropic_response)

        result = await tool.ainvoke({"url": "https://cnn.com/article", "fields": ["media_source", "article_writer"]})

    assert isinstance(result, dict)
    assert "media_source" in result
    assert "article_writer" in result
    mock_link_fetcher.fetch.assert_called_once_with("https://cnn.com/article")


@pytest.mark.contract
@pytest.mark.asyncio
async def test_extract_url_metadata_calls_haiku_model():
    """extract_url_metadata must use claude-haiku-4-5 for cost efficiency."""
    fake_article_text = "Some article text."
    fake_meta = {"url": "https://example.com", "title": "Example", "fetched_at": "2026-01-01T00:00:00Z"}

    mock_link_fetcher = AsyncMock()
    mock_link_fetcher.fetch.return_value = (fake_article_text, fake_meta)

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='{"media_source": "Example"}')]

    tool = make_extract_url_metadata_tool(mock_link_fetcher)

    with patch("atlasmind.agents.tools.url_metadata.anthropic.AsyncAnthropic") as MockClient:
        mock_client_instance = AsyncMock()
        MockClient.return_value = mock_client_instance
        mock_client_instance.messages.create = AsyncMock(return_value=mock_message)

        await tool.ainvoke({"url": "https://example.com", "fields": ["media_source"]})

    call_kwargs = mock_client_instance.messages.create.call_args
    assert call_kwargs.kwargs["model"] == "claude-haiku-4-5-20251001"


# ── register_entity (kb_entities) ────────────────────────────────────────────

@pytest.mark.contract
def test_register_entity_appends_new_entry(bootstrapped_vault: Path):
    """register_entity writes a new pipe-separated line to entities.md."""
    from atlasmind.agents.tools.kb_entities import make_kb_entity_tools

    tools = make_kb_entity_tools(bootstrapped_vault, "personal-diary")
    register = next(t for t in tools if t.name == "register_entity")

    result = register.invoke({"canonical_name": "Thomas Piketty", "aliases": ["Piketty"]})

    assert result == "Registered: Thomas Piketty"
    content = (bootstrapped_vault / "personal-diary" / "entities.md").read_text()
    assert "Thomas Piketty | Piketty" in content


@pytest.mark.contract
def test_register_entity_merges_aliases(bootstrapped_vault: Path):
    """Calling register_entity twice for the same canonical merges aliases, no duplicate line."""
    from atlasmind.agents.tools.kb_entities import make_kb_entity_tools

    tools = make_kb_entity_tools(bootstrapped_vault, "personal-diary")
    register = next(t for t in tools if t.name == "register_entity")

    register.invoke({"canonical_name": "Thomas Piketty", "aliases": ["Piketty"]})
    register.invoke({"canonical_name": "Thomas Piketty", "aliases": ["T. Piketty"]})

    content = (bootstrapped_vault / "personal-diary" / "entities.md").read_text()
    # Exactly one line for the entity
    entity_lines = [ln for ln in content.splitlines() if "Thomas Piketty" in ln]
    assert len(entity_lines) == 1
    assert "Piketty" in entity_lines[0]
    assert "T. Piketty" in entity_lines[0]


@pytest.mark.contract
def test_entities_md_scaffolded_per_kb(bootstrapped_vault: Path):
    """Bootstrap scaffolds entities.md in every KB folder."""
    entities = bootstrapped_vault / "personal-diary" / "entities.md"
    assert entities.exists()
    content = entities.read_text()
    assert "type: kb_entity_registry" in content
