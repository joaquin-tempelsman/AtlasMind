"""L1: RawMessage → NormalizedItem.

Single entry point: normalize(raw, *, transcriber, link_fetcher, vault_root).
"""
from __future__ import annotations

from pathlib import Path

from atlasmind.ingestion.link_fetcher import LinkFetcher
from atlasmind.ingestion.transcriber import Transcriber
from atlasmind.shared.types import NormalizedItem, RawMessage
from atlasmind.vault import fs as vault_fs
from atlasmind.vault.paths import link_html_filename, raw_capture_filename


def _persist_raw_capture(raw: RawMessage, meta: dict, vault_root: Path | None) -> None:
    """Save the verbatim input to raw/captures/ (original language, untranslated).

    Records the repo-relative path in meta["raw_capture_path"]. No-op when no
    vault_root is given or the text is empty/whitespace.
    """
    text = raw.text or ""
    if vault_root is None or not text.strip():
        return
    rel = raw_capture_filename(raw.received_at, text)
    body = (
        f"---\ntype: raw_capture\nsource_kind: {raw.kind}\n"
        f"received_at: {raw.received_at.isoformat()}\n"
        f"telegram_user_id: {raw.telegram_user_id}\n---\n\n{text}"
    )
    vault_fs.write_md(vault_root, rel, body)
    meta["raw_capture_path"] = rel


async def normalize(
    raw: RawMessage,
    *,
    transcriber: Transcriber | None = None,
    link_fetcher: LinkFetcher | None = None,
    vault_root: Path | None = None,
) -> NormalizedItem:
    if raw.kind == "text":
        meta: dict = {}
        if raw.linked_url:
            meta["linked_url"] = raw.linked_url
        _persist_raw_capture(raw, meta, vault_root)
        return NormalizedItem(
            received_at=raw.received_at,
            text=(raw.text or "").strip(),
            source_kind="text",
            source_meta=meta,
            telegram_user_id=raw.telegram_user_id,
        )

    if raw.kind == "voice":
        meta = {"voice_file_id": raw.voice_file_id}
        if raw.linked_url:
            meta["linked_url"] = raw.linked_url
        _persist_raw_capture(raw, meta, vault_root)
        return NormalizedItem(
            received_at=raw.received_at,
            text=raw.text or "",
            source_kind="voice",
            source_meta=meta,
            telegram_user_id=raw.telegram_user_id,
        )

    if raw.kind == "link":
        if link_fetcher is None:
            raise ValueError("link_fetcher is required for kind='link'")
        url = raw.url or raw.text or ""
        article_text, meta = await link_fetcher.fetch(url)

        if vault_root is not None:
            html_rel = link_html_filename(raw.received_at, url)
            vault_fs.write_md(vault_root, html_rel, article_text)
            meta["html_path"] = html_rel

        # Store full article text in meta for optional downstream use.
        # NormalizedItem.text holds only a short repr to keep agent context lean.
        meta["raw_article_text"] = article_text
        title = meta.get("title", "")
        short_repr = f"[Link] {title}\nURL: {url}" if title else f"[Link] {url}"

        return NormalizedItem(
            received_at=raw.received_at,
            text=short_repr,
            source_kind="link",
            source_meta=meta,
            telegram_user_id=raw.telegram_user_id,
        )

    raise ValueError(f"Unknown RawMessage kind: {raw.kind!r}")
