"""Contract tests for the amendment classifier (atlasmind/agents/amendment.py).

These assert the documented output shapes of classify_amendment (see
dev_specs/05_agent_layer.md §3.5), independent of the underlying LLM.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from atlasmind.agents.amendment import classify_amendment


def _mock_anthropic(text: str) -> MagicMock:
    """Build a patch target that yields a fake AsyncAnthropic returning `text`."""
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    return MagicMock(return_value=client)


@pytest.mark.contract
@pytest.mark.asyncio
async def test_empty_pending_is_new_without_llm_call():
    """No pending items → always {"kind": "new"}, and the LLM is not called."""
    factory = _mock_anthropic('{"kind": "new"}')
    with patch("atlasmind.agents.amendment.anthropic.AsyncAnthropic", factory):
        result = await classify_amendment(pending=[], new_text="Anything.")
    assert result == {"kind": "new"}
    factory.assert_not_called()


@pytest.mark.contract
@pytest.mark.asyncio
async def test_new_message_shape():
    """A genuinely new message returns exactly {"kind": "new"}."""
    factory = _mock_anthropic('{"kind": "new"}')
    with patch("atlasmind.agents.amendment.anthropic.AsyncAnthropic", factory):
        result = await classify_amendment(
            pending=["Met Pablo at the cafe."], new_text="Bought milk today."
        )
    assert result == {"kind": "new"}


@pytest.mark.contract
@pytest.mark.asyncio
async def test_modification_shape():
    """A correction returns the documented modification shape."""
    payload = (
        '{"kind": "modification", "target_index": 0, '
        '"new_text": "Met Pablo at the cafe.", "rationale": "fix typo Pablou->Pablo"}'
    )
    factory = _mock_anthropic(payload)
    with patch("atlasmind.agents.amendment.anthropic.AsyncAnthropic", factory):
        result = await classify_amendment(
            pending=["Met Pablou at the cafe."],
            new_text="I meant Pablo, not Pablou.",
        )
    assert result["kind"] == "modification"
    assert result["target_index"] == 0
    assert isinstance(result["target_index"], int)
    assert isinstance(result["new_text"], str) and result["new_text"]
    assert isinstance(result["rationale"], str)


@pytest.mark.contract
@pytest.mark.asyncio
async def test_modification_strips_markdown_fence():
    """A fenced JSON response is parsed, not rejected."""
    payload = (
        '```json\n{"kind": "modification", "target_index": 1, '
        '"new_text": "corrected", "rationale": "r"}\n```'
    )
    factory = _mock_anthropic(payload)
    with patch("atlasmind.agents.amendment.anthropic.AsyncAnthropic", factory):
        result = await classify_amendment(
            pending=["a", "b"], new_text="fix the second one"
        )
    assert result["kind"] == "modification"
    assert result["target_index"] == 1


@pytest.mark.contract
@pytest.mark.asyncio
async def test_bad_json_fails_safe_to_new():
    """Unparseable LLM output never rewrites — falls back to {"kind": "new"}."""
    factory = _mock_anthropic("not json at all")
    with patch("atlasmind.agents.amendment.anthropic.AsyncAnthropic", factory):
        result = await classify_amendment(pending=["a"], new_text="b")
    assert result == {"kind": "new"}


@pytest.mark.contract
@pytest.mark.asyncio
async def test_out_of_range_index_fails_safe_to_new():
    """A target_index outside the pending range is rejected, not applied blindly."""
    payload = '{"kind": "modification", "target_index": 9, "new_text": "x", "rationale": "r"}'
    factory = _mock_anthropic(payload)
    with patch("atlasmind.agents.amendment.anthropic.AsyncAnthropic", factory):
        result = await classify_amendment(pending=["only one"], new_text="fix it")
    assert result == {"kind": "new"}
