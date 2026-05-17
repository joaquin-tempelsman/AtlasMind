# KB Definitions — CI / Test fixture

This file is used by GitHub Actions CI in place of the gitignored personal `kb_definitions.md`.
It defines exactly the KBs the test suite expects. Do not rename slugs here without updating tests.

---

```yaml
kbs:

  - slug: personal-diary
    name: Personal Diary
    active: true
    description: |
      Real-world encounters, conversations, events I lived through. First-person.
      Distinct from reflections — this is what happened, not what I thought about it.
    entities:
      - people
      - places
    breathing: false
    ingest_delay_minutes: 5

  - slug: reflections
    name: Reflections
    active: true
    description: |
      Abstract thoughts, ideas, opinions, personal philosophy. Not events — patterns and meaning.
    entities:
      - people
      - concepts
    breathing: false
    ingest_delay_minutes: 5

  - slug: econ-politics
    name: Econ & Politics
    active: true
    description: |
      Articles, analysis and commentary on economics, political science, and geopolitics.
    entities:
      - people
      - topics
    breathing: false
    ingest_delay_minutes: 5

  - slug: work-ml
    name: Work / ML
    active: false
    description: |
      Machine learning research, work notes, papers, experiments, professional learning.
    entities:
      - people
      - concepts
    breathing: false
    ingest_delay_minutes: 5

  - slug: book-readings
    name: Book Readings
    active: false
    description: |
      Books I am reading or have read — summaries, notes, highlights, characters.
    entities:
      - books
      - characters
      - people
    breathing: false
    ingest_delay_minutes: 5
```
