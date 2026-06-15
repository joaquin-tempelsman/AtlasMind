# 01 — Architecture

## Purpose

Define the layers, what each owns, and the contracts between them. No code; just modules, boundaries, and data shapes.

---

## 1. Layered view

```
┌─────────────────────────────────────────────────────────────────┐
│  L0  Edge: Telegram                                             │
│      python-telegram-bot Application + handlers                 │
│      Owns: receiving messages, replying, session bookkeeping    │
└──────────────────────────────┬──────────────────────────────────┘
                               │  RawMessage
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  L1  Ingestion: source normalization                            │
│      transcriber (audio→text), link_fetcher (url→text)          │
│      Owns: turning any input into NormalizedItem                │
└──────────────────────────────┬──────────────────────────────────┘
                               │  NormalizedItem
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  L2  Routing agent (LangChain 1.0)                              │
│      Sees: KB registry, recent general_log.md entries           │
│      Owns: picking the target KB, appending to general_log.md   │
└──────────────────────────────┬──────────────────────────────────┘
                               │  RoutedItem
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  L3  KB ingestion agent (LangChain 1.0)                         │
│      Sees: ONE KB only — its agent.md, index.md, recent log     │
│      Owns: writing the note, updating entity/concept pages,     │
│             updating index.md and log.md, frontmatter           │
└──────────────────────────────┬──────────────────────────────────┘
                               │  IngestionResult
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  L4  Vault git layer                                            │
│      git pull → write → commit → push                           │
│      Owns: durability, history, conflict surfacing              │
└─────────────────────────────────────────────────────────────────┘
```

**One direction.** Layers do not call upward. The only way state flows back to the user is via:
- a final reply on the Telegram side, or
- a `langgraph.types.interrupt()` raised inside an agent tool, propagated back to L0 to ask the user a question (HITL).

---

## 2. Why two agent layers (not one)

This is the most important design decision in v0. Restated from the PRD:

- **Router context is small and stable.** Only needs the KB roster and recent routing decisions. Cheap, fast, and the prompt rarely changes.
- **KB ingestion context is large and KB-specific.** Each KB has its own conventions, entity types, and `agent.md`. Putting it all in one mega-prompt would be slow, expensive, and brittle. KB isolation is a real architectural property, not a soft preference.
- **It mirrors the PRD's "agent layer 1 / agent layer 2" framing** verbatim.

Both layers use `langchain.agents.create_agent` from LangChain 1.0 — same primitive, different scopes.

---

## 3. Core data shapes (contracts)

These are the only objects that cross layer boundaries in v0. Defined as plain Python `dataclass` / `TypedDict` (final choice in [`05_agent_layer.md`](05_agent_layer.md)).

### `RawMessage` (L0 → L1)
```
- telegram_user_id: int
- chat_id: int
- received_at: datetime  (UTC, ISO-8601 when serialized)
- kind: "text" | "voice" | "link"   # link = text msg that is a single URL
- text: str | None                  # None for voice until transcribed
- voice_file_id: str | None
- url: str | None
- linked_url: str | None            # set when a voice/text msg is a Telegram reply to a URL msg
- raw_payload: dict                 # original update for debugging only
```

**URL reply linking (L0):** When a URL message arrives, L0 stores the message_id → URL mapping in a per-user `UrlRegistry` (24h TTL, module-level, separate from session). When any subsequent voice or text message arrives with `reply_to_message`, L0 checks the registry and, if matched, sets `linked_url` on the `RawMessage`. The KB ingestion agent (L3) uses this to associate commentary with the linked article and to call `extract_url_metadata` when the KB is configured with `url_metadata_fields`.

### `NormalizedItem` (L1 → L2)
```
- received_at: datetime
- text: str                         # the canonical text representation
- source_kind: "voice" | "text" | "link"
- source_meta: dict                 # {"url": ..., "title": ..., "duration_s": ..., "raw_capture_path": ...}
- telegram_user_id: int             # author/owner — single-tenant in v0
```

**Raw capture (L1).** For `text` and `voice` inputs, L1 persists the verbatim text —
in its original language, untranslated — to `raw/captures/<ts>__<hash>.md` in the vault
(mirroring the `raw/links/` snapshot for `link` inputs) and records the repo-relative
path in `source_meta["raw_capture_path"]`. This guarantees the user's original words
survive even when the KB ingestion agent rewrites the note in another language (see
[`06_kb_contract.md` §6](06_kb_contract.md)). `NormalizedItem.text` is unchanged — it
still carries the original text the agents read.

### `RoutedItem` (L2 → L3)
```
- normalized: NormalizedItem
- kb_slug: str                      # e.g. "personal-diary", "econ-politics"
- routing_rationale: str            # one-line "why this KB" for general_log.md
- confidence: "high" | "medium" | "low"   # router self-report
```

### `IngestionResult` (L3 → L4)
```
- kb_slug: str
- note_path: str                    # repo-relative, e.g. "personal-diary/2026-05-02-coffee-with-mateo.md"
- pages_touched: list[str]          # all repo-relative paths the agent wrote/updated
- commit_message: str               # built by L3, executed by L4
- summary_for_user: str             # what to send back via Telegram
```

These are the *only* shapes that are stable across layers. Everything else (frontmatter formats, agent tool signatures, etc.) is internal to a layer and can change without touching neighbors.

---

## 4. Dependency graph (modules)

```
edge.telegram          ─┐
                        ├─→ ingestion.normalize ─→ agent.router ─→ agent.kb_ingestion ─→ vault.git
edge.session            ─┘                                                 │
                                                                           ├─→ vault.fs
                                                                           └─→ vault.frontmatter
shared.config       ←  (everyone imports this)
shared.kb_registry  ←  (router + kb_ingestion)
shared.types        ←  (everyone — RawMessage etc.)
```

Rules:
- `edge.*` does not import `agent.*` directly. It calls a single function `pipeline.process(raw_message)` exposed by an orchestrator module. This keeps Telegram-specific code out of agent code and makes a future CLI entry point trivial.
- `agent.*` does not import `edge.*`. Agents communicate "I need user input" by raising a LangGraph `interrupt()` from a tool — never by knowing about Telegram.
- `vault.*` is the only layer allowed to touch `subprocess` for git. Agents update files via vault tools.

---

## 5. Synchronous vs. async

Use `asyncio` end-to-end. `python-telegram-bot` v21 handlers are async; LangChain 1.0 supports `agent.ainvoke`. talkvault's pattern works directly: handlers `await pipeline.process(...)`, the pipeline `awaits` `agent.ainvoke(...)`, agent tools that hit disk are sync (the wins from making them async are negligible at this scale and `subprocess.run` for git is fine).

The git layer remains **synchronous** under the async pipeline, intentionally:
- Concurrent writes to the same vault repo would be a footgun.
- v0 is single-user; one ingest at a time is acceptable.
- An `asyncio.Lock` around the git critical section serializes ingests if two messages arrive within the same window.

---

## 6. Failure modes (architecture-level)

| Failure | Where it manifests | Response |
|---|---|---|
| Telegram update arrives during another ingest | L0 | Queue via `asyncio.Lock`, reply "queued" if wait > 2s |
| Whisper transcription fails | L1 | Reply error to user; do not call agents; do not commit |
| Router picks an unknown KB | L2 | Validation against `shared.kb_registry`; re-prompt with explicit list, then ask user via interrupt if still ambiguous |
| KB ingestion agent crashes mid-write | L3 | Files left in working tree; git layer detects partial state via `git status` and aborts the commit; user is told to inspect the vault |
| Git push rejected (remote moved ahead) | L4 | `pull --rebase`, retry once; if still rejected, leave commit local and surface the conflict |
| Git pull conflicts on inbound | L4 | Abort the ingest, reply with the conflicting files; user resolves manually in Obsidian/VSCode |

We **do not** build automatic conflict resolution in v0. Wikis are markdown; humans resolve.
