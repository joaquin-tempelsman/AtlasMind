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
