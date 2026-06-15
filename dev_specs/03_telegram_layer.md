# 03 — Telegram Layer (L0)

## Purpose

Receive user input from Telegram, hand it off to the pipeline, and route any agent-driven follow-up questions back to the user. This layer is the *only* thing that touches `python-telegram-bot`.

## Inputs / Outputs

- **In:** Telegram updates (text, voice notes, links pasted as text).
- **Out:**
  - `RawMessage` objects passed to `pipeline.process(...)`.
  - Reply messages sent back to the user (final ingestion summary, transcription preview, HITL questions, errors).

## Internal structure

```
edge/
├── telegram_app.py     # bootstraps Application, wires handlers, runs polling
├── handlers.py         # handle_voice, handle_text — only adapt; no business logic
└── session.py          # in-memory map: telegram_user_id → active session metadata
```

## Commands

Slash commands are wired as `CommandHandler` instances in `telegram_app.py` and handled in `handlers.py`. All commands pass through `_auth_guard` (allowlist) first.

- **`/lint <kb_slug>`** — runs a structural audit on a KB (see [`05_agent_layer.md` §4](05_agent_layer.md)).
- **`/version`** — replies with the currently-deployed code version: short git commit SHA, the commit subject and date, and (if present) the deploy stamp written by the deploy workflow. Read-only and synchronous; reads git metadata of the running checkout via `atlasmind/version.py`. This is the operator's confirmation that a deploy landed — the reported SHA should match `main`'s HEAD after a successful deploy.

## Learnings lifted from talkvault

These are validated patterns from [`bot/handlers.py`](https://github.com/joaquin-tempelsman/talkvault/blob/main/bot/handlers.py) and [`bot/main.py`](https://github.com/joaquin-tempelsman/talkvault/blob/main/bot/main.py). Re-use them; do not re-derive them.

1. **`Application.builder().token(...).build()`** with two `MessageHandler` instances:
   - `MessageHandler(filters.VOICE, handle_voice)`
   - `MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)`
2. **Run with `app.run_polling(drop_pending_updates=True)`.** Webhooks are out of scope for v0.
3. **Voice download via `context.bot.get_file(msg.voice.file_id)` → `download_to_memory(io.BytesIO())`.** Do not write to disk before transcription; the buffer goes straight to Whisper, then the original bytes are persisted under `raw/audio/` by the ingestion layer if (and only if) ingestion succeeds.
4. **One Whisper call per message** using `OpenAI(...).audio.transcriptions.create(model="whisper-1", file=...)`. Set `audio_file.name = "voice.ogg"` because OpenAI's SDK uses the suffix to detect format.
5. **Reply with the transcript before running the agent** (`"Transcript: …"`). The user gets immediate feedback that we heard them correctly, even if the agent takes 10s.
6. **Use `telegram_user_id` as the LangGraph `thread_id`.** This is what makes HITL work: the agent's `interrupt()` state is keyed by user, so when the user replies their next message resumes the same agent run.

## Sessions and HITL — the contract

The agent layer can pause mid-run by calling `langgraph.types.interrupt({"question": "..."})` from a tool. talkvault's pattern handles this with a tiny in-memory session table; we keep the same approach.

```
session.py owns a dict keyed by telegram_user_id:
  {
    "thread_id": str (== str(telegram_user_id)),
    "last_active": float (unix seconds),
    "expecting": "answer" | None,      # whether next text is a reply to interrupt
  }

SESSION_TIMEOUT defaults to 600s (10 min). After timeout the session is dropped
and the next message starts fresh.
```

The handler logic, expressed as flow:

```
on text message from user_id:
  if user has active session with expecting == "answer":
    pipeline.resume(thread_id=user_id, answer=text)
  else:
    pipeline.process(RawMessage(kind="text" or "link", text=text, ...))

on voice message from user_id:
  audio_bytes = download to memory
  reply "Transcribing..."
  transcript = await transcriber(audio_bytes)
  reply f"Transcript: {transcript}"
  pipeline.process(RawMessage(kind="voice", text=transcript,
                              voice_file_id=msg.voice.file_id, ...))
```

`pipeline.process(...)` and `pipeline.resume(...)` return one of:

- `{"reply": str}` — final answer, send to user, drop session.
- `{"interrupt_question": str}` — agent paused; set `expecting="answer"`, send the question, keep session.
- `{"error": str}` — something failed; reply, drop session.

The handler never inspects agent internals beyond this shape. All knowledge of `GraphOutput`, `Command(resume=...)`, etc. is hidden inside `pipeline.py`. (talkvault leaks some of that into `handlers.py`; we tighten it.)

## Auth — single tenant, allowlist

v0 is single-user (the dev). To prevent randos from typing `@your_bot` and racking up OpenAI bills:

- `config.py` reads `TELEGRAM_ALLOWED_USER_IDS` (comma-separated ints).
- A handler-level guard rejects updates from any other user with a polite "not authorized" reply and logs the attempt.
- This is the *only* auth in v0. Multi-user / per-user vaults are post-v0.

## Failure modes

| Failure | Handler response | Side effect |
|---|---|---|
| Whisper transcription error | "Transcription failed. Please try again." | Audio is **not** persisted to `raw/audio/`; no agent run; no commit |
| `pipeline.process` raises | "Could not process your message." with a request ID | Session dropped; partial vault state inspected by `vault.git_sync` and surfaced via log |
| Session timeout while user typing | Treated as a fresh message | Old thread state stays in the checkpointer until eviction |
| Telegram rate limit (HTTP 429) | python-telegram-bot retries; we log and otherwise ignore | None |

## Out of scope (v0)

- Webhooks / production-grade deployment hardening (talkvault has Docker/droplet scripts; copy them post-v0).
- Multi-user / per-user vault routing.
- Reply formatting (Markdown vs MarkdownV2 escapes — keep replies plain text in v0).
- Voice transcription in languages other than English/Spanish (Whisper handles both fine without configuration).
- Inline buttons for HITL approve/reject. v0 uses free-text replies because they round-trip identically through the same handler.
