# 06 — KB Contract

## Purpose

Lock down what every KB looks like on disk: required files, frontmatter shapes, naming conventions. This is the contract the KB ingestion agent reads from and writes to. Obsidian, the user, and the agent must all agree on this layout.

---

## 1. Required files in every KB

Every KB folder contains, at minimum:

```
<kb_slug>/
├── agent.md        # KB-specific schema/prompt addendum
├── entities.md     # entity alias registry (user-editable + agent-maintained)
├── index.md        # catalog of pages in this KB
├── log.md          # chronological per-KB log
└── notes/          # default destination for new notes
```

These five are scaffolded by `setup.sh` (which calls `python -m atlasmind.bootstrap`) from the definitions in `kb_definitions/kb_definitions.md`. The agent can *create* additional folders (`people/`, `topics/`, `books/`, etc.) as the KB's `agent.md` directs.

---

## 2. KB definitions — the single source of truth

KBs are defined in **one place only**: `kb_definitions/kb_definitions.md` in the code repo. This is a user-owned YAML file that the user edits to add, remove, enable, or configure KBs. It is the input to `bootstrap.py`, which generates everything else.

**Never define a KB anywhere else.** The `_meta/kb_registry.md` in the vault is **generated** from `kb_definitions.md` by bootstrap — do not edit it directly.

Adding a new KB:
1. Add an entry to `kb_definitions/kb_definitions.md`
2. Run `setup.sh --bootstrap-vault` (or `python -m atlasmind.bootstrap`)
3. Bootstrap creates the KB folder, scaffolds `agent.md`/`index.md`/`log.md`/`notes/`, and regenerates `_meta/kb_registry.md`

Disabling a KB:
1. Set `active: false` in its `kb_definitions.md` entry
2. Restart the bot (the registry is loaded at startup)
3. The router will not route to inactive KBs; existing vault content is preserved unchanged

### KB definition fields

Each entry in `kb_definitions.md`:

```yaml
- slug: personal-diary           # kebab-case, ≤ 32 chars, unique
  name: Personal Diary           # display name (used in Telegram replies, index headers)
  description: |                 # one paragraph; this is what the router reads
    Real-world encounters, conversations, events...
  active: true                   # false → router ignores this KB; ingestion agent refuses writes
  entities: [people, places]     # folder names to scaffold under <kb_slug>/
  kindle_sync: false             # Kindle API integration (per-KB feature flag; v0+1)
  breathing: false               # thin per-ingest breathing step (default false; enable when vault is mature)
  ingest_delay_minutes: 5        # debounce window before batch ingest fires (default 5)
  url_metadata_fields: []        # LLM-extracted URL metadata fields (e.g. [media_source, article_writer])
  include_article_content: false # forward full article text to KB agent (default false — keeps context lean)
```

All fields except `slug`, `name`, `description`, and `active` have defaults and are optional.

`url_metadata_fields` controls which structured metadata the KB ingestion agent extracts from linked articles via an LLM call. The agent calls `extract_url_metadata(url, fields)` for any link item or voice/text item with a `linked_url`. If the list is empty, no metadata extraction is performed.

`include_article_content` controls whether the full readability-extracted article text is forwarded to the KB ingestion agent in the batch prompt. When `false` (default), only a short representation (`[Link] {title}\nURL: {url}`) is forwarded, keeping context lean. The raw article text is still stored in `source_meta["raw_article_text"]` but not surfaced in the prompt.

### `_meta/kb_registry.md` — generated, do not edit

This file is written by bootstrap and read by the router at runtime. Format:

```markdown
---
type: kb_registry
version: 1
generated_from: kb_definitions/kb_definitions.md
---

# KB Registry

## personal-diary
- **Name:** Personal Diary
- **Description:** Real events, encounters with friends and family, memorable conversations. Distinct from "reflections" — this is what *happened*, not what I *thought about it*.
- **Entities:** people, places
- **Active:** true
- **Breathing:** false
- **Ingest delay (min):** 5
- **URL metadata fields:** 
- **Include article content:** false

## reflections
- **Name:** Reflections
- **Description:** ...
- **Active:** true

...
```

The router parses this on every run. **Never** done at runtime by an agent.

---

## 3. `_meta/general_log.md`

Append-only log of every routing decision. Format (each entry is one block):

```markdown
## [2026-05-02T14:25:03Z] route | personal-diary | high
**Source:** voice (whisper)
**Preview:** "Met Mateo at Tortoni today, he was telling me about..."
**Rationale:** Real-world encounter with a named friend; no abstract content.
**File:** personal-diary/notes/2026-05-02-coffee-with-mateo.md
```

Why this format:

- **Single grep target.** `grep "^## \[" general_log.md` returns all routing entries. The router's `read_recent_routing` tool uses stratified sampling over this output.
- **Confidence and KB are in the title line.** Easy to scan.
- **Preview is one short line** — the router doesn't need the full transcript replayed back at it.
- **File path is recorded** so we can audit "where did that voice note end up?" without grepping the whole vault.

Parser lives in `atlasmind/vault/frontmatter.py` (or a sibling `log_parser.py`). Strict: malformed entries are skipped with a warning, never silently mutated.

---

## 4. `_meta/routing_rules.md`

Free-form, human-edited. Whatever the user types here is read by the router as soft hints. Example:

```markdown
# Routing Rules

- Anything mentioning "my dad" or "papá" → personal-diary, even if reflective.
- Articles from FT, El País, Cenital → econ-politics by default.
- Notes about ML papers (transformers, RLHF, etc.) → work-ml, not reflections.
- D&D / vermouth / hobby content → if hobbies KB is active, route there; else reflections.
```

Strictly advisory. The router is told "these are hints from the user, you can override if context clearly disagrees, but you should err on the side of following them."

---

## 5. Per-KB `agent.md`

This is the **most important file in the entire system**. It tells the KB ingestion agent the schema for that KB. It lives in the vault repo (so the user owns it and can edit it in Obsidian/VSCode), and it is concatenated verbatim into the KB ingestion agent's system prompt.

Skeleton template (each KB starts here, the user evolves it):

```markdown
---
type: kb_agent_md
kb_slug: personal-diary
version: 1
---

# Personal Diary — Ingestion Schema

## What belongs here

Real-world encounters, conversations, events I lived through. First-person.
NOT abstract reflections (those go to `reflections`).

## Folder layout

- notes/         — daily entries, one file per ingestion
- people/        — one page per recurring person mentioned
- places/        — one page per recurring location

## When to create a new entity page

- People: create `people/<slug>.md` the first time someone is mentioned BY NAME.
  Skip "my friend", "the waiter".
- Places: create `places/<slug>.md` only for named places (cafés, neighborhoods,
  cities). Skip "the park", "her house".

## Note frontmatter (required)

` ` `yaml
type: note
kb: personal-diary
date: 2026-05-02
people: [Mateo, Sofía]
places: [Café Tortoni]
source_kind: voice
source_meta:
  voice_file_id: "..."
` ` `

## Entity page frontmatter (required)

` ` `yaml
type: person
kb: personal-diary
first_seen: 2026-05-02
aliases: []
` ` `

## Conventions

- Wiki-link people and places using Obsidian `[[Mateo]]` syntax.
- Note titles in body (H1) are short, present-tense ("Coffee with Mateo").
- When updating a person's page, append to a `## Encounters` section with a
  bullet linking the new note: `- 2026-05-02: [[2026-05-02-coffee-with-mateo|Coffee at Tortoni]]`
```

Each KB's `agent.md` differs in:
- Folder taxonomy (people/places vs books/characters vs people/topics).
- Frontmatter schema for that KB's note type.
- Tone of the writing (diary is first-person, econ-politics is third-person summary).
- Linking style.

**The agent does not invent these.** It reads `agent.md` and follows it. If the user wants different behavior, they edit `agent.md`.

---

## 6. Note frontmatter — minimum fields across all KBs

Regardless of KB, every note has at least:

```yaml
---
type: note
kb: <kb_slug>
date: YYYY-MM-DD
created_at: <ISO-8601 UTC>     # exact ingestion timestamp
source_kind: voice | text | link
source_meta:
  # whatever the ingestion layer captured: url, title, voice_file_id, etc.
---
```

Per-KB extras (people, places, books, etc.) are added on top per `agent.md`. This is what enables Dataview queries post-v0 — but v0 just writes correct frontmatter and trusts the user.

---

## 7. `index.md` — per-KB catalog

Format:

```markdown
---
type: kb_index
kb: personal-diary
last_updated: 2026-05-02
---

# Personal Diary — Index

## Notes
- 2026-05-02 — [[notes/2026-05-02-coffee-with-mateo|Coffee with Mateo]] — recurring philosophy chats.
- 2026-04-28 — [[notes/2026-04-28-easter-with-family|Easter with family]] — first family gathering after the move.
- ...

## People
- [[people/mateo|Mateo]] — close friend; weekly encounters since 2024.
- [[people/sofia|Sofía]] — work colleague turned friend; recurring philosophy thread.

## Places
- [[places/cafe-tortoni|Café Tortoni]] — meeting spot.
```

The agent appends to the right section on each ingest. Sections are created on demand. Order within a section is reverse-chronological for `Notes`, alphabetical otherwise (the agent enforces this on each touch — cheap because the file is small).

---

## 8. `log.md` — per-KB chronological log

Same format as `_meta/general_log.md` but scoped:

```markdown
## [2026-05-02T14:25:03Z] ingest | coffee-with-mateo
**Note:** [[notes/2026-05-02-coffee-with-mateo|Coffee with Mateo]]
**Pages updated:** people/mateo, places/cafe-tortoni
**Summary:** Met Mateo at Tortoni; talked about his dissertation, his
mom's recovery, plans for July.
```

Optional kinds of entries (post-v0): `lint`, `breathe`, `query`. v0 only writes `ingest`.

---

## 9. Naming and slugs

`atlasmind/vault/paths.py` owns these conventions:

- **KB slugs:** kebab-case, alphanumerics + dashes only, ≤ 32 chars.
- **Note filenames:** `YYYY-MM-DD-<slug>.md` where slug is ≤ 6 words, kebab-case, ASCII-folded (`café` → `cafe`). Date is the local-TZ date at write time.
- **Entity page filenames:** kebab-case slug, no date prefix. `mateo.md`, `cafe-tortoni.md`.
- **Collisions:** if `2026-05-02-coffee-with-mateo.md` exists, append `-2`, `-3`. Never overwrite.

The agent calls a tool to *propose* a slug; the path module validates and returns the final filename, handling collisions deterministically.

---

## 10. Extending a KB's schema

Schema evolution happens entirely through `agent.md` edits in the vault. No script is needed.

**To add a new entity type to a KB** (e.g. add `locations/` to `work-ml`):
1. Open the KB's `agent.md` in Obsidian or any editor.
2. Add a section under `## Folder layout` describing the new folder and its naming conventions.
3. Add a frontmatter block under `## Entity page frontmatter` for the new type.
4. On the next ingest that mentions a matching entity, the agent will create the folder and entity page according to the new schema.

**To add extra frontmatter fields to a specific entity type** (e.g. add `nationality:` to `people/` pages in `econ-politics`):
1. Open the KB's `agent.md`.
2. Add the new field to the relevant frontmatter block in `## Entity page frontmatter` or `## Note frontmatter`.
3. The agent reads `agent.md` verbatim and will write the new field on all subsequent writes to that entity type. Existing pages are not retroactively updated (that's a lint/breathing concern, post-v0).

**To enable a per-KB feature flag** (e.g. enable breathing):
1. Edit `kb_definitions/kb_definitions.md` and set `breathing: true` for that KB.
2. Restart the bot (config is loaded at startup).
3. No vault edits required.

Git history of the vault captures when schemas changed. The user can revert an `agent.md` edit from Obsidian's git pane or VSCode.

---

## 11. `entities.md` — entity alias registry

Each KB has an `entities.md` file that maps canonical entity names to their known aliases. It serves two purposes:

1. **User pre-definition:** Before ingesting content about "Piketty", the user adds `Thomas Piketty | Piketty | T. Piketty` so the agent always uses the canonical page name.
2. **Agent auto-registration:** After creating a new entity page, the agent calls `register_entity()` to add that entity to the registry for future reference.

### Format

```markdown
---
type: kb_entity_registry
kb: <kb_slug>
---

# Entity Registry

Each line: Canonical Name | alias1 | alias2 | ...
Edit this file in Obsidian or via the vault repo to pre-define entities.
The ingestion agent uses canonical names when creating entity pages.

---
Thomas Piketty | Piketty | T. Piketty | @piketty
Café Tortoni | Tortoni | the café
```

- One entity per line, pipe-separated.
- First field is the canonical name — this is used for the page slug (`vault/paths.py:entity_filename`).
- Remaining fields are aliases — alternate references the agent should recognize.
- Blank lines, header lines (`#`), and the YAML frontmatter block are ignored by the parser.
- The file is user-editable at any time in Obsidian or via the vault repo.

### Agent behavior

Before creating or updating any entity page, the KB ingestion agent reads the "Entity Registry" section injected into its batch context. If a referenced name matches a known alias, it uses the canonical name for the page path and title. After creating a new entity page not already in the registry, it calls `register_entity(canonical_name, aliases)` to log it.

The `register_entity` tool is provided by `atlasmind/agents/tools/kb_entities.py` and merges new aliases into existing entries rather than overwriting them.

---

## 12. What the user can break (and we accept)

The intended workflow is Telegram-only. The user opens Obsidian to **read**, not to write. The only deliberate vault edits are `agent.md` and `routing_rules.md`.

If the user does edit other vault files:
- **Edit any wiki page:** fine in principle; the agent will append on next ingest, potentially creating duplicate entries in some sections.
- **Edit `agent.md`:** intended. The agent will pick up changes on the next ingest (requires bot restart if the KB agent is cached).
- **Move files around:** will break wiki-links until the agent re-encounters them.
- **Delete the `_meta/` folder:** catastrophic — bootstrap will recreate; routing history is lost.
- **Edit `index.md` directly:** the agent will re-append on next ingest, possibly creating duplicates.

We don't defend against any of this in v0. The vault is a markdown repo and the user can do whatever they want with it. Git history is the safety net.
