# 08 — Deferred to v0+1

## Purpose

Map every PRD feature flagged "to be included after v0" (and some implied ones from `llm_wiki.md`) to the place in the v0 architecture where it will hook in. We don't build any of these now. We make sure v0 doesn't paint itself into a corner.

For each: **what it is**, **where it lands**, **what v0 must not break**.

---

## 1. Daily/weekly recall notifications

> "Send me a daily/weekly note to recall something randomly."

- **Lands in:** a new module `atlasmind/recall/`, scheduled by a cron-style runner inside the same Python process.
- **Trigger:** user-configurable schedule. Sends a Telegram message with a random or curated note.
- **Selection logic:** stratified random across KBs, with weight on age (older notes surface more). The Breathing system (post-v0) replaces this with smarter selection.
- **What v0 must not break:** Telegram outgoing path needs to support unprompted sends. v0 only sends in response to incoming updates. Add a `bot.send_message(chat_id, text)` helper now (used for nothing today) so the recall scheduler can use it later — **deferred**, but the `chat_id` is recorded in `_meta/general_log.md` per ingest, so post-v0 has the data.

## 2. Connection-suggestion replies on ingest

> "After I send something, show me how it's connected to stuff that I wrote before."

- **Lands in:** an enrichment step inside the KB ingestion agent's reply construction, between `finalize` and the Telegram reply.
- **What it does:** runs a dedicated query over the just-touched pages and adjacent ones, surfaces 1–3 top connections in the reply.
- **What v0 must not break:** the `finalize(summary_for_user)` tool already returns a free-form string. Post-v0 just enriches that string. No interface change.

## 3. "What I was doing 1 year ago"

> "Share with me what I was doing 1 year ago, how I started my month 1 year ago or X years ago."

- **Lands in:** the recall scheduler (item 1) plus a query path on demand (`/recall_year_ago` Telegram command).
- **Implementation:** read all `notes/` whose date frontmatter is exactly N years before today.
- **What v0 must not break:** the per-note frontmatter `date:` field is required across all KBs as of v0 ([§6](06_kb_contract.md)). Don't drop this.

## 4. `qmd` search tool

> "Qmd search tool" — local hybrid BM25/vector search over markdown.

- **Lands in:** new tool `atlasmind/agents/tools/kb_search.py` that shells out to `qmd` per [`llm_wiki.md`](../base_docs/llm_wiki.md).
- **Replaces:** the v0 `search_pages` tool (substring grep) for KB ingestion agents.
- **What v0 must not break:** `search_pages` must be a single tool with a single signature `search(query: str) -> list[matches]`. Swapping its implementation is a one-line change. Don't bake substring-specific quirks into the agent's prompts.

## 5. Firecrawl / headless browser link ingestion

> "Obsidian web clipper to transform html to markdown or Firecrawl alternative to scrape websites, avoiding paywalls."

v0 uses `readability-lxml` for link ingestion, which works well for standard HTML pages but fails on JS-heavy pages and paywalled content. Firecrawl is the preferred v0+1 upgrade.

- **Lands in:** swap `atlasmind/ingestion/link_fetcher.py` with a Firecrawl implementation. The `LinkFetcher` Protocol (`fetch(url) -> (text, meta)`) is already defined in v0 ([`04_ingestion_layer.md`](04_ingestion_layer.md)) for exactly this swap — no interface change.
- **Firecrawl advantages:** headless rendering (bypasses JS-only pages), markdown output (no need for readability post-processing), paywall bypass via rendered DOM, structured metadata (title, author, date) in the API response.
- **Implementation:** `atlasmind/ingestion/link_fetcher.py` gets a `FirecrawlLinkFetcher` class. `FIRECRAWL_API_KEY` added to `.env.example`. The v0 `ReadabilityLinkFetcher` stays as a fallback configurable via `LINK_FETCHER=readability|firecrawl` env var.
- **What v0 must not break:** `LinkFetcher.fetch(url) -> (text, meta)` Protocol stays stable. The `meta` dict shape (keys: `url`, `title`, `fetched_at`, `html_path`) may be extended but not narrowed.

## 6. Image asset auto-download

> "Download images locally configuration with hotkey to keep assets/images in case the URL which host them breaks."

- **Lands in:** post-fetch step inside `link_fetcher` and a separate post-ingest step for the agent.
- **Storage:** under `<vault>/raw/assets/`.
- **What v0 must not break:** `raw/` is reserved for original sources; v0 already creates this folder.

## 7. Dataview query templates

> "Dataview to query stuff."

- **Lands in:** authored `index.md` or per-KB `agent.md` snippets that include Dataview queries.
- **What v0 must not break:** every note has frontmatter with at minimum `kb`, `date`, `created_at`, `source_kind`. Per-KB schemas (people, books, etc.) are listed in `agent.md`. Dataview just reads what's already there.

## 8. The full Breathing system

> "Repetition / Contradictions / Long-term connections / Patterns / Evolution over time / Entity depth / Reflection triggers / no constant suggestions—only trigger when there is clear signal."

- **Lands in:** new agent `atlasmind/agents/breathing.py`. Triggers:
  - End of ingestion (already a thin v0 placeholder).
  - On-demand via Telegram command.
  - Scheduled (daily/weekly).
- **Scope:** can read across multiple KBs (this is the "grey area" the PRD names — it's the *one* legitimate cross-KB reader).
- **Outputs:** writes to a per-KB `breathing/` folder and/or sends a Telegram nudge.
- **What v0 must not break:** the v0 KB ingestion agent's last step is a thin reflection that touches *only* the new note ([§5 of the agent layer doc](05_agent_layer.md)). Post-v0 lifts that into a separate, more capable Breathing agent.

## 9. Lint workflows

> "Karpathy knowledge base idea" / `llm_wiki.md`'s lint operation.

- **Lands in:** new agent `atlasmind/agents/lint.py`.
- **What it does:** scans for orphan pages, missing cross-references, contradictions, stale claims; produces a report (a markdown file in the KB) and Telegram summary.
- **What v0 must not break:** `index.md` and `log.md` formats are stable as of v0. Lint reads them.

## 10. Multi-user / per-user vaults

- **Lands in:** `pipeline.py` and `edge.session`. Today: `thread_id = str(user_id)`, `VAULT_REPO_PATH` is global. Post-v0: vault path resolved per-user; checkpointer keyed by `(user, run)`.
- **What v0 must not break:** vault path is read from a single env var today, but the `pipeline.process(...)` signature already takes the `RawMessage` (which carries `telegram_user_id`), so the lookup point exists.

## 11. Persistent checkpointer

- **Lands in:** swap `InMemorySaver` for `AsyncPostgresSaver` (or SQLite for local).
- **What v0 must not break:** the agent factory takes a checkpointer as an argument. Easy swap.

## 12. Production deployment

talkvault has a Docker setup, droplet provisioning scripts, CD workflow. We can copy directly when needed.

- **Lands in:** `deploy/`, `infrastructure/`, `Dockerfile`, `.github/workflows/`.
- **What v0 must not break:** `python -m atlasmind.main` must be a single, env-driven entry point. Already the plan.

---

## 13. Quick map — feature → file in v0

| Future feature | Hook in v0 |
|---|---|
| Recall notifications | `edge/telegram_app.py` + new `recall/` |
| Connection-suggestion on ingest | `agents/kb_ingestion.py` reply |
| "1 year ago" | frontmatter `date:` already present |
| `qmd` search | swap `agents/tools/kb_pages.py:search_pages` impl |
| Firecrawl link fetching | swap `ingestion/link_fetcher.py` impl (`FirecrawlLinkFetcher`) |
| Image asset download | extend `link_fetcher` + agent post-step |
| Dataview queries | already supported via existing frontmatter |
| Full Breathing system | new `agents/breathing.py` |
| Lint | new `agents/lint.py` |
| Multi-user | `pipeline.py`, vault path resolution |
| Persistent checkpointer | swap arg in agent factory |
| Production deploy | copy from talkvault |

If a v0 design change makes any of these meaningfully harder, push back during the build.
