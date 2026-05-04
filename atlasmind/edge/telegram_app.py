"""Bootstrap the python-telegram-bot Application."""
from __future__ import annotations

from pathlib import Path

from telegram.ext import Application, MessageHandler, filters

from atlasmind.config import VAULT_REPO_PATH
from atlasmind.edge.handlers import handle_text, handle_voice
from atlasmind.pipeline import Pipeline


def _make_reply_fn(app: Application):
    async def reply_fn(user_id: int, text: str) -> None:
        await app.bot.send_message(chat_id=user_id, text=text)

    return reply_fn


def build_app(token: str, vault_root: Path | None = None) -> Application:
    """Build and return a configured Application (does not start polling)."""
    if vault_root is None:
        vault_root = VAULT_REPO_PATH

    app = Application.builder().token(token).build()

    pipeline = Pipeline(vault_root=vault_root, reply_fn=_make_reply_fn(app))
    app.bot_data["pipeline"] = pipeline

    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app
