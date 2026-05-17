#!/usr/bin/env python
"""Local end-to-end test runner — full pipeline without Telegram.

Creates a disposable vault at dev/.local_vault/, sends messages through the
pipeline, and prints every reply to stdout. No bot token required.

Usage:
    # Single message:
    .venv/bin/python dev/local_run.py "Met Sofia at the café today."

    # Interactive REPL (handles HITL questions in the terminal):
    .venv/bin/python dev/local_run.py

    # Reset the vault before running (wipes dev/.local_vault/):
    .venv/bin/python dev/local_run.py --clean "Your message"
    .venv/bin/python dev/local_run.py --clean

Requirements:
    OPENAI_API_KEY must be set in .env or the environment.
    kb_definitions/kb_definitions.md must exist (run ./setup.sh first if not).
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make sure project root is importable when run directly
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Load .env before importing anything that reads config
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import logging
logging.basicConfig(
    level=logging.DEBUG,
    format="[%(levelname)s %(name)s] %(message)s",
    stream=sys.stdout,
)
# Quiet noisy library loggers
for _noisy in ("httpcore", "httpx", "openai", "urllib3", "telegram"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

from atlasmind.bootstrap import run as bootstrap_run
from atlasmind.pipeline import Pipeline
from atlasmind.shared.types import RawMessage

VAULT_DIR = ROOT / "dev" / ".local_vault"
FAKE_USER_ID = 1
INGEST_DELAY = 5  # seconds — short for local testing (real default is 300)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _ensure_vault() -> Path:
    """Create and bootstrap the local vault if it doesn't exist."""
    VAULT_DIR.mkdir(parents=True, exist_ok=True)

    # Init as a git repo so git_sync doesn't blow up (no remote = no push)
    if not (VAULT_DIR / ".git").exists():
        subprocess.run(["git", "init"], cwd=str(VAULT_DIR), check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "atlasmind@local"],
            cwd=str(VAULT_DIR), check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "AtlasMind"],
            cwd=str(VAULT_DIR), check=True, capture_output=True,
        )
        # Initial commit so HEAD exists
        (VAULT_DIR / ".gitkeep").touch()
        subprocess.run(["git", "add", ".gitkeep"], cwd=str(VAULT_DIR), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "chore: init local test vault"],
            cwd=str(VAULT_DIR), check=True, capture_output=True,
        )
        print(f"[vault] Initialised git repo at {VAULT_DIR}")

    bootstrap_run(vault_path=VAULT_DIR)
    print(f"[vault] Bootstrapped at {VAULT_DIR}")
    return VAULT_DIR


def _make_raw(text: str) -> RawMessage:
    return RawMessage(
        telegram_user_id=FAKE_USER_ID,
        chat_id=FAKE_USER_ID,
        received_at=datetime.now(tz=timezone.utc),
        kind="text",
        text=text,
    )


# ── Main ─────────────────────────────────────────────────────────────────────

async def run(initial_message: str | None) -> None:
    # Pending HITL state: track whether the next stdin line is an answer
    state: dict = {"expecting_answer": False, "thread_id": str(FAKE_USER_ID)}

    # Set when reply_fn is called — single-message mode waits on this
    ingest_done = asyncio.Event()

    async def reply_fn(user_id: int, text: str) -> None:
        print(f"\n[bot → you] {text}\n", flush=True)
        ingest_done.set()

    vault_root = _ensure_vault()
    pipeline = Pipeline(
        vault_root=vault_root,
        ingest_delay_seconds=INGEST_DELAY,
        reply_fn=reply_fn,
    )

    print(f"\nAtlasMind local runner ready.")
    print(f"Vault:        {vault_root}")
    print(f"Ingest delay: {INGEST_DELAY}s")
    print(f"Type a message and press Enter. Ctrl-C to quit.\n")

    async def send(text: str) -> None:
        thread_id = state["thread_id"]
        if state["expecting_answer"]:
            print(f"[you → bot] (answering) {text}")
            state["expecting_answer"] = False
            result = await pipeline.resume(thread_id=thread_id, answer=text, user_id=FAKE_USER_ID)
        else:
            print(f"[you → bot] {text}")
            result = await pipeline.process(_make_raw(text), thread_id=thread_id)

        if "reply" in result:
            print(f"[bot → you] {result['reply']}")
            print(f"            (ingest will fire in ~{INGEST_DELAY}s)\n")
        elif "interrupt_question" in result:
            print(f"[bot → you] {result['interrupt_question']}")
            state["expecting_answer"] = True
        elif "error" in result:
            print(f"[error]     {result['error']}\n")

    if initial_message:
        await send(initial_message)
        print(f"Waiting for ingest to complete (timer: {INGEST_DELAY}s + LLM time)…")
        try:
            await asyncio.wait_for(ingest_done.wait(), timeout=INGEST_DELAY + 60)
        except asyncio.TimeoutError:
            print("[error] Timed out waiting for ingest reply. Check logs above for errors.")
        return

    # Interactive REPL
    loop = asyncio.get_running_loop()
    while True:
        try:
            prompt = "answer> " if state["expecting_answer"] else "you> "
            text = await loop.run_in_executor(None, lambda: input(prompt))
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break
        if not text.strip():
            continue
        await send(text.strip())


def main() -> None:
    args = sys.argv[1:]

    if "--clean" in args:
        args.remove("--clean")
        if VAULT_DIR.exists():
            shutil.rmtree(VAULT_DIR)
            print(f"[vault] Removed {VAULT_DIR}")

    message = " ".join(args) if args else None
    asyncio.run(run(message))


if __name__ == "__main__":
    main()
