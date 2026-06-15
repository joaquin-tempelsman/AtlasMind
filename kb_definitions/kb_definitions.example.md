# KB Definitions — Example / Template

This file is your **single source of truth** for knowledge bases. Copy it to `kb_definitions.md`,
fill in your KBs, and run `setup.sh --bootstrap-vault`.

- Each entry becomes a folder in the vault and an entry in `_meta/kb_registry.md`.
- The system is KB-agnostic: you can have 1 KB or 50. Add an entry here and bootstrap it.
- `active: false` mutes a KB: router ignores it, ingestion refuses to write to it. Vault content is preserved.
- All fields except `slug`, `name`, `description`, and `active` are optional (defaults shown).

---

```yaml
kbs:

  # ── Example KB 1 ────────────────────────────────────────────────────────────
  - slug: my-journal                  # kebab-case, alphanumeric + dashes, ≤ 32 chars, unique
    name: My Journal                  # display name (used in Telegram replies and vault headers)
    active: true                      # true = router sees it; false = muted/paused
    description: |
      Personal diary entries. Real-world encounters, conversations, events I lived through.
      First-person. Distinct from reflections — this is what happened, not what I thought.
      (The router reads this paragraph to decide routing. Write it in plain language.)

    # Optional: entity folders to scaffold under <slug>/
    # These are created by bootstrap. Additional folders can be created later by editing agent.md.
    entities:
      - people
      - places

    # Optional: per-KB feature flags
    kindle_sync: false                # Kindle API integration (import highlights from Kindle) — v0+1 feature
    breathing: false                  # thin per-ingest breathing/reflection step (enable when vault has ≥30 notes)

    # Optional: batching window
    ingest_delay_minutes: 5           # items are batched for this many minutes before the agent runs

    # Optional: agent.md template override
    # If omitted, bootstrap uses the default template from atlasmind/agents/prompts/agent_md_default.md
    # If provided, this text becomes the starting content of <slug>/agent.md in the vault.
    # The user can edit agent.md freely after bootstrap; this is only the initial content.
    agent_md: |
      ---
      type: kb_agent_md
      kb_slug: my-journal
      version: 1
      ---

      # My Journal — Ingestion Schema

      ## What belongs here
      Real-world encounters, conversations, events I lived through. First-person.
      NOT abstract reflections (those go to a separate KB).

      ## Folder layout
      - notes/    — one file per ingestion event
      - people/   — one page per recurring named person
      - places/   — one page per recurring named location

      ## When to create a new entity page
      - People: on first mention BY NAME. Skip anonymous references ("the waiter", "my friend").
      - Places: named locations only (cafés, neighborhoods, cities). Skip "the park", "her house".

      ## Note frontmatter (required)
      ```yaml
      type: note
      kb: my-journal
      date: YYYY-MM-DD
      created_at: ISO-8601-UTC
      source_kind: voice | text | link
      source_meta: {}
      raw_capture: raw/captures/<ts>__<hash>.md   # verbatim original (text/voice), if provided
      people: []
      places: []
      ```

      ## Entity page frontmatter — person
      ```yaml
      type: person
      kb: my-journal
      first_seen: YYYY-MM-DD
      aliases: []
      ```

      ## Entity page frontmatter — place
      ```yaml
      type: place
      kb: my-journal
      first_seen: YYYY-MM-DD
      ```

      ## Conventions
      - Wiki-link people and places: [[Person Name]], [[Place Name]].
      - Note H1 title: short, present-tense ("Coffee with Ana").
      - Person page: append to ## Encounters on each new mention.
      - Tone: first-person, conversational.

  # ── Example KB 2 — minimal entry ────────────────────────────────────────────
  - slug: reading-notes
    name: Reading Notes
    active: true
    description: |
      Notes from books I am reading. Characters, plot, themes, quotes.
      Excludes news/commentary — those go to a separate KB.
    entities:
      - books
      - characters
    kindle_sync: true                 # enable Kindle highlight sync for this KB
    breathing: false

  # ── Example KB 3 — inactive (muted) ─────────────────────────────────────────
  - slug: hobbies
    name: Hobbies
    active: false                     # router ignores this KB; existing vault content preserved
    description: |
      Hobby content: cooking experiments, games, sports, leisure activities.
    entities:
      - topics
```

---

## Field reference

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `slug` | string | yes | — | kebab-case, ≤ 32 chars, unique across all KBs |
| `name` | string | yes | — | Display name shown in Telegram replies |
| `active` | bool | yes | — | `false` = router skips this KB; agent refuses writes |
| `description` | string | yes | — | Router reads this to decide routing. One clear paragraph. |
| `entities` | list[string] | no | `[]` | Folder names to scaffold under `<slug>/` on bootstrap |
| `kindle_sync` | bool | no | `false` | Kindle API highlight import — v0+1 feature, per-KB flag |
| `breathing` | bool | no | `false` | Thin reflection pass after each ingest. Enable when vault matures. |
| `ingest_delay_minutes` | int | no | `5` | Debounce window (minutes) before batch ingest fires |
| `agent_md` | string | no | default template | Initial content of `<slug>/agent.md`. User can edit freely after bootstrap. |

## Adding a new KB after initial setup

1. Add an entry to this file (`kb_definitions.md`).
2. Run `./setup.sh --bootstrap-vault` (or `python -m atlasmind.bootstrap`).
3. Restart the bot.

The new KB folder is created in the vault, `_meta/kb_registry.md` is regenerated, and the router will start routing to the new KB on the next run.

## Disabling a KB

Set `active: false` and restart the bot. No data is deleted. Re-enable by setting `active: true` and restarting.
