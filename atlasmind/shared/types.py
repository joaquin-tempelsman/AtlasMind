from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class RawMessage:
    """L0 → L1: raw Telegram message before any normalization."""
    telegram_user_id: int
    chat_id: int
    received_at: datetime
    kind: Literal["text", "voice", "link"]
    text: str | None = None
    voice_file_id: str | None = None
    url: str | None = None
    raw_payload: dict = field(default_factory=dict)


@dataclass
class NormalizedItem:
    """L1 → L2: normalized representation of any input kind."""
    received_at: datetime
    text: str
    source_kind: Literal["voice", "text", "link"]
    source_meta: dict
    telegram_user_id: int


@dataclass
class RoutedItem:
    """L2 → L3: normalized item with a routing decision attached."""
    normalized: NormalizedItem
    kb_slug: str
    routing_rationale: str
    confidence: Literal["high", "medium", "low"]


@dataclass
class IngestionResult:
    """L3 → L4: result of a KB ingestion agent run."""
    kb_slug: str
    note_path: str
    pages_touched: list[str]
    commit_message: str
    summary_for_user: str
