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
