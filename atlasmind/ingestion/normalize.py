"""L1: RawMessage → NormalizedItem.

Single entry point: normalize(raw, *, transcriber, link_fetcher, vault_root).
"""
from __future__ import annotations

from pathlib import Path

from atlasmind.ingestion.link_fetcher import LinkFetcher, LinkFetchError
from atlasmind.ingestion.transcriber import Transcriber
from atlasmind.shared.types import NormalizedItem, RawMessage
from atlasmind.vault import fs as vault_fs
from atlasmind.vault.paths import link_html_filename


async def normalize(
    raw: RawMessage,
    *,
    transcriber: Transcriber | None = None,
    link_fetcher: LinkFetcher | None = None,
    vault_root: Path | None = None,
) -> NormalizedItem:
    if raw.kind == "text":
        return NormalizedItem(
            received_at=raw.received_at,
            text=(raw.text or "").strip(),
            source_kind="text",
            source_meta={},
            telegram_user_id=raw.telegram_user_id,
        )

    if raw.kind == "voice":
        text = raw.text or ""
        return NormalizedItem(
            received_at=raw.received_at,
            text=text,
            source_kind="voice",
            source_meta={
                "voice_file_id": raw.voice_file_id,
            },
            telegram_user_id=raw.telegram_user_id,
        )

    if raw.kind == "link":
        if link_fetcher is None:
            raise ValueError("link_fetcher is required for kind='link'")
        url = raw.url or raw.text or ""
        text, meta = await link_fetcher.fetch(url)

        if vault_root is not None:
            html_rel = link_html_filename(raw.received_at, url)
            # Persist raw HTML — requires a separate fetch or we store the extracted text only.
            # We store the extracted text as a placeholder; the full HTML path is recorded in meta.
            vault_fs.write_md(vault_root, html_rel, text)
            meta["html_path"] = html_rel

        return NormalizedItem(
            received_at=raw.received_at,
            text=text,
            source_kind="link",
            source_meta=meta,
            telegram_user_id=raw.telegram_user_id,
        )

    raise ValueError(f"Unknown RawMessage kind: {raw.kind!r}")
