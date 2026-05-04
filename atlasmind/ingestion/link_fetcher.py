"""URL fetching and article extraction.

Defines the LinkFetcher Protocol and the v0 readability-lxml implementation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

import httpx
from readability import Document


class LinkFetchError(RuntimeError):
    """Raised when a URL cannot be fetched or yields empty article text."""


@runtime_checkable
class LinkFetcher(Protocol):
    async def fetch(self, url: str) -> tuple[str, dict]: ...


class ReadabilityLinkFetcher:
    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout

    async def fetch(self, url: str) -> tuple[str, dict]:
        """Fetch url, extract main article text and title.

        Returns (text, meta) where meta includes url, title, fetched_at.
        Raises LinkFetchError on HTTP errors or empty body.
        """
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise LinkFetchError(f"HTTP {exc.response.status_code} fetching {url}") from exc
            except httpx.RequestError as exc:
                raise LinkFetchError(f"Network error fetching {url}: {exc}") from exc

        html = response.text
        doc = Document(html)
        title = doc.title() or ""
        body_html = doc.summary(html_partial=True)

        # Strip HTML tags from the body for plain text
        import re
        plain = re.sub(r"<[^>]+>", " ", body_html)
        plain = re.sub(r"\s+", " ", plain).strip()

        if not plain:
            raise LinkFetchError(f"Article extraction returned empty body for {url}")

        text = f"{title}\n\n{plain}" if title else plain

        meta = {
            "url": url,
            "title": title,
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        return text, meta
