"""Pipeline (L1.5 bridge): process a RawMessage end-to-end.

Owns the per-KB IngestQueue with asyncio debounce timers. Coordinates
normalize → route → queue → ingest.

Usage:
    pipeline = Pipeline(vault_root=VAULT_REPO_PATH)
    result = await pipeline.process(raw, thread_id=str(user_id))
    result = await pipeline.resume(thread_id=..., answer=..., user_id=user_id)

Return shapes:
    {"reply": str}             — final answer, drop session
    {"interrupt_question": str} — agent paused, set expecting="answer"
    {"error": str}             — something failed, drop session
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable

from atlasmind.agents.amendment import classify_amendment
from atlasmind.agents.kb_ingestion import ingest, resume_ingest
from atlasmind.agents.router import route, resume_route
from atlasmind.ingestion.normalize import normalize
from atlasmind.shared.types import RawMessage, RoutedItem
from atlasmind.vault import git_sync

logger = logging.getLogger(__name__)

_DEFAULT_INGEST_DELAY = 300  # 5 minutes


class Pipeline:
    """Stateful pipeline instance. One per bot application."""

    def __init__(
        self,
        vault_root: Path,
        ingest_delay_seconds: float = _DEFAULT_INGEST_DELAY,
        reply_fn: Callable[[int, str], Awaitable[None]] | None = None,
    ) -> None:
        self.vault_root = vault_root
        self.ingest_delay_seconds = ingest_delay_seconds
        self.reply_fn = reply_fn

        # Per-KB ingest queue and debounce timer handles
        self._queues: dict[str, list[RoutedItem]] = {}
        self._timers: dict[str, asyncio.TimerHandle] = {}

        # Tracks router-interrupted sessions: thread_id → normalized_item
        self._pending_route: dict[str, object] = {}

        # Tracks kb-ingestion-interrupted sessions: thread_id → (kb_slug, user_id)
        self._pending_ingest: dict[str, tuple[str, int]] = {}

        # Tracks proposed batch amendments awaiting yes/no:
        # thread_id → {kb_slug, item_index, old_text, new_text}
        self._pending_amendments: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process(self, raw: RawMessage, thread_id: str) -> dict:
        """Normalize, route, and queue a RawMessage.

        Returns {"reply"}, {"interrupt_question"}, or {"error"}.
        """
        try:
            normalized = await normalize(raw, vault_root=self.vault_root)
        except Exception as exc:
            logger.exception("normalize failed: %s", exc)
            return {"error": str(exc)}

        user_id = raw.telegram_user_id

        # If a batch is already pending, this message might be a correction of a
        # queued item rather than a new one. Classify before routing.
        pending = self._pending_items_for_user(user_id)
        if pending:
            try:
                verdict = await classify_amendment(
                    pending=[item.text for _slug, _idx, item in pending],
                    new_text=normalized.text,
                )
            except Exception as exc:
                logger.exception("classify_amendment failed: %s", exc)
                verdict = {"kind": "new"}

            if verdict.get("kind") == "modification":
                return self._propose_amendment(thread_id, user_id, pending, verdict)

        try:
            route_result = await route(normalized, self.vault_root, thread_id)
        except Exception as exc:
            logger.exception("route failed: %s", exc)
            return {"error": f"Routing failed: {exc}"}

        if "interrupt_question" in route_result:
            self._pending_route[thread_id] = normalized
            return {"interrupt_question": route_result["interrupt_question"]}

        return self._enqueue(
            kb_slug=route_result["kb_slug"],
            rationale=route_result.get("rationale", ""),
            confidence=route_result.get("confidence", "medium"),
            normalized=normalized,
            user_id=raw.telegram_user_id,
        )

    async def resume(self, thread_id: str, answer: str, user_id: int) -> dict:
        """Resume a HITL-interrupted session with a user answer.

        Returns {"reply"}, {"interrupt_question"}, or {"error"}.
        """
        # Check if we're confirming a proposed batch amendment
        if thread_id in self._pending_amendments:
            return self._resolve_amendment(thread_id, answer, user_id)

        # Check if we're in a router interrupt
        if thread_id in self._pending_route:
            normalized = self._pending_route.pop(thread_id)
            try:
                route_result = await resume_route(answer, self.vault_root, thread_id)
            except Exception as exc:
                logger.exception("resume_route failed: %s", exc)
                return {"error": f"Resume routing failed: {exc}"}

            if "interrupt_question" in route_result:
                self._pending_route[thread_id] = normalized
                return {"interrupt_question": route_result["interrupt_question"]}

            return self._enqueue(
                kb_slug=route_result["kb_slug"],
                rationale=route_result.get("rationale", ""),
                confidence=route_result.get("confidence", "medium"),
                normalized=normalized,
                user_id=user_id,
            )

        # Check if we're in a kb-ingestion interrupt
        if thread_id in self._pending_ingest:
            kb_slug, orig_user_id = self._pending_ingest.pop(thread_id)
            try:
                ingest_result = await resume_ingest(
                    answer, self.vault_root, kb_slug, thread_id
                )
            except Exception as exc:
                logger.exception("resume_ingest failed: %s", exc)
                return {"error": f"Resume ingestion failed: {exc}"}

            if "interrupt_question" in ingest_result:
                self._pending_ingest[thread_id] = (kb_slug, orig_user_id)
                return {"interrupt_question": ingest_result["interrupt_question"]}

            summary = ingest_result.get("summary", "Ingested.")
            return {"reply": summary}

        return {"error": "No active session to resume."}

    # ------------------------------------------------------------------
    # Internal queue helpers
    # ------------------------------------------------------------------

    def _enqueue(
        self,
        *,
        kb_slug: str,
        rationale: str,
        confidence: str,
        normalized: object,
        user_id: int,
    ) -> dict:
        from atlasmind.shared.types import RoutedItem

        routed = RoutedItem(
            normalized=normalized,
            kb_slug=kb_slug,
            routing_rationale=rationale,
            confidence=confidence,
        )
        if kb_slug not in self._queues:
            self._queues[kb_slug] = []
        self._queues[kb_slug].append(routed)

        self._arm_timer(kb_slug, user_id)

        kb_display = kb_slug.replace("-", " ").title()
        return {"reply": f"Routed to {kb_display} — will ingest shortly."}

    def _arm_timer(self, kb_slug: str, user_id: int) -> None:
        """(Re)start the debounce timer for a KB — resets the quiet window."""
        if kb_slug in self._timers:
            self._timers[kb_slug].cancel()

        loop = asyncio.get_running_loop()
        self._timers[kb_slug] = loop.call_later(
            self.ingest_delay_seconds,
            lambda slug=kb_slug, uid=user_id: loop.create_task(
                self._fire_ingest(slug, uid)
            ),
        )

    # ------------------------------------------------------------------
    # Batch amendment helpers
    # ------------------------------------------------------------------

    def _pending_items_for_user(self, user_id: int):
        """Flatten the queues into a numbered list of pending items for the user.

        Single-tenant in v0: every queued item belongs to the one user. Returns
        a list of (kb_slug, index_within_kb_queue, NormalizedItem).
        """
        out = []
        for kb_slug, routed_items in self._queues.items():
            for idx, routed in enumerate(routed_items):
                out.append((kb_slug, idx, routed.normalized))
        return out

    def _format_batch(self, user_id: int) -> str:
        pending = self._pending_items_for_user(user_id)
        if not pending:
            return "Pending batch is empty."
        lines = [
            f"{n}. {item.text}" for n, (_slug, _idx, item) in enumerate(pending, start=1)
        ]
        return "Pending batch:\n" + "\n".join(lines)

    def _propose_amendment(
        self, thread_id: str, user_id: int, pending: list, verdict: dict
    ) -> dict:
        """Store a proposed amendment and return the yes/no interrupt question."""
        target = verdict["target_index"]
        kb_slug, idx, item = pending[target]
        old_text = item.text
        new_text = verdict["new_text"]

        self._pending_amendments[thread_id] = {
            "kb_slug": kb_slug,
            "item_index": idx,
            "old_text": old_text,
            "new_text": new_text,
        }
        # An amendment is activity — keep the batch from flushing mid-confirmation.
        self._arm_timer(kb_slug, user_id)

        question = (
            f"Change item {target + 1}:\n"
            f"  '{old_text}'\n"
            f"→ '{new_text}'\n"
            f"(yes/no)"
        )
        return {"interrupt_question": question}

    def _resolve_amendment(self, thread_id: str, answer: str, user_id: int) -> dict:
        """Apply or discard a proposed amendment based on the user's yes/no reply."""
        proposal = self._pending_amendments.pop(thread_id)
        kb_slug = proposal["kb_slug"]
        idx = proposal["item_index"]

        queue = self._queues.get(kb_slug, [])
        # Guard the race where the batch already flushed while awaiting the reply.
        if idx >= len(queue) or queue[idx].normalized.text != proposal["old_text"]:
            return {
                "reply": "That batch was already processed — send it again to make the change."
            }

        if _is_affirmative(answer):
            queue[idx].normalized.text = proposal["new_text"]
            self._arm_timer(kb_slug, user_id)
            return {"reply": "Updated. " + self._format_batch(user_id)}

        self._arm_timer(kb_slug, user_id)
        return {"reply": "Kept original. " + self._format_batch(user_id)}

    async def _fire_ingest(self, kb_slug: str, user_id: int) -> None:
        items = self._queues.pop(kb_slug, [])
        self._timers.pop(kb_slug, None)
        if not items:
            return

        # Use the user_id as ingest thread_id (scoped to kb to avoid collision)
        ingest_thread_id = f"{user_id}:{kb_slug}"
        try:
            result = await ingest(items, self.vault_root, ingest_thread_id)
        except Exception as exc:
            logger.exception("ingest failed for kb=%s: %s", kb_slug, exc)
            await self._send_reply(user_id, f"Ingestion failed: {exc}")
            return

        if "interrupt_question" in result:
            self._pending_ingest[ingest_thread_id] = (kb_slug, user_id)
            await self._send_reply(user_id, result["interrupt_question"])
            return

        summary = result.get("summary", "Ingested.")

        # Commit vault changes produced by the agent
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: _vault_commit(self.vault_root, kb_slug, items),
            )
        except Exception as exc:
            logger.exception("vault commit failed for kb=%s: %s", kb_slug, exc)
            await self._send_reply(user_id, f"Ingested but vault commit failed: {exc}")
            return

        await self._send_reply(user_id, summary)

    # ------------------------------------------------------------------

    async def _send_reply(self, user_id: int, text: str) -> None:
        if self.reply_fn is not None:
            try:
                await self.reply_fn(user_id, text)
            except Exception:
                logger.exception("reply_fn failed for user_id=%s", user_id)


_AFFIRMATIVE = {
    "yes", "y", "yeah", "yep", "yup", "ok", "okay", "sure", "correct", "right",
    "apply", "do it", "confirm", "confirmed", "si", "sí", "claro", "dale", "hazlo",
}
_NEGATIVE = {
    "no", "n", "nope", "nah", "cancel", "leave", "keep", "stop", "don't", "dont",
    "negative", "no gracias", "dejalo", "déjalo",
}


def _is_affirmative(answer: str) -> bool:
    """Pragmatic EN/ES yes/no check for amendment confirmation.

    Defaults to True only on a clear affirmative; an unrecognized or clearly
    negative reply is treated as a rejection (the safe choice — leaves the
    queued text untouched).
    """
    text = answer.strip().lower().rstrip(".!")
    if not text:
        return False
    if text in _AFFIRMATIVE:
        return True
    if text in _NEGATIVE:
        return False
    first = text.split()[0]
    return first in _AFFIRMATIVE


def _vault_commit(vault_root: Path, kb_slug: str, items: list) -> None:
    """Pull, commit all agent-written files, and push (if remote exists)."""
    git_sync.pull(vault_root)
    source = items[0].normalized.source_kind if items else "text"
    message = (
        f"note({kb_slug}): batch of {len(items)} item(s)\n\n"
        f"source: {source}"
    )
    git_sync.commit(vault_root, message)
    git_sync.push(vault_root)
