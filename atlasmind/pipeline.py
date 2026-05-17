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

        # Reset the debounce timer
        if kb_slug in self._timers:
            self._timers[kb_slug].cancel()

        loop = asyncio.get_running_loop()
        self._timers[kb_slug] = loop.call_later(
            self.ingest_delay_seconds,
            lambda slug=kb_slug, uid=user_id: loop.create_task(
                self._fire_ingest(slug, uid)
            ),
        )

        kb_display = kb_slug.replace("-", " ").title()
        return {"reply": f"Routed to {kb_display} — will ingest shortly."}

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
