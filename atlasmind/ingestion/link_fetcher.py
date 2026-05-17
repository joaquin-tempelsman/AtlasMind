"""URL fetching and article extraction.

Defines the LinkFetcher Protocol and the v0 readability-lxml implementation.
"""
from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

import httpx
from readability import Document

from atlasmind.vault.frontmatter import utc_now_iso


class LinkFetchError(RuntimeError):
    """Raised when a URL cannot be fetched or yields empty article text."""


@runtime_checkable
class LinkFetcher(Protocol):
    async def fetch(self, url: str) -> tuple[str, dict]: ...


class ReadabilityLinkFetcher:
    def __init__(self, timeout: float = 10.0) -> None:
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    async def fetch(self, url: str) -> tuple[str, dict]:
        """Fetch url, extract main article text and title.

        Returns (text, meta) where meta includes url, title, fetched_at.
        Raises LinkFetchError on HTTP errors or empty body.
        """
        try:
            response = await self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LinkFetchError(f"HTTP {exc.response.status_code} fetching {url}") from exc
        except httpx.RequestError as exc:
            raise LinkFetchError(f"Network error fetching {url}: {exc}") from exc

        doc = Document(response.text)
        title = doc.title() or ""
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", doc.summary(html_partial=True))).strip()

        if not plain:
            raise LinkFetchError(f"Article extraction returned empty body for {url}")

        text = f"{title}\n\n{plain}" if title else plain
        return text, {"url": url, "title": title, "fetched_at": utc_now_iso()}

    async def aclose(self) -> None:
        await self._client.aclose()
