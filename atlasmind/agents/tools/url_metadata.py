"""URL metadata extraction tool for KB ingestion agents.

Fetches a URL and uses claude-haiku to extract structured metadata fields
(e.g. media_source, article_writer) without forwarding the full article text.
"""
from __future__ import annotations

import json
import logging

import anthropic
from langchain_core.tools import tool

from atlasmind.ingestion.link_fetcher import LinkFetcher

logger = logging.getLogger(__name__)

_HAIKU_MODEL = "claude-haiku-4-5-20251001"
_MAX_ARTICLE_CHARS = 4000


def make_extract_url_metadata_tool(link_fetcher: LinkFetcher):
    """Return an extract_url_metadata tool bound to the given link_fetcher."""

    @tool
    async def extract_url_metadata(url: str, fields: list[str]) -> dict:
        """Fetch a URL and extract structured metadata fields via LLM.

        Use this for link items or voice/text items with a linked_url when the
        KB is configured with url_metadata_fields. Do NOT use to retrieve full
        article content — call this only for metadata extraction.

        Args:
            url: The URL to fetch metadata from.
            fields: List of field names to extract (e.g. ["media_source", "article_writer"]).

        Returns:
            Dict mapping each requested field name to its extracted value.
            Unknown fields are returned as empty strings.
        """
        try:
            article_text, _meta = await link_fetcher.fetch(url)
        except Exception as exc:
            logger.warning("URL fetch failed for %s: %s", url, exc)
            return {f: "" for f in fields}

        fields_str = ", ".join(fields)
        prompt = (
            f"Extract the following metadata from this article: {fields_str}.\n"
            f"Return ONLY a JSON object with those exact keys and string values.\n"
            f"If a field cannot be determined, use an empty string.\n\n"
            f"Article (first {_MAX_ARTICLE_CHARS} chars):\n"
            f"{article_text[:_MAX_ARTICLE_CHARS]}"
        )

        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        # Strip markdown code fence if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("extract_url_metadata: JSON parse failed for response: %r", raw)
            return {f: "" for f in fields}

        return {f: str(result.get(f, "")) for f in fields}

    return extract_url_metadata
