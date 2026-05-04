from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Required env var {name!r} is not set. Copy .env.example to .env and fill it in.")
    return val


def _optional(name: str, default: str = "") -> str:
    return os.getenv(name, default)


TELEGRAM_BOT_TOKEN: str = _optional("TELEGRAM_BOT_TOKEN")
TELEGRAM_ALLOWED_USER_IDS: list[int] = [
    int(uid.strip())
    for uid in _optional("TELEGRAM_ALLOWED_USER_IDS").split(",")
    if uid.strip()
]
OPENAI_API_KEY: str = _optional("OPENAI_API_KEY")
VAULT_REPO_PATH: Path = Path(_optional("VAULT_REPO_PATH", "")) if _optional("VAULT_REPO_PATH") else Path.cwd() / "vault"

KB_DEFINITIONS_PATH: Path = Path(__file__).parent.parent / "kb_definitions" / "kb_definitions.md"
KB_DEFINITIONS_EXAMPLE_PATH: Path = Path(__file__).parent.parent / "kb_definitions" / "kb_definitions.example.md"

ROUTER_MODEL: str = _optional("ROUTER_MODEL", "gpt-4o")
KB_INGESTION_MODEL: str = _optional("KB_INGESTION_MODEL", "gpt-4o")
SUMMARIZATION_MODEL: str = _optional("SUMMARIZATION_MODEL", "gpt-4o-mini")

SESSION_TIMEOUT_SECONDS: int = int(_optional("SESSION_TIMEOUT_SECONDS", "600"))
