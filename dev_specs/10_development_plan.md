# 10 — Development Plan

## Purpose

Ordered build sequence for AtlasMind v0. Each phase is a shippable increment that can be tested in isolation. Do not start a phase until the prior one has passing tests.

---

## Guiding principles

- **Build bottom-up.** Vault layer before agents. Agents before edge. Everything before integration.
- **Test at every layer.** Each module gets tests before the next module builds on it.
- **Make it run end-to-end as early as possible.** A working but incomplete system beats a complete system that has never run.
- **KBs are generic from day one.** Nothing in the code references a specific KB by name. All KB-specific behavior comes from `kb_definitions.md` and `agent.md`.

---

## Phase 0 — Project scaffolding (Day 1)

Get a runnable skeleton with all contracts defined.

| Step | What | Why first |
|---|---|---|
| 0.1 | `pyproject.toml`, `requirements.txt`, `setup.sh` skeleton | Entry point for every future action |
| 0.2 | `shared/types.py` — `RawMessage`, `NormalizedItem`, `RoutedItem`, `IngestionResult` | Every layer imports these; define them first so imports don't change later |
| 0.3 | `config.py` — load `.env`, expose typed constants | All modules need config; do it once cleanly |
| 0.4 | `kb_definitions/kb_definitions.example.md` + `kb_definitions/kb_definitions.md` | Bootstrap needs this file; write yours first so you know what the system will scaffold |
| 0.5 | `bootstrap.py` — read `kb_definitions.md`, scaffold vault | Makes the vault exist so vault tests have something to work with |
| 0.6 | Complete `setup.sh` — deps, `.env` prompting, bootstrap call | End-to-end onboarding path; validates the scaffold works |

**Exit criteria:** `./setup.sh` runs on a fresh clone, creates `.env`, scaffolds the vault, and the vault has the right folder structure for every KB in `kb_definitions.md`.

---

## Phase 1 — Vault layer (Days 1–2)

The foundation all agents write through. Must be rock-solid before any agent code.

| Step | What | Notes |
|---|---|---|
| 1.1 | `vault/fs.py` — safe `read_md`, `write_md`, `append_md` under `VAULT_REPO_PATH` | Path escape validation is the critical property. Every read/write goes through here. |
| 1.2 | `vault/frontmatter.py` — parse/serialize YAML frontmatter | Used by agents to read/write structured metadata. Use `python-frontmatter` library. |
| 1.3 | `vault/paths.py` — slug generation, collision handling, date formatting | Deterministic: same input always produces same output. |
| 1.4 | `vault/git_sync.py` — `pull`, `commit`, `push` | Lifted from talkvault. Wrap `subprocess.run`. Keep sync. |
| 1.5 | Tests: `test_vault_fs.py`, `test_frontmatter.py`, `test_git_sync.py` | Use `tmp_path` fixtures. Mock subprocess for git tests. |

**Exit criteria:** all vault tests pass; `write_md` + `read_md` roundtrip works; slug collision is handled; `git_sync.commit` produces a real git commit in a temp repo.

---

## Phase 2 — Ingestion layer (Days 2–3)

Normalize user input into a canonical form. No agents yet.

| Step | What | Notes |
|---|---|---|
| 2.1 | `ingestion/transcriber.py` — Whisper via OpenAI SDK | Implement `Transcriber` Protocol. Single class: `WhisperTranscriber`. |
| 2.2 | `ingestion/link_fetcher.py` — `readability-lxml` | Implement `LinkFetcher` Protocol. Single class: `ReadabilityLinkFetcher`. Persist HTML to `raw/links/`. |
| 2.3 | `ingestion/normalize.py` — dispatch by `kind`, produce `NormalizedItem` | Wires transcriber + fetcher. This is the single entry point for L1. |
| 2.4 | Tests: `test_normalize.py` | Mock both protocols. Test all three kinds (text, voice, link). Test `LinkFetchError` paths. |

**Exit criteria:** `normalize(RawMessage(kind="link", url="..."))` returns a `NormalizedItem` with populated `text` and `source_meta`; `normalize(kind="voice")` returns transcript text; all tests pass with mocked I/O.

---

## Phase 3 — Agent tools (Days 3–4)

The bridge between agents and the vault. Build and test tools in isolation before wiring them into agents.

| Step | What | Notes |
|---|---|---|
| 3.1 | `agents/tools/interaction.py` — `ask_user` (LangGraph `interrupt()`) | Simplest tool; defines the HITL pattern for all others. |
| 3.2 | `agents/tools/kb_meta.py` — `list_kbs`, `read_recent_routing` (stratified), `read_routing_rules`, `commit_route` | `list_kbs` reads `_meta/kb_registry.md`. `read_recent_routing` implements stratified sampling logic. `commit_route` validates slug against registry. |
| 3.3 | `agents/tools/kb_pages.py` — `list_pages`, `read_page`, `write_page`, `append_to_page`, `search_pages`, `read_index`, `update_index` | All scoped to a KB path root at construction. Path escape validation delegates to `vault.fs`. |
| 3.4 | `agents/tools/kb_log.py` — `append_kb_log`, `finalize` | `finalize` is the KB agent's terminal tool. |
| 3.5 | Tests for all tools | Use a real temp vault (from bootstrap). Test path escape rejection. Test stratified sampling produces one entry per KB. |

**Exit criteria:** all tool tests pass; `commit_route` with an unknown slug returns an error; `read_page` with a path that escapes the KB root raises; stratified sampling returns at most one entry per KB in the first N-slots.

---

## Phase 4 — Agents (Days 4–5)

The two LangChain agents. Build router first (simpler), then KB ingestion.

| Step | What | Notes |
|---|---|---|
| 4.1 | `agents/prompts/router_system.md` | Write the routing prompt. Hardcode nothing KB-specific — it must work for any set of KBs. |
| 4.2 | `agents/router.py` — `create_agent` with router tools | Module-level singleton. Reads KB list from registry at startup. |
| 4.3 | `agents/prompts/kb_ingestion_system.md` | Template with `{{ kb_agent_md }}`, `{{ kb_index_md }}`, `{{ kb_recent_log }}`, `{{ items }}`, etc. |
| 4.4 | `agents/kb_ingestion.py` — `create_agent` per KB; per-KB cache dict; batched invocation | Cache keyed by `kb_slug`. Each cache entry holds a fresh `create_agent` result with tools scoped to that KB's folder. Breathing step gated by `breathing` flag from registry. |
| 4.5 | Tests: `test_router.py`, `test_kb_ingestion.py` | Mock the LLM (use `FakeListLLM` or similar). Test prompt assembly. Test that KB agent tools cannot escape their KB folder. |

**Exit criteria:** router test passes with mocked LLM producing a `commit_route` call; KB ingestion test creates a note file and entity page in the temp vault and calls `finalize`; breathing step is skipped when `breathing=false`.

---

## Phase 5 — Pipeline + Edge (Days 5–6)

Wire everything together. The only place all layers meet.

| Step | What | Notes |
|---|---|---|
| 5.1 | `edge/session.py` — in-memory session table | Mirrors talkvault's pattern. `SESSION_TIMEOUT = 600s`. |
| 5.2 | `pipeline.py` — `process(raw_message)` and `resume(thread_id, answer)` | Owns the per-KB `IngestQueue` with `asyncio` debounce timers. Returns `{"reply"}`, `{"interrupt_question"}`, or `{"error"}`. |
| 5.3 | `edge/handlers.py` — `handle_voice`, `handle_text` | Thin adapters. Voice: download → transcribe → send transcript preview → call `pipeline.process`. Text: detect link kind → call `pipeline.process` or `pipeline.resume`. |
| 5.4 | `edge/telegram_app.py` — `Application.builder()`, wire handlers, `run_polling` | Mirrors talkvault's `bot/main.py`. |
| 5.5 | `atlasmind/main.py` — entry point | Loads config, starts Application. |

**Exit criteria:** `python -m atlasmind.main` starts without errors; a hardcoded text message piped through the pipeline produces a `NormalizedItem`, routes it, queues it, and (after the debounce timer) ingests it to the vault and commits.

---

## Phase 6 — Integration & Deployment (Days 6–7)

End-to-end validation and production setup.

| Step | What | Notes |
|---|---|---|
| 6.1 | Manual end-to-end test — voice note | Send voice note via Telegram → transcript reply → "Routed to X" reply → wait debounce → "Ingested" reply → check vault commit. |
| 6.2 | Manual end-to-end test — link | Send URL → "Routed to X" reply → ingested note contains extracted text → HTML in `raw/links/`. |
| 6.3 | Manual end-to-end test — HITL | Send ambiguous item → agent asks a question → reply → agent continues → ingested. |
| 6.4 | Complete `setup.sh` — test on a fresh clone in a temp dir | Must work without any prior state. |
| 6.5 | Configure droplet — `systemd` service, deploy keys, vault remote | Do this once manually; document in README. |
| 6.6 | `.github/workflows/deploy.yml` — test + SSH deploy | Push a dummy commit to main; watch CI pass and bot restart on droplet. |
| 6.7 | `README.md` + `CLAUDE.md` | README: what this is, how to clone + run. CLAUDE.md: agent-facing guide for code navigation. |

**Exit criteria:** push to `main` → CI runs tests → deploys to droplet → bot restarts → send a Telegram message → it's in the vault within 6 minutes.

---

## What to prioritize if time is constrained

If you need to cut scope and ship something functional sooner:

1. **Skip CI/CD** (Phase 6.6) — deploy manually via SSH until the core loop is stable.
2. **Skip HITL** (session.py + interrupt pattern) — route everything at high confidence in v0; add HITL in a follow-up.
3. **Simplify batching** — start with immediate dispatch (no debounce queue); add the 5-minute window once single-item ingestion is reliable.

Do **not** skip:
- The vault layer (everything writes through it)
- The `kb_definitions.md` / registry separation (central invariant of the architecture)
- Per-KB tool scoping (the most important safety property)
