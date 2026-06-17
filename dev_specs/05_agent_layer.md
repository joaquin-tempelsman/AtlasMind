# 05 — Agent Layer (L2 + L3)

## Purpose

Two LangChain 1.0 agents, each with a tightly-scoped context. The router decides *where* an item belongs; the KB ingestion agent decides *how* it integrates into that KB. A thin breathing pass exists in code but is **disabled by default** in v0.

This is where most of the v0 design risk lives, so this doc is the longest. Read it twice.

---

## 1. LangChain 1.0 conventions (the framework choices)

We use LangChain 1.0's `create_agent` primitive. Confirmed via Context7 docs and validated in talkvault. The constructor we'll use:

```
from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware, HumanInTheLoopMiddleware
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

agent = create_agent(
    model=ChatOpenAI(model="gpt-4o", temperature=0),
    tools=[...],
    system_prompt="...",
    middleware=[
        SummarizationMiddleware(model="gpt-4o-mini",
                                trigger=("tokens", 6000),
                                keep=("messages", 20)),
    ],
    checkpointer=InMemorySaver(),
)
```

Why these pieces:

- **`create_agent`** is the 1.0 entry point. It returns a graph that you call with `agent.ainvoke({"messages": [...]}, config={"configurable": {"thread_id": "..."}}, version="v2")`.
- **`InMemorySaver` checkpointer** — required for HITL because `interrupt()` needs persistent graph state between turns. Talkvault uses it; we keep it. (Persistent checkpointer like `AsyncPostgresSaver` is post-v0.)
- **`SummarizationMiddleware`** — auto-summarizes message history when context gets long. We add it preemptively because the KB ingestion agent does multi-turn tool calls that can blow up message count (read 10 pages, edit 5, re-read for review). Configured to summarize when tokens ≥ 6000, keep last 20 messages.
- **`HumanInTheLoopMiddleware`** — *not* used in v0. Talkvault uses an explicit `ask_user` tool that calls `interrupt()`, which is more granular and matches our HITL needs (we want to ask custom questions, not approve/reject specific tool calls). We follow talkvault's pattern.
- **`thread_id` = `str(telegram_user_id)`** — so resumes round-trip per user. Single-tenant in v0 means thread collisions are impossible; multi-tenant later will need a tuple `(user, run_id)`.
- **`version="v2"`** — required for the GraphOutput shape with `.value` and `.interrupts` (talkvault uses this; v1 returns a different structure).

### Single agent instance? Or per-call?

Talkvault uses a module-level singleton (`_agent` cached in `bot/brain.py`). We do the same for the **router** because its tools and prompt are static.

For the **KB ingestion agent** the tools differ per-KB (each KB has its own scoped read/write tools). Two viable options:

- **Option A: build a fresh agent per ingest** — slower (~200ms graph construction) but cleanest scope.
- **Option B: cache one agent per KB slug** — fast, but means KB tool factories must be deterministic and side-effect-free at construction.

**Decision:** Option B. Cache `dict[kb_slug, AgentExecutor]` in a module-level registry. Keep the cache populated lazily on first ingest per KB. This matches talkvault's spirit (one cached agent) while honoring per-KB isolation.

---

## 2. The Router agent (L2)

### What it sees

The router's system prompt is small and stable:

- A list of active KBs with their one-paragraph descriptions (read from `_meta/kb_registry.md` — only KBs with `active: true`).
- A **stratified sample** of up to N=20 entries from `_meta/general_log.md` — gives the router calibrated examples of how each KB is used (see §Stratified sampling below).
- Optional human-written hints in `_meta/routing_rules.md` (e.g. "anything about my dad → personal-diary, not reflections, even if reflective in tone").

### Stratified sampling of `general_log.md`

The router does not simply read the last N entries, because a heavily-used KB would crowd out examples from less-active KBs. Instead:

1. Collect the **most recent entry per active KB slug** (one per vault). This guarantees every KB has at least one routing example visible to the router.
2. Fill remaining slots (up to N=20 total) with additional entries in **reverse-chronological order**, skipping already-selected entries.

This logic lives in the `read_recent_routing(n=20)` tool. The router calls it by name; it returns a list of up to 20 log entries shaped the same way regardless of the sampling strategy. The router prompt and the agent code do not change if the sampling strategy is tuned.

### What it gets as input

Just the `NormalizedItem.text` plus a tiny envelope:
```
{
  "text": "...",
  "source_kind": "voice" | "text" | "link",
  "source_meta": {...},
  "received_at": "2026-05-02T14:25:03Z"
}
```

### Tools available to the router

Minimal — the router should not be a swiss army knife.

| Tool | Purpose |
|---|---|
| `list_kbs()` | Returns `[{slug, name, description}, ...]` for active KBs from `_meta/kb_registry.md`. The router always calls this once at start (idempotent). |
| `read_recent_routing(n=20)` | Returns up to N entries from `_meta/general_log.md` using stratified sampling (one per vault, then reverse-chron fill). |
| `read_routing_rules()` | Returns the contents of `_meta/routing_rules.md` (human-editable hints). |
| `commit_route(kb_slug, rationale, confidence)` | The terminal action. Validates `kb_slug` against the active registry, appends an entry to `_meta/general_log.md`, returns `{"ok": True, "kb_slug": ..., "log_entry": ...}`. The agent's run ends after this tool returns. |
| `ask_user(question)` | LangGraph `interrupt()` for HITL — only used when the router has low confidence and wants to confirm. |

### Output (to the pipeline)

The router does not emit a Python object directly. It emits a structured tool call (`commit_route`) whose effect *is* the routing decision. The pipeline reads the latest `general_log.md` entry to construct the `RoutedItem`. This keeps the agent's contract grounded in observable file state — easier to debug than parsing a free-form last message.

### Routing prompt sketch

`atlasmind/agents/prompts/router_system.md` — committed file, edited like code:

```
You are AtlasMind's routing agent. You decide which knowledge base a new item belongs to.

You have access to N knowledge bases. ALWAYS start by calling list_kbs().
Then call read_recent_routing(20) to see how recent items were routed and what
worked. Optionally call read_routing_rules() if any rule might apply.

Pick the single best KB. Items belong to exactly one KB; isolation is enforced.

Confidence levels:
- "high": clear topical match.
- "medium": plausible but ambiguous; route anyway and note the ambiguity.
- "low": you genuinely cannot decide between 2+ KBs OR the item doesn't fit any.
   In this case ONLY, call ask_user with a one-line question listing your top
   candidates. Do not over-use this — most items are not low-confidence.

Always finish by calling commit_route(kb_slug, rationale, confidence).
The rationale is one short sentence in the user's voice that will appear in
general_log.md.

Do not write notes. Do not modify any KB. Your only side effect is one
commit_route call.
```

---

## 3. The KB Ingestion agent (L3)

### Invocation model — batched items

The KB ingestion agent is invoked **once per batch**, not once per item. When the per-KB ingest queue fires (see [`04_ingestion_layer.md` §Per-KB Ingest Queue](04_ingestion_layer.md)), the pipeline passes all queued `RoutedItem`s for that KB to the agent in a single invocation. The agent ingests them sequentially within one agent run, reusing any entity pages it created earlier in the same batch.

The system prompt injection covers the full batch:
```
{{ kb_agent_md }}           ← KB schema
{{ kb_index_md }}           ← current KB index (full picture of what exists)
{{ kb_recent_log }}         ← tail of KB log.md (last 30 lines)
{{ standard_workflow }}     ← the 7-step list (repeated per item in the batch)
{{ tool_summary }}          ← auto-generated from available tools
{{ items }}                 ← list of NormalizedItem texts in this batch
```

### What it sees

Scoped to a single KB. The agent is built per-KB with:

- The KB's `agent.md` injected verbatim into the system prompt (this is the user's per-KB schema — see [`06_kb_contract.md`](06_kb_contract.md)).
- The KB's `index.md` contents (passed in as the *first* user message after the system prompt — gives the agent a full picture of what already exists).
- The last 30 entries of the KB's `log.md` for recent context.
- All `NormalizedItem` texts in the current batch.

### What it does

Following the PRD's "agent layer 2" responsibilities, for each item in the batch:

1. **Reads the new item.**
2. **Searches existing pages** (people, concepts, books, etc.) to find what's affected.
3. **Creates a new note file** under `<kb>/notes/YYYY-MM-DD-<slug>.md` with frontmatter (see [`06_kb_contract.md`](06_kb_contract.md)).
4. **Updates entity pages** — if the note mentions Mateo and `personal-diary/people/mateo.md` exists, append a one-liner with a wiki-link back to the new note. If Mateo doesn't have a page yet, create one *only if the agent.md schema for this KB says so* (most do for `people/`).
5. **Updates the KB's `index.md`** — adds a one-line entry for the new note under the right category.
6. **Appends to the KB's `log.md`** with format `## [YYYY-MM-DD] ingest | <slug>` followed by a 1-3 line summary.
7. **Returns a one-line summary per item** for the Telegram reply.

After all items in the batch are processed, the agent calls `finalize(summary_for_user)` once.

### The breathing step — disabled by default

A thin per-ingest breathing step exists in the agent's workflow but is **off by default**. It is controlled by the per-KB `breathing` flag in `kb_definitions.md` (default `false`).

When `breathing: true` for a KB, after filing the note the agent runs one additional pass:

> "Look at the note you just filed and the entity/concept pages you touched. If you notice a contradiction with prior content, OR a strong connection to another page (within this KB only), append a `> [!note] Related` callout to the new note pointing at it. If nothing notable, do nothing. Do **not** restructure or rewrite anything."

This is intentionally tiny. Enable it per KB once the vault has enough content for connections to be meaningful (rough threshold: ~30+ notes in that KB). Light breathing is also disabled by default for the same reason.

When to enable: edit `kb_definitions.md` and set `breathing: true` for that KB. No code change needed; the agent checks the flag at runtime.

### Output language — opt-in per KB

A per-KB `language` setting (natural-language name, e.g. `Spanish`) controls the language of
everything the agent **writes into the KB**. When set, a language addon is appended to the
system prompt instructing the agent to write all wiki content — note titles and bodies,
`index.md` lines, entity-page prose, and any callouts/summaries — in that language,
translating the input as it files it. When unset (default), no addon is added and the note
is written in the input's own language (prior behavior).

Two boundaries matter:

- **Proper nouns and `[[wiki-link]]` targets are never translated** — people, place, and
  work titles stay as written so links and entity pages remain consistent.
- **The `finalize(summary_for_user)` text is NOT wiki content** — it is the Telegram reply
  to the user and is written in the language of the user's input, not the KB language.

The verbatim original input is always preserved in `raw/captures/` (see
[`06_kb_contract.md` §6](06_kb_contract.md)), so translating the note never loses the
source. Like breathing, this is a runtime flag — edit `kb_definitions.md`, no code change.

### Tools available to the KB ingestion agent

All tools are **scoped to the KB folder** at construction time. The agent literally cannot read or write outside its KB (paths are validated). This is the most important property of the layer.

| Tool | Purpose |
|---|---|
| `list_pages(folder=None)` | Lists markdown files in the KB, optionally filtered to a subfolder. |
| `read_page(rel_path)` | Reads a page within the KB. Errors if path escapes. |
| `write_page(rel_path, content, frontmatter)` | Creates or overwrites a page. Frontmatter merged with sane defaults. |
| `append_to_page(rel_path, content)` | Appends to an existing page. |
| `search_pages(query)` | Substring + case-insensitive search across the KB's markdown files. (No vectors in v0.) |
| `read_index()` | Returns the KB's `index.md`. Sugar on `read_page("index.md")`. |
| `update_index(category, line)` | Appends a one-line entry under the named category in `index.md`, creating the category section if needed. |
| `append_kb_log(entry)` | Appends a `## [date] kind | title` entry to `log.md`. |
| `ask_user(question)` | Same `interrupt()` tool as the router. Use for ambiguity (`"This note mentions 'Sofía' — is this Sofía P. (work) or Sofía R. (family)?"`). |
| `finalize(summary_for_user)` | Terminal tool. Signals "I am done with all items in this batch" and provides the Telegram reply text. The pipeline will then commit the working tree to git. |

### What the agent must NOT have

- Any tool that writes to `_meta/`. The router owns the meta layer; the KB agent is sandboxed.
- Any tool that runs git commands. Git is the pipeline's job, executed once at the end of a successful run.
- Any tool that reads other KBs' folders. Cross-KB awareness is post-v0 (see PRD §Isolation: "grey area").

### KB ingestion prompt — per-KB substitution

`atlasmind/agents/prompts/kb_ingestion_system.md` is a template. At runtime, for `kb_slug = "personal-diary"`:

```
{{ kb_agent_md }}        ← contents of personal-diary/agent.md verbatim
{{ kb_index_md }}        ← contents of personal-diary/index.md
{{ kb_recent_log }}       ← tail of personal-diary/log.md (last 30 lines)
{{ standard_workflow }}   ← shared text (the 7-step list above)
{{ tool_summary }}        ← auto-generated from the tools you've been given
{{ items }}               ← the batch of NormalizedItem texts to ingest
```

---

## 3.5 — The Amendment classifier (pre-commit batch edits)

Items sit in the per-KB ingest queue for the debounce window before they reach the KB
ingestion agent (see [`04_ingestion_layer.md`](04_ingestion_layer.md) and
[`03_telegram_layer.md`](03_telegram_layer.md)). During that window the user can **correct** a
message already queued — fix a typo'd name, reword a garbled dictation — *before* anything is
written or committed. A small, cheap classifier decides whether each new message is a brand-new
item or a correction of one already pending.

**Module:** `atlasmind/agents/amendment.py`. Not a `create_agent` graph — a single
claude-haiku call, mirroring `extract_url_metadata` in
[`tools/url_metadata.py`](../atlasmind/agents/tools/url_metadata.py). It is stateless and has no
tools.

**Contract:**

```
async def classify_amendment(pending: list[str], new_text: str) -> dict
```

- **Input:** `pending` is the ordered list of the texts of the items currently queued for the
  user (shown 1-indexed to the user); `new_text` is the incoming message.
- **Output** is exactly one of:
  - `{"kind": "new"}` — the message is a new item; the pipeline routes and enqueues it normally.
  - `{"kind": "modification", "target_index": int, "new_text": str, "rationale": str}` — the
    message corrects pending item `target_index` (0-based into `pending`); `new_text` is the
    **full corrected text** that should replace the queued item's text; `rationale` is one line.
- On any ambiguity, an empty `pending`, or a parse failure the classifier returns
  `{"kind": "new"}` (fail-safe: never silently rewrite the wrong item).

**How the pipeline uses it.** When a message arrives and the user has a non-empty pending batch,
the pipeline calls `classify_amendment` *before* routing:

- `new` → normal route + enqueue (unchanged behavior).
- `modification` → the pipeline does **not** route or enqueue. It proposes the change back to the
  user via the standard interrupt path
  (`{"interrupt_question": "Change item N: '<old>' → '<new>'? (yes/no)"}`) and remembers the
  proposal. On an affirmative reply the queued item's text is **rewritten in place**; on a
  negative reply the batch is left untouched. Either way the debounce timer is re-armed, and the
  next message re-enters the classifier — so a second correction is just another message.

The original verbatim input remains in `raw/captures/` (persisted at normalize time); rewriting
the queued text only changes what the KB ingestion agent will see at flush, not the archive.

---

## 4. HITL — the interrupt pattern, one more time

talkvault's `ask_user` tool is exactly this:

```
@tool
def ask_user(question: str) -> str:
    return interrupt({"question": question})
```

- Agent calls `ask_user("Is X correct?")`.
- LangGraph saves graph state in the checkpointer (keyed by `thread_id`).
- `agent.ainvoke(...)` returns a `GraphOutput` whose `.interrupts` is non-empty.
- Pipeline detects the interrupt, returns `{"interrupt_question": "..."}` to the edge.
- Edge sends the question via Telegram, marks the session as `expecting="answer"`.
- User replies. Edge calls `pipeline.resume(thread_id=..., answer=text)`.
- Pipeline calls `agent.ainvoke(Command(resume=text), config=..., version="v2")`. The graph picks up where it left off; `ask_user` returns the user's text.

This works identically for the router and the KB ingestion agent because they share the tool. The pipeline doesn't need to know which agent paused — `thread_id` selects the right graph.

**Constraint:** only one interrupt at a time per `thread_id`. If the agent calls `ask_user` twice in parallel branches, behavior is undefined. Don't.

**Batching + HITL:** if an interrupt fires during a batch run, the batch is paused. New items arriving for the same KB during the pause are queued normally; their debounce timer runs but will not fire a new agent instantiation until the current batch's interrupt is resolved. (The pipeline checks: if an agent for that KB has an active interrupt, skip the timer and wait.)

---

## 5. Context management — the long-running concern

This system is intended to run for years. A few specific concerns and how v0 handles them:

| Concern | Mitigation |
|---|---|
| `general_log.md` grows huge | The router reads at most N=20 entries using **stratified sampling** (one per active KB first, then reverse-chron fill). The file itself can grow indefinitely. |
| KB `log.md` grows huge | Agent reads the last 30 lines. |
| KB `index.md` grows huge | Read in full but bounded by user behavior — at ~100 sources/KB this stays under 1k lines. Past that, post-v0 we'd add a per-category index. |
| Per-ingest agent message history blows up | `SummarizationMiddleware` triggers at 6000 tokens. |
| Checkpointer accumulates dead threads | `InMemorySaver` resets on process restart. Acceptable for v0 single-process polling deployment. Post-v0: persistent checkpointer + TTL eviction. |
| Prompt drift (agent.md gets edited badly) | All `agent.md` files live in the **vault repo**, so the user gets git history of their own prompt edits. They can revert from Obsidian's git pane or VSCode. |

---

## 6. Failure modes

| Failure | Where | Behavior |
|---|---|---|
| Router's `commit_route` called with unknown `kb_slug` | router tool | tool returns error to agent; agent retries; if agent insists, `ask_user` |
| Router routes to an inactive KB | router tool | `list_kbs()` returns only active KBs; inactive KBs are never in the list |
| KB agent tries to write outside its folder | tool path validator | tool returns error; agent retries with corrected path |
| KB agent never calls `finalize` (loops, exhausts tokens) | pipeline | enforce a hard step limit on the agent invocation; if exceeded, abort, no commit |
| OpenAI rate-limit / timeout | LangChain retry layer | one automatic retry; on second failure, propagate as ingest failure |
| HITL interrupt with no follow-up (user disappears) | session timeout | session evicted at 10 min; thread state lingers in checkpointer until process restart |
| Two messages from same user mid-flight | edge | second message is treated as a *resume* (because session is active with `expecting="answer"`). If the user actually meant a new message, they say so and we'll get it wrong sometimes. v0 limitation. |

## §4 — Lint agent

The lint agent is a read-heavy, one-shot audit that scans a single KB for structural issues and produces a markdown report.

**Trigger:** User sends `/lint <kb_slug>` via Telegram. The `handle_lint` command handler in `edge/handlers.py` calls `lint.run(vault_root, kb_slug, thread_id)`.

**Module:** `atlasmind/agents/lint.py`  
**System prompt:** `atlasmind/agents/prompts/lint_system.md`  
**Tools:** `make_kb_page_tools(vault_root, kb_slug)` + `make_kb_lint_tools(vault_root, kb_slug)`

### Checks performed (in order)

1. **Orphan pages** — files with no incoming `[[wikilink]]` from index.md or any other page.
2. **Missing entity links** — entity names mentioned in notes as plain text, without a `[[wikilink]]` to their entity page.
3. **Duplicate entity pages** — entity page pairs that likely represent the same real-world entity (name overlap + content similarity).

### Agent design

- No HITL (`ask_user` is not in the tool set).
- No `InMemorySaver` checkpointer (one-shot, no resume needed).
- Agent reads with `list_pages`, `read_page`, `search_pages`, `read_index`; writes one report file with `write_page`; terminates with `finalize_lint(summary)`.

### Output

- Report written to `<kb_slug>/lint/YYYY-MM-DD-lint-report.md`.
- `finalize_lint` returns `{"done": True, "summary": str}`.
- `lint.run()` returns `{"summary": str}` which the edge handler sends to Telegram.

---

## Out of scope (v0)

- Cross-KB awareness ("when filing in personal-diary, also note in econ-politics that I commented on inflation").
- Persistent checkpointer (Postgres / SQLite).
- Per-KB model selection (different KBs use different LLMs based on cost/quality).
- Streaming replies to Telegram while the agent works.
- Tool-level human approval (the `HumanInTheLoopMiddleware` per-tool gates).
- Full breathing system: contradiction-across-time, opinion evolution tracking, repetition detection across months. The thin per-ingest breathing pass above is a placeholder; it is disabled by default.
- Multi-step lint / health-check workflows from `llm_wiki.md`. Those become a separate `lint` agent post-v0.
