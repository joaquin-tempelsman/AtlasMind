"""Entry point: starts the Telegram application."""
from __future__ import annotations

from atlasmind.config import TELEGRAM_BOT_TOKEN
from atlasmind.edge.telegram_app import build_app


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")
    app = build_app(TELEGRAM_BOT_TOKEN)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
