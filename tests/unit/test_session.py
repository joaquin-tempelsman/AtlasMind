"""Unit tests for edge/session.py."""
from __future__ import annotations

import time

import pytest

from atlasmind.edge import session


@pytest.fixture(autouse=True)
def clear():
    session.clear_all()
    yield
    session.clear_all()


@pytest.mark.unit
def test_get_absent_returns_none():
    assert session.get(42) is None


@pytest.mark.unit
def test_set_and_get_roundtrip():
    session.set_active(1, "t-1", expecting="answer", kb_slug="diary")
    entry = session.get(1)
    assert entry is not None
    assert entry["thread_id"] == "t-1"
    assert entry["expecting"] == "answer"
    assert entry["kb_slug"] == "diary"


@pytest.mark.unit
def test_drop_removes_entry():
    session.set_active(1, "t-1")
    session.drop(1)
    assert session.get(1) is None


@pytest.mark.unit
def test_expired_session_returns_none(monkeypatch):
    monkeypatch.setattr("atlasmind.edge.session.SESSION_TIMEOUT_SECONDS", 0)
    session.set_active(1, "t-1")
    time.sleep(0.01)
    assert session.get(1) is None


@pytest.mark.unit
def test_touch_refreshes_session():
    session.set_active(1, "t-1")
    original = session.get(1)["last_active"]
    time.sleep(0.01)
    session.touch(1)
    assert session.get(1)["last_active"] >= original


@pytest.mark.unit
def test_set_active_updates_expecting():
    session.set_active(1, "t-1", expecting="answer")
    session.set_active(1, "t-1", expecting=None)
    assert session.get(1)["expecting"] is None
