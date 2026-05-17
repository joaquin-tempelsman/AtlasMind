# KB Definitions — AtlasMind (Joaquin)

# IMPORTANT: This file contains your personal KB configuration.
# Do not commit to a public repo. Add kb_definitions/kb_definitions.md to .gitignore
# if you plan to make the code repo public.

---

```yaml
kbs:

  # ── Personal Diary ──────────────────────────────────────────────────────────
  - slug: personal-diary
    name: Personal Diary
    active: true
    description: |
      Real-world encounters, conversations, memorable events I lived through.
      First-person accounts of what happened. Named people, real places.
      Distinct from "reflections" — this is the raw event log, not the meaning I extract from it.
      Examples: coffee with a friend, a trip, a dinner, a conversation about someone's life.
    entities:
      - people
      - places
    kindle_sync: false
    breathing: false
    ingest_delay_minutes: 5
    agent_md: |
      ---
      type: kb_agent_md
      kb_slug: personal-diary
      version: 1
      ---

      # Personal Diary — Ingestion Schema

      ## What belongs here
      Real-world encounters, conversations, events I lived through. First-person.
      NOT abstract reflections (those go to `reflections`).
      NOT news or opinions about the world (those go to `econ-politics`).

      ## Folder layout
      - notes/    — one file per ingestion event
      - people/   — one page per recurring named person
      - places/   — one page per recurring named location

      ## When to create a new entity page
      - People: create `people/<slug>.md` on first mention BY NAME. Skip "my friend", "the waiter".
      - Places: create `places/<slug>.md` for named locations (cafés, neighborhoods, cities).
        Skip "the park", "her house", unnamed spaces.

      ## Note frontmatter (required)
      ```yaml
      type: note
      kb: personal-diary
      date: YYYY-MM-DD
      created_at: ISO-8601-UTC
      source_kind: voice | text | link
      source_meta: {}
      people: []       # list of named people mentioned
      places: []       # list of named places mentioned
      ```

      ## Entity page frontmatter — person
      ```yaml
      type: person
      kb: personal-diary
      first_seen: YYYY-MM-DD
      aliases: []
      ```

      ## Entity page frontmatter — place
      ```yaml
      type: place
      kb: personal-diary
      first_seen: YYYY-MM-DD
      ```

      ## Conventions
      - Wiki-link people and places: [[Mateo]], [[Café Tortoni]].
      - Note H1 title: short, present-tense, descriptive ("Coffee with Mateo at Tortoni").
      - Person page: maintain a `## Encounters` section; append one bullet per new note.
        Format: `- YYYY-MM-DD: [[note-slug|Short description]]`
      - Tone: first-person, conversational, warm. Write as if narrating to a future self.

  # ── Reflections ─────────────────────────────────────────────────────────────
  - slug: reflections
    name: Reflections
    active: true
    description: |
      Ideas, mental models, opinions, insights about the world — abstract content.
      What I think, not what happened to me (that's personal-diary).
      Philosophical musings, observations about human nature, life lessons, opinions formed.
      Often triggered by real events but focused on the idea, not the event.
    entities:
      - concepts
      - people
    kindle_sync: false
    breathing: false
    ingest_delay_minutes: 5
    agent_md: |
      ---
      type: kb_agent_md
      kb_slug: reflections
      version: 1
      ---

      # Reflections — Ingestion Schema

      ## What belongs here
      Abstract ideas, mental models, opinions, insights. What I think about the world.
      NOT what happened (personal-diary). NOT news/analysis (econ-politics).

      ## Folder layout
      - notes/      — one file per reflection
      - concepts/   — one page per recurring concept or mental model
      - people/     — thinkers, philosophers, authors whose ideas I engage with (NOT real-world people I know)

      ## When to create a new entity page
      - Concepts: create `concepts/<slug>.md` when a named idea recurs (e.g. "mimetic-desire", "status-games").
      - People (thinkers): create `people/<slug>.md` for thinkers/authors I reference repeatedly.
        Skip for one-off mentions.

      ## Note frontmatter (required)
      ```yaml
      type: note
      kb: reflections
      date: YYYY-MM-DD
      created_at: ISO-8601-UTC
      source_kind: voice | text | link
      source_meta: {}
      concepts: []    # named ideas or models this reflection touches
      people: []      # thinkers/sources referenced
      ```

      ## Entity page frontmatter — concept
      ```yaml
      type: concept
      kb: reflections
      first_seen: YYYY-MM-DD
      aliases: []
      ```

      ## Conventions
      - Wiki-link concepts and thinkers: [[mimetic-desire]], [[René Girard]].
      - Note H1 title: the central claim or question ("On status games and invisible audiences").
      - Concept page: maintain a `## Notes` section linking back to all notes that touch this concept.
      - Tone: first-person, exploratory. Incomplete thoughts are fine — capture the shape of the idea.

  # ── Economics & Politics ─────────────────────────────────────────────────────
  - slug: econ-politics
    name: Economics & Politics
    active: true
    description: |
      News, articles, commentary on economics and politics. Third-person analysis.
      Sources: FT, El País, Cenital, The Economist, podcasts on macro/policy/geopolitics.
      Includes my reactions and opinions on articles I read or listen to.
      NOT personal encounters (diary) or abstract philosophy (reflections).
    entities:
      - people
      - topics
    kindle_sync: false
    breathing: false
    ingest_delay_minutes: 5
    url_metadata_fields:
      - media_source
      - article_writer
    include_article_content: false
    agent_md: |
      ---
      type: kb_agent_md
      kb_slug: econ-politics
      version: 1
      ---

      # Economics & Politics — Ingestion Schema

      ## What belongs here
      News, analysis, commentary on economics and politics. My reactions to articles/podcasts.
      Sources include FT, El País, Cenital, The Economist, macro/geopolitics podcasts.
      NOT abstract philosophy (reflections). NOT personal diary (personal-diary).

      ## Folder layout
      - notes/    — one note per article, podcast, or item
      - people/   — journalists, economists, politicians, analysts referenced repeatedly
      - topics/   — recurring thematic areas (e.g. "argentina-economy", "us-elections", "monetary-policy")

      ## When to create a new entity page
      - People: create `people/<slug>.md` for analysts, journalists, economists I reference 2+ times.
      - Topics: create `topics/<slug>.md` for a recurring thematic cluster once it appears in 3+ notes.

      ## Note frontmatter (required)
      ```yaml
      type: note
      kb: econ-politics
      date: YYYY-MM-DD
      created_at: ISO-8601-UTC
      source_kind: voice | text | link
      source_meta: {}
      people: []      # journalists, economists, politicians mentioned
      topics: []      # thematic tags (kebab-case, from topics/ folder)
      media_source:   # e.g. "FT", "El País", "Cenital", "The Economist"
      ```

      ## Entity page frontmatter — person
      ```yaml
      type: person
      kb: econ-politics
      first_seen: YYYY-MM-DD
      role:           # e.g. "economist", "journalist", "politician"
      affiliation:    # e.g. "FT", "IMF", "Argentine government"
      ```

      ## Entity page frontmatter — topic
      ```yaml
      type: topic
      kb: econ-politics
      first_seen: YYYY-MM-DD
      aliases: []
      ```

      ## Conventions
      - Wiki-link people and topics: [[Martin Wolf]], [[argentina-economy]].
      - Note H1 title: the headline or main claim ("FT: Argentina's primary surplus and the IMF deal").
      - Tone: third-person summary + first-person reaction separated by a `---` divider.
        Summary comes first; my reaction/opinion after the divider.
      - Include the source in `source_meta.title` if available.

  # ── Book Readings ────────────────────────────────────────────────────────────
  - slug: book-readings
    name: Book Readings
    active: false
    description: |
      Reading notes from books — excluding economics/politics books (those go to econ-politics).
      Characters, plot, themes, quotes, my reactions. Literary fiction, essays, biographies,
      philosophy books, science books. Kindle highlights are imported automatically for this KB.
    entities:
      - books
      - characters
      - people
    kindle_sync: true                 # Kindle API highlight sync enabled for this KB only
    breathing: false
    ingest_delay_minutes: 5
    agent_md: |
      ---
      type: kb_agent_md
      kb_slug: book-readings
      version: 1
      ---

      # Book Readings — Ingestion Schema

      ## What belongs here
      Reading notes from books. Literary fiction, essays, biographies, philosophy, science.
      Excludes econ/politics books (route those to econ-politics).
      Includes Kindle highlights (auto-imported when kindle_sync is enabled).

      ## Folder layout
      - notes/       — one note per reading session or batch of highlights
      - books/       — one page per book
      - characters/  — one page per recurring character or person in the book
      - people/      — authors and real people referenced in non-fiction books

      ## When to create a new entity page
      - Books: create `books/<slug>.md` on the first note from that book.
      - Characters: create `characters/<slug>.md` for named characters who appear in 2+ notes.
      - Authors/people: create `people/<slug>.md` for authors and real people in non-fiction.

      ## Note frontmatter (required)
      ```yaml
      type: note
      kb: book-readings
      date: YYYY-MM-DD
      created_at: ISO-8601-UTC
      source_kind: voice | text | link
      source_meta: {}
      book:           # slug of the book (links to books/<slug>.md)
      characters: []  # character slugs mentioned
      people: []      # real people (authors, etc.)
      ```

      ## Entity page frontmatter — book
      ```yaml
      type: book
      kb: book-readings
      first_seen: YYYY-MM-DD
      author:
      year_published:
      genre:
      status: reading | finished | abandoned
      ```

      ## Entity page frontmatter — character
      ```yaml
      type: character
      kb: book-readings
      first_seen: YYYY-MM-DD
      book:           # slug of the book they appear in
      aliases: []
      ```

      ## Conventions
      - Wiki-link books, characters, and authors: [[crime-and-punishment]], [[Raskolnikov]], [[Dostoevsky]].
      - Book page: maintain `## Reading notes` (links to all notes from that book) and `## Characters`.
      - Character page: one-paragraph description + `## Appearances` section with note links.
      - Note H1 title: book title + chapter or theme ("Crime and Punishment — the dream sequence").
      - Tone: mix of summary and personal reaction. Quotes indented with `>`.
      - Kindle highlights: treat each imported highlight as a note; group multiple highlights from
        the same session into one note if they share a theme.

  # ── Work & ML ────────────────────────────────────────────────────────────────
  - slug: work-ml
    name: Work & ML
    active: false
    description: |
      Work ideas, ML theory, technical reflections, research notes.
      Papers I read, techniques I explore, work problems I think about.
      NOT personal encounters (diary). NOT general philosophy (reflections).
    entities:
      - concepts
      - people
    kindle_sync: false
    breathing: false
    ingest_delay_minutes: 5
    agent_md: |
      ---
      type: kb_agent_md
      kb_slug: work-ml
      version: 1
      ---

      # Work & ML — Ingestion Schema

      ## What belongs here
      Work ideas, ML/AI theory, technical reflections, research notes. Papers, experiments,
      technical conversations with colleagues. My opinions on technical topics.
      NOT personal diary. NOT abstract philosophy.

      ## Folder layout
      - notes/     — one note per item
      - concepts/  — one page per recurring technical concept or idea
      - people/    — researchers, colleagues referenced repeatedly (researchers by their ideas, not social context)

      ## When to create a new entity page
      - Concepts: create `concepts/<slug>.md` when a named technique, model, or idea recurs.
        Examples: "transformer-architecture", "rlhf", "chain-of-thought", "feature-engineering".
      - People: create `people/<slug>.md` for researchers/authors referenced in 2+ notes.

      ## Note frontmatter (required)
      ```yaml
      type: note
      kb: work-ml
      date: YYYY-MM-DD
      created_at: ISO-8601-UTC
      source_kind: voice | text | link
      source_meta: {}
      concepts: []   # technical concepts touched
      people: []     # researchers or colleagues referenced
      ```

      ## Entity page frontmatter — concept
      ```yaml
      type: concept
      kb: work-ml
      first_seen: YYYY-MM-DD
      domain:        # e.g. "nlp", "rl", "ml-systems", "work"
      aliases: []
      ```

      ## Conventions
      - Wiki-link concepts and researchers: [[chain-of-thought]], [[Andrej Karpathy]].
      - Note H1: the paper title, technique name, or work idea ("Attention is All You Need — key ideas").
      - Concept page: maintain `## Notes` (links) and `## Summary` (one-paragraph synthesis).
      - Tone: technical but conversational. Incomplete notes are fine — capture the insight.

  # ── Hobbies ──────────────────────────────────────────────────────────────────
  - slug: hobbies
    name: Hobbies
    active: false                     # muted for v0 — low value; flip active: true when ready
    description: |
      Hobby content: tabletop RPGs (D&D), wine/vermouth exploration, cooking experiments,
      sports, leisure activities. Content that doesn't fit the other KBs.
    entities:
      - topics
    kindle_sync: false
    breathing: false
    ingest_delay_minutes: 5
```
