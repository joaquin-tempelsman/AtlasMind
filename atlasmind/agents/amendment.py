"""Amendment classifier — decide if an incoming message is a new item or a
correction of one already pending in the ingest queue.

A single cheap claude-haiku call (no tools, no graph), mirroring
`extract_url_metadata` in tools/url_metadata.py. Contract and behavior are
specified in dev_specs/05_agent_layer.md §3.5.

    {"kind": "new"}
    {"kind": "modification", "target_index": int, "new_text": str, "rationale": str}

On anything ambiguous — empty pending, parse failure, out-of-range index, or an
LLM/API error — it fails safe to {"kind": "new"} so a wrong item is never
silently rewritten.
"""
from __future__ import annotations

import json
import logging

import anthropic

logger = logging.getLogger(__name__)

_HAIKU_MODEL = "claude-haiku-4-5-20251001"
_MAX_ITEM_CHARS = 2000

_NEW: dict = {"kind": "new"}


def _build_prompt(pending: list[str], new_text: str) -> str:
    listing = "\n".join(
        f"[{i}] {text[:_MAX_ITEM_CHARS]}" for i, text in enumerate(pending)
    )
    return (
        "You are a classifier for a note-taking system. A user has the following "
        "messages queued, waiting to be filed. They have NOT been saved yet.\n\n"
        f"Pending messages (0-indexed):\n{listing}\n\n"
        f"New incoming message:\n{new_text}\n\n"
        "Decide whether the new message is a BRAND-NEW note, or a CORRECTION of one "
        "of the pending messages (e.g. fixing a misspelled name, rewording a garbled "
        "dictation, or changing a detail).\n\n"
        "Return ONLY a JSON object, no prose. One of:\n"
        '  {"kind": "new"}\n'
        '  {"kind": "modification", "target_index": <int>, '
        '"new_text": "<the full corrected text of that pending message>", '
        '"rationale": "<one short line>"}\n\n'
        "Rules:\n"
        "- target_index must be one of the indices shown above.\n"
        "- new_text is the COMPLETE replacement text for that pending message, with "
        "the correction applied — not just the diff.\n"
        "- If you are not confident it is a correction, choose \"new\".\n"
    )


async def classify_amendment(pending: list[str], new_text: str) -> dict:
    """Classify `new_text` as a new item or a correction of a pending item.

    Args:
        pending: ordered texts of the items currently queued for the user.
        new_text: the incoming message.

    Returns:
        {"kind": "new"} or
        {"kind": "modification", "target_index": int, "new_text": str, "rationale": str}.
    """
    if not pending:
        return dict(_NEW)

    prompt = _build_prompt(pending, new_text)
    try:
        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
    except Exception as exc:  # network / API / SDK error — fail safe
        logger.warning("classify_amendment: LLM call failed: %s", exc)
        return dict(_NEW)

    # Strip a markdown code fence if the model wrapped the JSON.
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("classify_amendment: JSON parse failed for response: %r", raw)
        return dict(_NEW)

    if not isinstance(data, dict) or data.get("kind") != "modification":
        return dict(_NEW)

    target_index = data.get("target_index")
    corrected = data.get("new_text")
    if (
        not isinstance(target_index, int)
        or isinstance(target_index, bool)
        or not (0 <= target_index < len(pending))
        or not isinstance(corrected, str)
        or not corrected.strip()
    ):
        logger.warning("classify_amendment: invalid modification payload: %r", data)
        return dict(_NEW)

    return {
        "kind": "modification",
        "target_index": target_index,
        "new_text": corrected,
        "rationale": str(data.get("rationale", "")),
    }
