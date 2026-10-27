"""Agent middleware shared by the router, KB ingestion, and lint agents.

ToolErrorsAsMessages turns a raising tool into an error ToolMessage so the
agent can read the reason and retry, instead of the exception aborting the
whole run (dev_specs/05_agent_layer.md §6).
"""
from __future__ import annotations

import logging

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphBubbleUp

logger = logging.getLogger(__name__)


def _error_message(request, exc: Exception) -> ToolMessage:
    call = request.tool_call
    logger.warning("tool %s failed: %s", call.get("name"), exc)
    return ToolMessage(
        content=f"Error: {type(exc).__name__}: {exc}. Fix the arguments and try again.",
        tool_call_id=call["id"],
        name=call.get("name"),
        status="error",
    )


class ToolErrorsAsMessages(AgentMiddleware):
    """Return tool exceptions to the model as error ToolMessages.

    GraphBubbleUp (raised by interrupt() inside ask_user) is control flow, not
    an error, and is always re-raised.
    """

    def wrap_tool_call(self, request, handler):
        try:
            return handler(request)
        except GraphBubbleUp:
            raise
        except Exception as exc:
            return _error_message(request, exc)

    async def awrap_tool_call(self, request, handler):
        try:
            return await handler(request)
        except GraphBubbleUp:
            raise
        except Exception as exc:
            return _error_message(request, exc)
