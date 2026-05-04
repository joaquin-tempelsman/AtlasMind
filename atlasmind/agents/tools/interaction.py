"""HITL tool: ask_user wraps LangGraph interrupt()."""
from __future__ import annotations

from langchain_core.tools import tool
from langgraph.types import interrupt


@tool
def ask_user(question: str) -> str:
    """Ask the user a clarifying question; returns their answer when the graph resumes."""
    return interrupt({"question": question})
