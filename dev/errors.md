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
