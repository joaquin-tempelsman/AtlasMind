# AtlasMind — v0 Development Spec

**Status:** Draft v0 · 2026-05-02
**Scope:** This spec defines the v0 architecture and contracts for AtlasMind. It is meant to guide development end-to-end without prescribing concrete code. Items listed in [`PRD: To be included features after v0`](../base_docs/) are explicitly **out of scope** here and only appear in the deferred map at the end.

---

## 1. What we are building

AtlasMind is a self-maintained, multi-KB personal knowledge system. The user feeds it raw input (text, audio, links) — exclusively through Telegram — and an agent layer classifies that input into one of several **isolated knowledge bases** (KBs), then maintains each KB as a structured, interlinked Obsidian vault.

The core pattern (per [`base_docs/llm_wiki.md`](../base_docs/llm_wiki.md)) is: the LLM owns the wiki layer, the human owns sourcing and direction. AtlasMind extends that pattern from one wiki to **many**, governed by a routing layer and a single git-versioned monorepo.

### Interaction model

The user interacts with the system **exclusively via the Telegram bot**. The Obsidian vault is a read-only artifact for the user — they can open it in Obsidian to browse and inspect their knowledge, but should not edit it directly. Agent writes are the authoritative source of truth. The only intentional user edits are:
- `routing_rules.md` — soft routing hints the user refines over time
- `agent.md` per KB — schema evolution (entity types, frontmatter fields, tone)

### Knowledge bases

KBs are defined in **one place only**: [`kb_definitions/kb_definitions.md`](../kb_definitions/kb_definitions.md). This file is user-owned and drives all KB scaffolding. The system treats KBs generically — it does not hardcode any KB by name. Adding a new KB means adding an entry to `kb_definitions.md` and running `setup.sh --bootstrap-vault`.

Each KB can be **enabled or disabled** individually (`active: true/false`). Disabled KBs are ignored by the router and cannot receive new ingests. A disabled KB's existing vault content is preserved.

See [`kb_definitions/kb_definitions.example.md`](../kb_definitions/kb_definitions.example.md) for the template structure, and the actual `kb_definitions.md` for this instance's KBs.

### Non-goals for v0

These are deferred — see [`08_deferred_v0+1.md`](08_deferred_v0+1.md):
- Daily/weekly recall notifications
- Connection-suggestion replies on ingest
- Anniversary-style "1 year ago" surfacing
- `qmd` or any embedding-based search
- Firecrawl / proper headless browser scraping (v0 uses `readability-lxml`)
- Image asset auto-download with hotkeys
- Dataview integration polish (frontmatter is written, but query templates are not built)
- The full **Breathing system** (contradiction/repetition/evolution detection across time)

The Breathing layer is **disabled by default in v0**. The thin per-ingest breathing step is present in code but gated behind the per-KB `breathing` flag in `kb_definitions.md` (default `false`). Enable it per KB once the vault has enough content for connections to be meaningful.

---

## 2. Documents in this spec

Read in order. Each is short and contract-first.

1. [`01_architecture.md`](01_architecture.md) — Layered architecture, data flow, dependency graph
2. [`02_repo_layout.md`](02_repo_layout.md) — Code repo structure and the vault repo structure
3. [`03_telegram_layer.md`](03_telegram_layer.md) — Telegram I/O, sessions, transcription (talkvault learnings)
4. [`04_ingestion_layer.md`](04_ingestion_layer.md) — Source normalization (audio→text, link→text); batching queue
5. [`05_agent_layer.md`](05_agent_layer.md) — Routing agent, KB ingestion agent, breathing (disabled), LangChain 1.0 conventions
6. [`06_kb_contract.md`](06_kb_contract.md) — KB filesystem contract, `index.md`/`log.md`, frontmatter, schemas
7. [`07_git_versioning.md`](07_git_versioning.md) — Git strategy: monorepo, branch model, commit conventions, sync flow
8. [`08_deferred_v0+1.md`](08_deferred_v0+1.md) — Map of post-v0 features and where they hook in
9. [`09_open_questions.md`](09_open_questions.md) — Decisions we have explicitly punted on
10. [`10_development_plan.md`](10_development_plan.md) — Ordered build plan: phases, dependencies, what to build first

---

## 3. The one-paragraph contract

A user message lands in **Telegram**. The **Ingestion layer** normalizes it to plain text plus metadata (`text`, `source_kind`, `received_at`, optional `url`). A **Router agent** with minimum context — the list of KBs, KB descriptions, and a stratified sample from `general_log.md` — picks one KB. The routed item is placed in a **per-KB queue** with a configurable debounce window (default 5 minutes). When the timer fires, the **KB Ingestion agent** (scoped to that KB only) ingests all queued items in a single instantiation: reads the KB's `agent.md` schema, extracts entities, files new notes, updates affected wiki pages, appends to the KB's `index.md` and `log.md`, and writes a single git commit. Any human confirmation needed is performed via a **LangGraph interrupt** that routes back through Telegram. The vault is one git repo; one commit per batch ingest; the same repo is what the user browses in Obsidian.

---

## 4. Tech stack (locked)

- **Language:** Python 3.13 (matches user environment).
- **Agents:** `langchain >= 1.0` (`langchain.agents.create_agent`), `langgraph` for checkpointing and `interrupt()` HITL. (Pattern proven in talkvault.)
- **Telegram:** `python-telegram-bot` v21.x.
- **Audio transcription:** OpenAI Whisper API for v0 (cheapest path; pluggable behind a transcription interface — see [`04_ingestion_layer.md`](04_ingestion_layer.md)).
- **LLM:** OpenAI via `langchain_openai`. Model choice configurable per agent layer; default `gpt-4o` for routing/ingestion, smaller model for the summarization middleware.
- **Storage:** Plain markdown in a git repo. No database. No vector store in v0.
- **Config:** `.env` + `pyproject.toml`. No global state beyond a module-level agent singleton (matching talkvault's `bot/brain.py:_agent`).
- **Tests:** `pytest` + `pytest-asyncio`.
- **Setup:** `setup.sh` — single script for fresh-clone onboarding (see [`02_repo_layout.md`](02_repo_layout.md)).
- **Deploy:** GitHub Actions → Digital Ocean droplet on push to `main`.

Anything not on this list is a v0+1 decision.

---

## 5. How to read the rest of this spec

Each layer doc has the same shape:
- **Purpose** — one sentence.
- **Inputs / Outputs** — the contract.
- **Internal structure** — modules and what each owns.
- **Failure modes** — what can break and what we do about it.
- **Out of scope (v0)** — what we are deliberately *not* building yet.

If a doc and the PRD disagree, the PRD wins for *intent* and this spec wins for *implementation*. Update both when alignment slips.
