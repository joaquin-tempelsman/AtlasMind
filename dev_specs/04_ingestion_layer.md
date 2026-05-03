# 04 — Ingestion Layer (L1) + Ingest Queue

## Purpose

Take a `RawMessage` from the edge and produce a `NormalizedItem`. Nothing more. This layer does **not** decide where the item goes (that's the router) or how it's stored (that's the KB ingestion agent).

A second concern lives here conceptually: the **per-KB Ingest Queue** that sits between the router and the KB ingestion agent, batching items before they trigger an agent run.

## Inputs / Outputs

- **In:** `RawMessage` (see [`01_architecture.md` §3](01_architecture.md)).
- **Out:** `NormalizedItem` with a canonical `text` field plus `source_kind` and `source_meta`.
- **Side effect:** persists scraped HTML under `<vault>/raw/links/` for link ingests. Raw audio is **not** persisted (see §Voice below).

## Internal structure

```
ingestion/
├── normalize.py        # the single entry point: normalize(raw) -> NormalizedItem
├── transcriber.py      # voice bytes -> text  (Whisper)
└── link_fetcher.py     # url -> {text, title} (v0: readability-lxml)
```

## The contract per source kind

### `kind = "text"`
Trivial. Pass-through.
```
NormalizedItem(
  text = raw.text.strip(),
  source_kind = "text",
  source_meta = {},
  ...
)
```

### `kind = "voice"`
1. Whisper has already run in the edge layer (because we want to reply with the transcript fast). The transcript is on `raw.text`.
2. Raw audio is **not persisted**. The audio bytes are used only for transcription and then discarded. If re-transcription is ever needed, Telegram stores files on its own servers for approximately one year and they are retrievable via `voice_file_id`.
3. Emit:
```
NormalizedItem(
  text = raw.text,
  source_kind = "voice",
  source_meta = {"voice_file_id": ..., "duration_s": ...},
  ...
)
```

### `kind = "link"`
Decided by the edge: a text message whose entire body is a single URL is treated as `kind="link"`. (This is the simplest rule that matches the PRD's example flow without false positives. It is wrong for "here's a link: https://...", which we accept.)
1. Fetch the URL with a short timeout (10s).
2. Extract the main article text (v0: `readability-lxml` — established library, no LLM calls). Title goes to `source_meta`.
3. Persist the raw HTML under `raw/links/<received_at_iso>__<sha1(url)>.html`.
4. Emit:
```
NormalizedItem(
  text = "<title>\n\n<body text>",
  source_kind = "link",
  source_meta = {"url": ..., "title": ..., "fetched_at": ..., "html_path": "raw/links/..."},
  ...
)
```

If the fetch fails or returns empty body, the layer raises `LinkFetchError`. The pipeline catches it and replies to the user — it does **not** fall back to using the URL as plain text, because that would route the link into a KB based on the URL string and that's misleading.

## Why we do not persist raw audio

Transcript quality is the only thing that matters downstream. If a transcript looks wrong, the user can re-send the voice note. Telegram retains the original audio file on its servers (accessible via `voice_file_id`) for approximately one year. Persisting locally adds storage overhead and complexity for a recovery path that is rarely needed.

Link HTML is still persisted under `raw/links/` because re-fetching a URL may yield different content (paywalls, updates, deletions) — the HTML snapshot is the only guarantee we have of what was seen at ingest time.

## Pluggability — the interfaces

Define two thin protocols so the implementation can be swapped without touching agents:

```
class Transcriber(Protocol):
    async def transcribe(self, audio_bytes: bytes, hint_filename: str) -> str: ...

class LinkFetcher(Protocol):
    async def fetch(self, url: str) -> tuple[str, dict]:  # (text, meta)
        ...
```

v0 has one impl of each. Tests mock the protocols. Firecrawl is the planned v0+1 swap for `LinkFetcher` (see [`08_deferred_v0+1.md` §5](08_deferred_v0+1.md)).

## Per-KB Ingest Queue

After routing, items are **not immediately dispatched** to the KB ingestion agent. The pipeline maintains an in-memory per-KB queue:

```
IngestQueue:
  queues: dict[kb_slug, list[RoutedItem]]
  timers: dict[kb_slug, asyncio.TimerHandle]
```

**Flow:**
1. Router emits a `RoutedItem` for `kb_slug`.
2. Pipeline appends it to `queues[kb_slug]`.
3. Any existing timer for that KB is cancelled and reset to `ingest_delay_minutes` (read from `kb_definitions.md` for that KB; default 5 minutes).
4. Pipeline replies to the user immediately: `"Routed to <KB name> — will ingest shortly."` (No final confirmation yet.)
5. When the timer fires, the pipeline drains `queues[kb_slug]`, invokes the KB ingestion agent once with all queued items, and sends the final Telegram confirmation after the batch completes.

**Why batch:** multiple items sent in quick succession (e.g., a voice burst about a book) belong to one conceptual ingestion session. Batching them into one agent run produces a more coherent note structure and avoids redundant entity-page updates.

**HITL interaction with batching:** if the KB ingestion agent calls `ask_user` during a batch run, the batch is paused. The user's answer resumes the same agent instantiation. The timer does not re-fire for the same batch.

**Process restart:** the in-memory queue is lost on restart. Items that were queued but not yet ingested are silently dropped. This is acceptable in v0 — the user will notice if the Telegram confirmation never arrives and can re-send. Post-v0: persist the queue to a lightweight store (SQLite or a flat file).

## Failure modes

| Failure | Surfaces as | Effect |
|---|---|---|
| Whisper API error / timeout | edge replies "Transcription failed", no `RawMessage` reaches L1 | nothing queued |
| `link_fetcher` HTTP error (4xx/5xx) | `LinkFetchError` → pipeline → user reply "Couldn't fetch \<url\>" | nothing queued |
| Article extraction returns empty | `LinkFetchError("empty body")` | nothing queued |
| KB ingestion agent fails mid-batch | logged + partial result; git layer detects dirty working tree and aborts commit | items remain in vault working tree; user told to inspect |

## Out of scope (v0)

- Firecrawl / headless browser scraping. v0 uses `readability-lxml` and accepts that JS-heavy pages will sometimes return thin extracts. Firecrawl is the planned v0+1 swap.
- Image asset download from articles (PRD post-v0).
- Multi-language transcription tuning, speaker diarization, timestamps in transcripts.
- PDF / EPUB / Kindle imports. Manual paste only.
- Deduplication ("you already added this URL last week"). The router *will* see recent entries via `general_log.md`, but explicit dedup logic is post-v0.
- Queue persistence across restarts. v0 queue is in-memory only.
