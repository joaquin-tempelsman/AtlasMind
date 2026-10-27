"""Unit tests for agents/middleware.py."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphInterrupt

from atlasmind.agents.middleware import ToolErrorsAsMessages


def _request(name: str = "write_page") -> SimpleNamespace:
    return SimpleNamespace(tool_call={"name": name, "args": {}, "id": "tc1"})


def _raises(exc: Exception):
    def handler(request):
        raise exc
    return handler


def _araises(exc: Exception):
    async def handler(request):
        raise exc
    return handler


@pytest.mark.unit
def test_sync_tool_error_becomes_error_tool_message():
    msg = ToolErrorsAsMessages().wrap_tool_call(_request(), _raises(ValueError("bad path")))

    assert isinstance(msg, ToolMessage)
    assert msg.status == "error"
    assert msg.tool_call_id == "tc1"
    assert msg.name == "write_page"
    assert "ValueError: bad path" in msg.content


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_tool_error_becomes_error_tool_message():
    msg = await ToolErrorsAsMessages().awrap_tool_call(_request(), _araises(OSError("disk")))

    assert msg.status == "error"
    assert "OSError: disk" in msg.content


@pytest.mark.unit
def test_successful_tool_result_passes_through_unchanged():
    ok = ToolMessage(content="written", tool_call_id="tc1")

    assert ToolErrorsAsMessages().wrap_tool_call(_request(), lambda r: ok) is ok


@pytest.mark.unit
def test_interrupt_is_reraised_not_swallowed():
    with pytest.raises(GraphInterrupt):
        ToolErrorsAsMessages().wrap_tool_call(_request("ask_user"), _raises(GraphInterrupt()))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_interrupt_is_reraised_not_swallowed():
    with pytest.raises(GraphInterrupt):
        await ToolErrorsAsMessages().awrap_tool_call(
            _request("ask_user"), _araises(GraphInterrupt())
        )
