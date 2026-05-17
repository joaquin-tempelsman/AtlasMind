"""Unit tests for edge/url_registry.py."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from atlasmind.edge import url_registry


@pytest.fixture(autouse=True)
def _clear():
    yield
    url_registry.clear_all()


@pytest.mark.unit
def test_register_and_lookup():
    url_registry.register(user_id=1, message_id=100, url="https://example.com")
    assert url_registry.lookup(1, 100) == "https://example.com"


@pytest.mark.unit
def test_lookup_unknown_returns_none():
    assert url_registry.lookup(1, 999) is None


@pytest.mark.unit
def test_lookup_different_user_returns_none():
    url_registry.register(user_id=1, message_id=100, url="https://example.com")
    assert url_registry.lookup(2, 100) is None


@pytest.mark.unit
def test_multiple_message_ids_same_user():
    url_registry.register(1, 100, "https://a.com")
    url_registry.register(1, 101, "https://a.com")  # bot reply id for same url
    url_registry.register(1, 200, "https://b.com")
    assert url_registry.lookup(1, 100) == "https://a.com"
    assert url_registry.lookup(1, 101) == "https://a.com"
    assert url_registry.lookup(1, 200) == "https://b.com"


@pytest.mark.unit
def test_expired_entry_returns_none():
    url_registry.register(1, 100, "https://example.com")
    future = datetime.now(timezone.utc) + timedelta(hours=25)
    with patch("atlasmind.edge.url_registry.datetime") as mock_dt:
        mock_dt.now.return_value = future
        result = url_registry.lookup(1, 100)
    assert result is None


@pytest.mark.unit
def test_clear_user():
    url_registry.register(1, 100, "https://a.com")
    url_registry.register(2, 200, "https://b.com")
    url_registry.clear_user(1)
    assert url_registry.lookup(1, 100) is None
    assert url_registry.lookup(2, 200) == "https://b.com"


@pytest.mark.unit
def test_clear_all():
    url_registry.register(1, 100, "https://a.com")
    url_registry.register(2, 200, "https://b.com")
    url_registry.clear_all()
    assert url_registry.lookup(1, 100) is None
    assert url_registry.lookup(2, 200) is None
