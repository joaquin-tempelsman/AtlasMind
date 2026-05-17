# Feature Log

Chronological record of every feature merged into AtlasMind. One entry per merged PR. Entries are append-only — corrections go in a new entry that says "amends PR #X."

The one-line index lives in [`CLAUDE.md` §5](../CLAUDE.md#5-feature-index). Update both in the same PR.

Entry template:

```markdown
## PR #<num> — <short title>
**Date:** YYYY-MM-DD
**Branch:** feat/<name>
**Layer(s):** <e.g. ingestion, agents.router>
**Spec:** [link to dev_specs section]

### What changed
- 2–5 bullets describing the feature.

### Contracts asserted
- Test file(s) + contract section(s) they cover.

### Within-layer tests added
- File(s) + what they cover.

### Notes
- Anything future-you should remember (gotchas, deferred TODOs, follow-up PRs).
```

---

<!-- entries go below, newest at top -->

## PR #8 — Phase 8: Entity alias registry per KB
**Date:** 2026-05-17
**Branch:** feat/phase-8-entity-aliasing
**Layer(s):** agents.kb_ingestion, agents.tools, bootstrap, vault

### What changed
- `bootstrap.py` — `_scaffold_kb()` creates `entities.md` per KB with header template
- `agents/tools/kb_entities.py` (new) — `make_kb_entity_tools()` factory with `register_entity` tool; append-or-merge so canonical lines are never duplicated
- `agents/kb_ingestion.py` — entity tools added to tool set; `entities.md` injected as "Entity Registry" into `_build_batch_message`; `_ENTITY_RESOLUTION_ADDON` prompt section instructs alias resolution and auto-registration
- `dev_specs/06_kb_contract.md` — `entities.md` added to KB folder listing (§1) and new §11 documents format and agent contract

### Contracts asserted
- `tests/contract/test_kb_ingestion_tools.py` — register_entity appends, merges aliases, entities.md scaffolded per KB

### Within-layer tests added
- `tests/unit/test_kb_entities.py` — 5 tests: append, no-alias, merge, missing-file graceful, multi-entity
- `tests/unit/test_kb_ingestion.py` — entity registry injected in batch message; absent when entities.md missing

### Notes
- Users edit entities.md in Obsidian/git directly; no Telegram command needed for v0
- Agent auto-registers newly created entity pages, growing the registry organically

## PR #7 — Phase 7: KB-level URL metadata + reply-based URL linking
**Date:** 2026-05-17
**Branch:** feat/phase-7-rebased
**Layer(s):** edge, ingestion, agents.kb_ingestion, agents.tools, shared.types
**Spec:** [dev_specs/06_kb_contract.md §2](../dev_specs/06_kb_contract.md), [dev_specs/01_architecture.md §3](../dev_specs/01_architecture.md)

### What changed
- `shared/types.py` — added `linked_url: str | None` to `RawMessage` (L0→L1 contract)
- `edge/url_registry.py` (new) — per-user in-memory registry (24h TTL) mapping Telegram message_ids to URLs; separate from session, survives session expiry
- `edge/handlers.py` — URL messages register both user msg_id and bot reply msg_id; voice/text handlers detect `reply_to_message` and attach `linked_url` to `RawMessage`
- `ingestion/normalize.py` — link kind: `NormalizedItem.text` is now short repr `[Link] {title}\nURL: {url}`; full article stored in `source_meta["raw_article_text"]`; voice/text: `linked_url` propagated into `source_meta`
- `agents/tools/url_metadata.py` (new) — `make_extract_url_metadata_tool(link_fetcher)`: fetches URL, calls `claude-haiku-4-5-20251001` to extract KB-configured metadata fields (e.g. media_source, article_writer)
- `agents/kb_ingestion.py` — parses `url_metadata_fields` + `include_article_content` from registry; injects URL metadata extraction instructions into system prompt; adds `extract_url_metadata` tool to agent toolset when fields configured; `_build_batch_message` conditionally includes full article text and annotates items with `linked_url`
- `bootstrap.py` — `_generate_registry` writes `URL metadata fields` and `Include article content` to `_meta/kb_registry.md`
- `dev_specs/06_kb_contract.md` — added `url_metadata_fields` and `include_article_content` to KB definition schema
- `dev_specs/01_architecture.md` — added `linked_url` to `RawMessage` shape; documented URL reply registry at L0
- `requirements.txt` — added `anthropic>=0.40,<1.0`

### Contracts asserted
- `tests/contract/test_data_shapes.py` — `linked_url` field defaults None, set on voice, set on text
- `tests/contract/test_kb_ingestion_tools.py` — `extract_url_metadata` returns dict with requested fields; uses `claude-haiku-4-5-20251001` model

### Within-layer tests added
- `tests/unit/test_url_registry.py` — register/lookup, multi-user isolation, TTL expiry, clear_user/clear_all
- `tests/unit/test_normalize.py` — short repr for link items, `raw_article_text` in meta, `linked_url` propagation for voice and text, no `linked_url` key when absent

### Notes
- `kb_definitions.md` is gitignored (personal config) — add `url_metadata_fields: [media_source, article_writer]` and `include_article_content: false` to local econ-politics entry to activate extraction
- The debounce timer naturally batches a URL + N voice replies into one ingest run — no special grouping logic needed
- `extract_url_metadata` re-fetches the URL (separate from the normalization fetch); acceptable trade-off for simplicity; could cache in v0+1

## PR #5 — Phase 6: CI/CD, README, setup.sh
**Date:** 2026-05-04
**Branch:** feat/phase-6-ci-readme
**Layer(s):** ci, docs
**Spec:** [dev_specs/10_development_plan.md Phase 6](../dev_specs/10_development_plan.md)

### What changed
- `.github/workflows/ci.yml` — ruff lint + pytest on every PR and push to main; `OPENAI_API_KEY=dummy-key-for-tests` for CI
- `.github/workflows/deploy.yml` — on push to main: runs tests then SSHs to droplet; expects `DROPLET_HOST`, `DROPLET_USER`, `DROPLET_SSH_KEY` secrets
- `README.md` — project overview, setup instructions, systemd deployment guide, project layout, dev workflow
- `setup.sh` — creates `.venv/` if absent; uses `.venv/bin/python` throughout; improved prompts

### Contracts asserted
- None — infra/docs phase. All 154 existing tests pass unchanged.

### Within-layer tests added
- None.

### Notes
- Manual end-to-end tests (6.1–6.3 in the plan) require a live Telegram bot + OpenAI key — run manually before first production deploy
- Add `DROPLET_HOST`, `DROPLET_USER`, `DROPLET_SSH_KEY` to GitHub repo secrets before the deploy workflow will fire

## PR #4 — Phase 5: pipeline + edge
**Date:** 2026-05-04
**Branch:** feat/phase-5-pipeline-edge
**Layer(s):** pipeline, edge.session, edge.handlers, edge.telegram_app
**Spec:** [dev_specs/10_development_plan.md Phase 5](../dev_specs/10_development_plan.md)

### What changed
- `edge/session.py` — in-memory session table; `SESSION_TIMEOUT = 600s`; `get/set_active/touch/drop/clear_all`
- `pipeline.py` — `Pipeline` class with `process()` + `resume()`; per-KB `IngestQueue` with asyncio debounce timers; `reply_fn` callback for timer-fired Telegram replies
- `edge/handlers.py` — `handle_voice` (download → transcribe → pipeline.process), `handle_text` (HITL resume or fresh process); auth guard on `TELEGRAM_ALLOWED_USER_IDS`; lazy `WhisperTranscriber` init (avoids OPENAI_API_KEY requirement at import time)
- `edge/telegram_app.py` — `build_app(token)` wires voice + text `MessageHandler`s; attaches pipeline to `bot_data`
- `atlasmind/main.py` — entry point; `run_polling(drop_pending_updates=True)`

### Contracts asserted
- `tests/contract/test_pipeline.py` — process returns `{"reply"}` shape; `{"interrupt_question"}` shape; resume after route interrupt; IngestQueue fires after delay; IngestQueue batches two items within window

### Within-layer tests added
- `tests/unit/test_session.py` — absent→None; set/get roundtrip; drop; timeout; touch; update expecting
- `tests/unit/test_pipeline.py` — reply shape; interrupt_question; normalize error; resume no session; resume after route interrupt; timer fires; timer reset on second message; `_is_url` detection

### Notes
- `WhisperTranscriber` instantiates `OpenAI()` at construction; lazy init via `_get_transcriber()` is required to prevent OpenAI API key errors when importing handlers in tests
- Per-KB ingest thread_id is `"{user_id}:{kb_slug}"` to avoid collision across KBs
- `reply_fn` is passed into `Pipeline` at construction so the bot can reach users from timer callbacks without holding a reference to the `Update` object

## PR #3 — Phase 4: router and KB ingestion agents
**Date:** 2026-05-04
**Branch:** feat/phase-4-agents
**Layer(s):** agents.router, agents.kb_ingestion
**Spec:** [dev_specs/05_agent_layer.md §2–3](../dev_specs/05_agent_layer.md)

### What changed
- `agents/prompts/router_system.md` — static routing system prompt
- `agents/prompts/kb_ingestion_system.md` — template with `{kb_agent_md}` + `{standard_workflow}` substituted at construction
- `agents/router.py` — singleton per vault_root; `route()` + `resume_route()` for HITL
- `agents/kb_ingestion.py` — singleton per `(vault_root, kb_slug)`; `ingest()` + `resume_ingest()`; breathing controlled by registry flag; dynamic context (index, log tail, items) in user message

### Contracts asserted
- `tests/contract/test_agents.py` — router log write; KB note creation + finalize; path escape; breathing absent by default; interrupt→resume for both agents

### Within-layer tests added
- `tests/unit/test_router.py` — happy path, log write, interrupt, resume, cache singleton
- `tests/unit/test_kb_ingestion.py` — note creation, finalize, interrupt, empty batch, breathing flag, cache isolation, multi-tool

### Notes
- `langchain.agents.create_agent` (not deprecated `langgraph.prebuilt.create_react_agent`) — use `system_prompt=` not `prompt=`
- `FakeToolCallingModel` pattern: subclass `FakeMessagesListChatModel`, override `bind_tools` to return `self`; responses are consumed in order by the agent loop
- Tool messages from dict-returning tools are JSON-serialized in the ToolMessage content

## PR #2 — Phase 3: agent tools
**Date:** 2026-05-04
**Branch:** feat/phase-3-agent-tools
**Layer(s):** agents.tools
**Spec:** [dev_specs/05_agent_layer.md §2–3](../dev_specs/05_agent_layer.md)

### What changed
- `agents/tools/interaction.py` — `ask_user` wraps LangGraph `interrupt()` for HITL
- `agents/tools/kb_meta.py` — router tools (`list_kbs`, `read_recent_routing` with stratified sampling, `read_routing_rules`, `commit_route`) bound to vault_root via factory
- `agents/tools/kb_pages.py` — KB-scoped page tools (`list_pages`, `read_page`, `write_page`, `append_to_page`, `search_pages`, `read_index`, `update_index`); path escape validated against KB root
- `agents/tools/kb_log.py` — `append_kb_log`, `finalize` terminal tool
- Bug fix: `_FIELD_RE` in `frontmatter.py` corrected (colon was inside bold markers, not outside)

### Contracts asserted
- `tests/contract/test_router_tools.py` — list_kbs active/inactive filtering; commit_route rejects unknown slug; stratified sampling; n-cap
- `tests/contract/test_kb_ingestion_tools.py` — path escape raises PathEscapeError; write/read roundtrip; append; search; update_index; append_kb_log; finalize shape

### Within-layer tests added
- `tests/unit/test_kb_meta.py` — registry parsing, active field, stratified sample edge cases, commit_route source/preview
- `tests/unit/test_kb_pages.py` — _update_index_text, write/list/read, missing file, escape, search
- `tests/unit/test_kb_log.py` — append content, multiple appends, finalize dict

### Notes
- `_FIELD_RE` bug existed in frontmatter.py since Phase 1/2 but was untested; field extraction in `parse_routing_log_entries` was silently returning only timestamp/kb_slug/confidence (no source/preview/rationale/file_path fields). Fixed here.
- Tools are factory-bound (not class-based) — each call to `make_kb_*_tools(vault_root)` returns a new list of `@tool`-decorated functions closing over vault_root. This is intentional and tested.

## PR #1 — Phases 0–2: scaffolding, vault layer, ingestion layer
**Date:** 2026-05-04
**Branch:** feat/phases-0-2
**Layer(s):** scaffold, vault, ingestion
**Spec:** [dev_specs/10_development_plan.md Phases 0–2](../dev_specs/10_development_plan.md)

### What changed
- Project scaffolding: pyproject.toml, requirements.txt, .env.example, setup.sh
- Shared types: RawMessage, NormalizedItem, RoutedItem, IngestionResult
- config.py, bootstrap.py (vault scaffolding from kb_definitions.md)
- vault/fs.py (path-escape-safe read/write), vault/frontmatter.py, vault/paths.py, vault/git_sync.py
- ingestion/transcriber.py (Whisper), ingestion/link_fetcher.py (readability-lxml), ingestion/normalize.py

### Contracts asserted
- tests/contract/test_data_shapes.py — all four layer-boundary types
- tests/contract/test_kb_filesystem.py — bootstrap scaffold structure

### Within-layer tests added
- tests/unit/test_vault_fs.py, test_frontmatter.py, test_paths.py, test_git_sync.py, test_normalize.py

### Notes
- bootstrap YAML parser uses column-0 fence matching (`line == "```yaml"`) to avoid matching nested fences inside agent_md literals in kb_definitions.md
