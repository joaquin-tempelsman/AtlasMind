"""Telegram message handlers.

Thin adapters: download/transcribe, detect message kind, delegate to pipeline.
No business logic here — all routing/ingestion decisions live in pipeline.py.
"""
from __future__ import annotations

import io
import logging

from telegram import Update
from telegram.ext import ContextTypes

from atlasmind.agents import lint as lint_agent
from atlasmind.config import TELEGRAM_ALLOWED_USER_IDS, VAULT_REPO_PATH
from atlasmind.edge import url_registry
from atlasmind.ingestion.transcriber import WhisperTranscriber
from atlasmind.shared.types import RawMessage

logger = logging.getLogger(__name__)

_transcriber: WhisperTranscriber | None = None


def _get_transcriber() -> WhisperTranscriber:
    global _transcriber
    if _transcriber is None:
        _transcriber = WhisperTranscriber()
    return _transcriber

_URL_PREFIXES = ("http://", "https://")


def _is_url(text: str) -> bool:
    stripped = text.strip()
    return any(stripped.startswith(p) for p in _URL_PREFIXES) and " " not in stripped


def _get_pipeline(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["pipeline"]


async def _auth_guard(update: Update) -> bool:
    """Return True if the user is allowed; reply and return False otherwise."""
    user_id = update.effective_user.id
    if TELEGRAM_ALLOWED_USER_IDS and user_id not in TELEGRAM_ALLOWED_USER_IDS:
        logger.warning("Rejected message from unauthorized user_id=%s", user_id)
        await update.message.reply_text("Not authorized.")
        return False
    return True


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _auth_guard(update):
        return

    user_id = update.effective_user.id
    msg = update.message

    await msg.reply_text("Transcribing…")

    try:
        tg_file = await context.bot.get_file(msg.voice.file_id)
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        buf.seek(0)
        audio_bytes = buf.read()
        transcript = await _get_transcriber().transcribe(audio_bytes, hint_filename="voice.ogg")
    except Exception as exc:
        logger.exception("Transcription failed for user_id=%s: %s", user_id, exc)
        await msg.reply_text("Transcription failed. Please try again.")
        return

    await msg.reply_text(f"Transcript: {transcript}")

    linked_url: str | None = None
    if msg.reply_to_message is not None:
        linked_url = url_registry.lookup(user_id, msg.reply_to_message.message_id)

    raw = RawMessage(
        telegram_user_id=user_id,
        chat_id=msg.chat_id,
        received_at=msg.date,
        kind="voice",
        text=transcript,
        voice_file_id=msg.voice.file_id,
        linked_url=linked_url,
    )

    pipeline = _get_pipeline(context)
    thread_id = str(user_id)

    from atlasmind.edge import session
    session.set_active(user_id, thread_id)

    result = await pipeline.process(raw, thread_id=thread_id)
    await _dispatch_result(update, user_id, thread_id, result)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _auth_guard(update):
        return

    user_id = update.effective_user.id
    msg = update.message
    text = (msg.text or "").strip()

    from atlasmind.edge import session

    active = session.get(user_id)
    if active and active.get("expecting") == "answer":
        thread_id = active["thread_id"]
        session.set_active(user_id, thread_id, expecting=None)

        pipeline = _get_pipeline(context)
        result = await pipeline.resume(thread_id=thread_id, answer=text, user_id=user_id)
        await _dispatch_result(update, user_id, thread_id, result)
        return

    thread_id = str(user_id)
    session.set_active(user_id, thread_id)

    if _is_url(text):
        raw = RawMessage(
            telegram_user_id=user_id,
            chat_id=msg.chat_id,
            received_at=msg.date,
            kind="link",
            text=text,
            url=text,
        )
        pipeline = _get_pipeline(context)
        result = await pipeline.process(raw, thread_id=thread_id)
        # Register message_id → url so subsequent replies can be linked.
        # Store both the user's message id and the bot's reply id (if we get one).
        url_registry.register(user_id, msg.message_id, text)
        if "reply" in result and update.message:
            # The bot's reply message_id is not easily accessible here without
            # capturing the sent message; register will be called in _dispatch_result.
            pass
        await _dispatch_result(update, user_id, thread_id, result, link_url=text)
        return

    linked_url: str | None = None
    if msg.reply_to_message is not None:
        linked_url = url_registry.lookup(user_id, msg.reply_to_message.message_id)

    raw = RawMessage(
        telegram_user_id=user_id,
        chat_id=msg.chat_id,
        received_at=msg.date,
        kind="text",
        text=text,
        linked_url=linked_url,
    )

    pipeline = _get_pipeline(context)
    result = await pipeline.process(raw, thread_id=thread_id)
    await _dispatch_result(update, user_id, thread_id, result)


async def handle_lint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /lint <kb_slug> — runs a structural audit on the specified KB."""
    if not await _auth_guard(update):
        return

    text = (update.message.text or "").strip()
    parts = text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await update.message.reply_text("Usage: /lint <kb_slug>")
        return

    kb_slug = parts[1].strip()
    vault_root = VAULT_REPO_PATH
    user_id = update.effective_user.id

    await update.message.reply_text(f"Running lint on {kb_slug}…")
    try:
        result = await lint_agent.run(
            vault_root=vault_root,
            kb_slug=kb_slug,
            thread_id=f"lint:{user_id}:{kb_slug}",
        )
        await update.message.reply_text(result["summary"] or "Lint complete.")
    except Exception as exc:
        logger.exception("Lint failed for kb_slug=%s user_id=%s: %s", kb_slug, user_id, exc)
        await update.message.reply_text(f"Lint failed: {exc}")


async def _dispatch_result(
    update: Update, user_id: int, thread_id: str, result: dict,
    link_url: str | None = None,
) -> None:
    from atlasmind.edge import session

    if "reply" in result:
        sent = await update.message.reply_text(result["reply"])
        if link_url is not None:
            url_registry.register(user_id, sent.message_id, link_url)
        session.drop(user_id)
    elif "interrupt_question" in result:
        await update.message.reply_text(result["interrupt_question"])
        session.set_active(user_id, thread_id, expecting="answer")
    elif "error" in result:
        await update.message.reply_text(f"Error: {result['error']}")
        session.drop(user_id)
