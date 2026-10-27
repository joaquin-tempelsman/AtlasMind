# Errors Log

Long-form record of non-trivial errors encountered during AtlasMind development. Each entry captures what went wrong, why, the fix, and the generalized learning.

The one-line index lives in [`CLAUDE.md` §6](../CLAUDE.md#6-error-index). Update both in the same PR. Entries are immutable once filed — corrections go in a new entry referencing the old one.

**ID format:** `E-NNN`, zero-padded counter starting at `E-001`.

**What goes here** (per [`CLAUDE.md` §4b](../CLAUDE.md#4b-deverrorsmd--long-form-error-log)):
- Bugs found in code review or tests that weren't immediately obvious.
- Surprises from external systems (LangChain, Telegram, OpenAI, git).
- Misreads of the spec that led to wasted work.
- Flaky tests whose flakiness has a real underlying cause.

**What does not go here:**
- Typos or one-line mistakes caught while typing.
- Test failures from incomplete WIP code.

Entry template:

```markdown
## E-<NNN> — <short title>
**Date:** YYYY-MM-DD
**Encountered in:** <PR # or branch>
**Layer:** <e.g. vault.git_sync>

### What happened
- The actual error: stack trace summary, conditions to reproduce.

### Root cause
- 1–3 sentences. The real reason, not the surface symptom.

### Fix
- What we did. Reference the PR that closed it.

### Learning
- Generalized lesson. What should anyone working on this layer remember?
```

---

<!-- entries go below, newest at top -->

_No errors filed yet._

## E-001 — Link messages always fail in normalize
**Date:** 2026-10-27
**Encountered in:** fix/link-normalize (found by a local end-to-end chat QA harness)
**Layer:** pipeline, ingestion.normalize

### What happened
- Sending a bare URL in Telegram replied `Error: link_fetcher is required for kind='link'`. Every link message failed; `raw/links/` in the real vault was empty.

### Root cause
- `Pipeline.process()` called `normalize(raw, vault_root=...)` without a `link_fetcher`. The normalize layer was unit-tested with an injected fetcher and the pipeline tests mocked `normalize` entirely, so no test crossed that boundary with `kind="link"`.

### Fix
- `Pipeline` now owns a `LinkFetcher` (injectable, lazily defaulting to `ReadabilityLinkFetcher`) and passes it to `normalize()`. `LinkFetchError` becomes `{"error": "Couldn't fetch <url>: ..."}` per `dev_specs/04_ingestion_layer.md`. Fixed in the `fix/link-normalize` PR.

### Learning
- A boundary that is mocked on both sides is untested. For every optional dependency a layer requires for some input kind, add a contract test that drives the real callee through the caller with that input kind.

## E-002 — Ingest-time HITL answer filed as a new note
**Date:** 2026-10-27
**Encountered in:** fix/ingest-hitl (found by a local end-to-end chat QA harness)
**Layer:** pipeline, edge

### What happened
- When the KB ingestion agent called `ask_user` mid-batch, the question reached Telegram via `reply_fn`, but the user's reply was routed and queued as a brand-new item. The paused batch stayed in `_pending_ingest` forever.

### Root cause
- Router interrupts flow back through `process()`'s return value, where the edge's `_dispatch_result` sets `expecting="answer"`. Ingest runs from a timer, so its interrupt took a different path (`reply_fn`) that has no way to touch the session. The spec's "edge marks the session" step was only implemented for the synchronous path.

### Fix
- New `Pipeline(interrupt_fn=...)` callback carrying `(user_id, thread_id, question)`. The Telegram app's implementation sets the session to `expecting="answer"` on the ingest thread and sends the question. Fixed in the `fix/ingest-hitl` PR.

### Learning
- Every HITL path needs a test that asserts the *next user message* is a resume. Async work started by timers cannot report back through a return value, so it needs an explicit edge callback.

## E-003 — Resumed ingest batches never committed
**Date:** 2026-10-27
**Encountered in:** fix/ingest-hitl (found by a local end-to-end chat QA harness)
**Layer:** pipeline

### What happened
- After answering an ingest-time question, the note, index, log and entity changes were written but left uncommitted. The next unrelated batch's commit swept them in under its own message.

### Root cause
- The commit lived inline in `_fire_ingest()`. The `resume()` branch for ingest returned the summary without committing. Also, a timer firing while the KB was paused would start a second run on the same thread, contrary to `dev_specs/05_agent_layer.md` §4.

### Fix
- Extracted `_commit_batch()`, called from both completion paths. The paused batch's items are kept in `_pending_ingest` for the commit message. `_fire_ingest()` skips a paused KB and `resume()` re-arms it afterwards. Fixed in the `fix/ingest-hitl` PR.

### Learning
- When a flow can complete on two paths (direct or after resume), put the completion side effects in one function and test both paths for them.
